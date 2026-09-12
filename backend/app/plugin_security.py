import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import ROOT_DIR, settings
from .models import PluginRegistryVersion, PluginSecurityAssessment


MANIFEST_DIR = ROOT_DIR / "backend" / "plugins" / "manifests"
PROVIDER_TYPES = {
    "LLMProvider", "SearchProvider", "TrendSourceProvider", "OCRProvider",
    "CoverRendererProvider", "ImageGenerationProvider", "PublicMetricsProvider",
    "ExportProvider", "EmbeddingProvider",
}
FORBIDDEN_PERMISSION_PARTS = {
    "browser_profile", "browser.cookies", "cookie.export", "credentials.social",
    "captcha", "anti_scrape", "private_api", "system_security", "filesystem:*",
}
DENIED_LICENSES = {"", "unknown", "noassertion", "unlicensed", "proprietary"}
UNPINNED_REFS = {"", "main", "master", "latest", "head", "stable"}


class ToolDefinition(BaseModel):
    tool_id: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=500)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: list[str] = Field(default_factory=list, max_length=30)
    timeout_seconds: int = Field(ge=1, le=120)
    max_output_bytes: int = Field(ge=1024, le=52_428_800)


class PluginManifest(BaseModel):
    plugin_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    name: str = Field(min_length=2, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    provider_type: str
    source_repo: str = Field(min_length=3, max_length=1000)
    pinned_ref: str = Field(min_length=1, max_length=160)
    license: str = Field(min_length=1, max_length=120)
    maintenance_status: Literal["maintained", "limited", "planned", "archived"]
    permissions: list[str] = Field(default_factory=list, max_length=50)
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)
    read_dirs: list[str] = Field(default_factory=list, max_length=50)
    write_dirs: list[str] = Field(default_factory=list, max_length=50)
    secret_names: list[str] = Field(default_factory=list, max_length=30)
    needs_secret: bool
    retention: str = Field(min_length=2, max_length=500)
    timeout_seconds: int = Field(ge=1, le=600)
    health_check: str = Field(min_length=2, max_length=500)
    rollback_version: str = Field(min_length=1, max_length=120)
    enabled: bool
    built_in: bool
    tools: list[ToolDefinition] = Field(default_factory=list, max_length=30)

    @field_validator("provider_type")
    @classmethod
    def valid_provider_type(cls, value: str) -> str:
        if value not in PROVIDER_TYPES:
            raise ValueError("provider_type is not a supported provider contract")
        return value

    @field_validator("allowed_domains")
    @classmethod
    def plain_domain_allowlist(cls, values: list[str]) -> list[str]:
        for value in values:
            if "*" in value or "://" in value or "/" in value or not value.strip():
                raise ValueError("allowed_domains must contain exact hostnames only")
        return values

    @model_validator(mode="after")
    def secret_contract(self) -> "PluginManifest":
        if self.timeout_seconds > 120 and not (self.built_in and self.plugin_id == "image-generation-compatible"):
            raise ValueError("Only the built-in image adapter supports timeouts above 120 seconds")
        if self.needs_secret and not self.secret_names:
            raise ValueError("needs_secret requires at least one secret name")
        return self


class PluginEvidence(BaseModel):
    last_update: str | None = None
    commits_90d: int | None = Field(default=None, ge=0)
    open_issues: int | None = Field(default=None, ge=0)
    maintainer_trust: Literal["verified", "known", "unknown"] = "unknown"
    dependency_count: int | None = Field(default=None, ge=0)
    known_high_vulnerabilities: int = Field(default=0, ge=0)
    has_install_script: bool = False
    has_start_script: bool = False
    network_targets: list[str] = Field(default_factory=list, max_length=100)
    reads_browser_data: bool = False
    requires_password_cookie_or_captcha: bool = False
    bypasses_captcha_or_anti_scrape: bool = False
    uses_private_api: bool = False
    obfuscated_code: bool = False
    suspicious_binaries: bool = False
    changes_security_settings: bool = False


class AssessmentRequest(BaseModel):
    manifest: PluginManifest
    evidence: PluginEvidence
    confirm: bool = False


class GitHubInspectRequest(BaseModel):
    source_repo: str = Field(min_length=10, max_length=1000)
    pinned_ref: str = Field(min_length=1, max_length=160)


class ConfirmationRequest(BaseModel):
    confirm: bool = False


class PluginSecurityError(RuntimeError):
    pass


def _manifest_payload(manifest: PluginManifest | dict[str, Any]) -> dict[str, Any]:
    if isinstance(manifest, PluginManifest):
        return manifest.model_dump(mode="json")
    return PluginManifest.model_validate(manifest).model_dump(mode="json")


def manifest_hash(manifest: PluginManifest | dict[str, Any]) -> str:
    payload = _manifest_payload(manifest)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_builtin_manifests() -> list[PluginManifest]:
    manifests: list[PluginManifest] = []
    for path in sorted(MANIFEST_DIR.glob("*.json")):
        manifests.append(PluginManifest.model_validate_json(path.read_text(encoding="utf-8")))
    if not manifests:
        raise PluginSecurityError("No built-in plugin manifests were found")
    ids = [item.plugin_id for item in manifests]
    if len(ids) != len(set(ids)):
        raise PluginSecurityError("Built-in plugin IDs must be unique")
    return manifests


def tool_registry() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest in load_builtin_manifests():
        for tool in manifest.tools:
            rows.append({"plugin_id": manifest.plugin_id, "provider_type": manifest.provider_type, **tool.model_dump()})
    return rows


def _external_manifest_findings(manifest: PluginManifest, evidence: PluginEvidence) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    def add(level: str, code: str, message: str) -> None:
        findings.append({"level": level, "code": code, "message": message})

    parsed = urlparse(manifest.source_repo)
    if manifest.built_in or parsed.scheme != "https" or parsed.hostname != "github.com":
        add("blocking", "source_not_public_github", "Third-party candidates must use a public github.com HTTPS repository")
    if manifest.pinned_ref.strip().lower() in UNPINNED_REFS:
        add("blocking", "ref_not_pinned", "A commit SHA or immutable release/tag must be pinned")
    if manifest.license.strip().lower() in DENIED_LICENSES:
        add("blocking", "license_unacceptable", "The license is missing, unknown, or incompatible")
    if manifest.maintenance_status in {"archived", "planned"}:
        add("blocking", "maintenance_unacceptable", "Archived or merely planned projects cannot be activated")
    for permission in manifest.permissions + [p for tool in manifest.tools for p in tool.permissions]:
        normalized = permission.lower()
        if any(part in normalized for part in FORBIDDEN_PERMISSION_PARTS):
            add("blocking", "forbidden_permission", f"Forbidden permission requested: {permission}")
    allowed_prefixes = (
        f"data/plugin_data/{manifest.plugin_id}",
        f"uploads/plugin/{manifest.plugin_id}",
        f"exports/plugin/{manifest.plugin_id}",
    )
    for directory in manifest.read_dirs + manifest.write_dirs:
        clean = directory.replace("\\", "/").strip("/")
        if ".." in clean.split("/") or not any(clean == p or clean.startswith(f"{p}/") for p in allowed_prefixes):
            add("blocking", "directory_outside_sandbox", f"Directory is outside the plugin sandbox: {directory}")
    if any(domain not in manifest.allowed_domains for domain in evidence.network_targets):
        add("blocking", "network_target_not_allowed", "Observed network targets exceed the manifest domain allowlist")
    if evidence.known_high_vulnerabilities:
        add("blocking", "known_high_vulnerability", "Known high-severity vulnerabilities must be resolved first")
    gates = {
        "reads_browser_data": evidence.reads_browser_data,
        "credential_or_captcha_required": evidence.requires_password_cookie_or_captcha,
        "captcha_or_anti_scrape_bypass": evidence.bypasses_captcha_or_anti_scrape,
        "private_api": evidence.uses_private_api,
        "obfuscated_code": evidence.obfuscated_code,
        "suspicious_binary": evidence.suspicious_binaries,
        "security_settings_change": evidence.changes_security_settings,
    }
    for code, blocked in gates.items():
        if blocked:
            add("blocking", code, f"Security gate rejected: {code.replace('_', ' ')}")
    if evidence.has_install_script or evidence.has_start_script:
        add("warning", "scripts_require_static_review", "Install/start scripts were reported and must never run during this validation")
    if evidence.commits_90d is None or evidence.last_update is None:
        add("warning", "maintenance_evidence_incomplete", "Repository activity evidence is incomplete")
    if evidence.dependency_count is None:
        add("warning", "dependency_evidence_incomplete", "Dependency inventory has not been reviewed")
    if evidence.maintainer_trust == "unknown":
        add("warning", "maintainer_unknown", "Maintainer trust has not been independently verified")
    return findings


def assess_candidate(db: Session, payload: AssessmentRequest) -> PluginSecurityAssessment:
    if not payload.confirm:
        raise PluginSecurityError("Explicit confirmation is required before storing a security assessment")
    data = payload.manifest.model_dump(mode="json")
    findings = _external_manifest_findings(payload.manifest, payload.evidence)
    if any(item["level"] == "blocking" for item in findings):
        status = "rejected"
    elif any(item["code"] in {"maintenance_evidence_incomplete", "dependency_evidence_incomplete"} for item in findings):
        status = "needs_review"
    else:
        status = "approved"
    record = PluginSecurityAssessment(
        plugin_id=payload.manifest.plugin_id,
        candidate_version=payload.manifest.version,
        source_repo=payload.manifest.source_repo,
        pinned_ref=payload.manifest.pinned_ref,
        manifest=data,
        manifest_hash=manifest_hash(data),
        evidence=payload.evidence.model_dump(mode="json"),
        findings=findings,
        status=status,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def isolate_and_validate(db: Session, assessment_id: str, confirm: bool) -> PluginSecurityAssessment:
    if not confirm:
        raise PluginSecurityError("Explicit confirmation is required before isolated validation")
    record = db.get(PluginSecurityAssessment, assessment_id)
    if not record:
        raise PluginSecurityError("Assessment not found")
    if record.status != "approved":
        raise PluginSecurityError("Only approved assessments can enter isolation")
    workspace = settings.data_dir / "plugin_isolation" / record.id
    try:
        workspace.mkdir(parents=True, exist_ok=False)
        snapshot = workspace / "manifest.json"
        snapshot.write_text(json.dumps(record.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        reloaded = PluginManifest.model_validate_json(snapshot.read_text(encoding="utf-8"))
        findings = _external_manifest_findings(reloaded, PluginEvidence.model_validate(record.evidence))
        if manifest_hash(reloaded) != record.manifest_hash or any(item["level"] == "blocking" for item in findings):
            raise PluginSecurityError("Isolated manifest checksum or security regression failed")
        record.isolation_status = "passed"
        record.regression_summary = {
            "execution_mode": "manifest_only",
            "code_executed": False,
            "install_scripts_executed": False,
            "manifest_schema": "passed",
            "checksum": "passed",
            "security_regression": "passed",
            "workspace": str(workspace),
        }
        record.error_summary = None
    except Exception as exc:
        record.isolation_status = "failed"
        record.error_summary = str(exc)
        record.regression_summary = {"execution_mode": "manifest_only", "code_executed": False}
    db.commit()
    db.refresh(record)
    return record


def activate_assessment(db: Session, assessment_id: str, confirm: bool) -> PluginRegistryVersion:
    if not confirm:
        raise PluginSecurityError("Explicit confirmation is required before activation")
    assessment = db.get(PluginSecurityAssessment, assessment_id)
    if not assessment or assessment.status != "approved" or assessment.isolation_status != "passed":
        raise PluginSecurityError("Assessment and isolated regression must pass before activation")
    current = db.scalar(
        select(PluginRegistryVersion).where(
            PluginRegistryVersion.plugin_id == assessment.plugin_id,
            PluginRegistryVersion.status == "active",
        )
    )
    next_version = (db.scalar(select(func.max(PluginRegistryVersion.registry_version)).where(
        PluginRegistryVersion.plugin_id == assessment.plugin_id
    )) or 0) + 1
    if current:
        current.status = "retired"
    row = PluginRegistryVersion(
        plugin_id=assessment.plugin_id,
        registry_version=next_version,
        plugin_version=assessment.candidate_version,
        manifest=assessment.manifest,
        manifest_hash=assessment.manifest_hash,
        status="active",
        change_type="activation",
        source_assessment_id=assessment.id,
        source_registry_version=current.registry_version if current else 0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def rollback_registry(db: Session, plugin_id: str, registry_version: int, confirm: bool) -> PluginRegistryVersion:
    if not confirm:
        raise PluginSecurityError("Explicit confirmation is required before rollback")
    target = db.scalar(select(PluginRegistryVersion).where(
        PluginRegistryVersion.plugin_id == plugin_id,
        PluginRegistryVersion.registry_version == registry_version,
    ))
    if not target:
        raise PluginSecurityError("Registry version not found")
    current = db.scalar(select(PluginRegistryVersion).where(
        PluginRegistryVersion.plugin_id == plugin_id,
        PluginRegistryVersion.status == "active",
    ))
    next_version = (db.scalar(select(func.max(PluginRegistryVersion.registry_version)).where(
        PluginRegistryVersion.plugin_id == plugin_id
    )) or 0) + 1
    if current:
        current.status = "retired"
    restored_manifest = PluginManifest.model_validate(target.manifest)
    row = PluginRegistryVersion(
        plugin_id=plugin_id,
        registry_version=next_version,
        plugin_version=restored_manifest.version,
        manifest=restored_manifest.model_dump(mode="json"),
        manifest_hash=manifest_hash(restored_manifest),
        status="active",
        change_type="rollback",
        source_assessment_id=target.source_assessment_id,
        source_registry_version=target.registry_version,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_registry(db: Session) -> list[dict[str, Any]]:
    active_rows = {
        row.plugin_id: row for row in db.scalars(select(PluginRegistryVersion).where(
            PluginRegistryVersion.status == "active"
        ))
    }
    result: list[dict[str, Any]] = []
    for built_in in load_builtin_manifests():
        if built_in.plugin_id == "image-generation-compatible":
            from .image_provider import image_status
            status = image_status(db)
            host = urlparse(status["base_url"]).hostname
            built_in = built_in.model_copy(update={
                "enabled": status["available"], "allowed_domains": [host] if host else [],
                "timeout_seconds": int(status["timeout_seconds"]),
            })
        row = active_rows.pop(built_in.plugin_id, None)
        result.append({
            "manifest": row.manifest if row else built_in.model_dump(mode="json"),
            "registry_version": row.registry_version if row else 0,
            "change_type": row.change_type if row else "builtin",
            "activation_mode": "manifest_only" if row else "builtin_adapter",
        })
    for row in active_rows.values():
        result.append({"manifest": row.manifest, "registry_version": row.registry_version,
                       "change_type": row.change_type, "activation_mode": "manifest_only"})
    return result


def list_assessments(db: Session) -> list[PluginSecurityAssessment]:
    return list(db.scalars(select(PluginSecurityAssessment).order_by(
        PluginSecurityAssessment.created_at.desc()
    ).limit(100)))


def list_registry_history(db: Session, plugin_id: str) -> list[PluginRegistryVersion]:
    return list(db.scalars(select(PluginRegistryVersion).where(
        PluginRegistryVersion.plugin_id == plugin_id
    ).order_by(PluginRegistryVersion.registry_version.desc())))


def discard_isolation(assessment_id: str) -> None:
    workspace = (settings.data_dir / "plugin_isolation" / assessment_id).resolve()
    root = (settings.data_dir / "plugin_isolation").resolve()
    if root not in workspace.parents:
        raise PluginSecurityError("Isolation path escaped its root")
    if workspace.exists():
        shutil.rmtree(workspace)


async def inspect_github_repository(payload: GitHubInspectRequest) -> dict[str, Any]:
    parsed = urlparse(payload.source_repo)
    parts = [part for part in parsed.path.strip("/").removesuffix(".git").split("/") if part]
    if parsed.scheme != "https" or parsed.hostname != "github.com" or len(parts) != 2:
        raise PluginSecurityError("Only https://github.com/OWNER/REPO public repositories are supported")
    if payload.pinned_ref.strip().lower() in UNPINNED_REFS:
        raise PluginSecurityError("Use an immutable commit SHA or release/tag, not a moving branch name")
    owner, repo = parts
    base = f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "chaoshi-yuji-plugin-security-review"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers=headers) as client:
        repository, license_response, commit_response = await _github_requests(
            client, base, payload.pinned_ref
        )
    repo_data = repository.json()
    license_data = license_response.json() if license_response.status_code == 200 else {}
    commit_data = commit_response.json()
    return {
        "source_repo": payload.source_repo,
        "pinned_ref": payload.pinned_ref,
        "resolved_commit": commit_data.get("sha"),
        "license": (license_data.get("license") or {}).get("spdx_id") or "NOASSERTION",
        "last_update": repo_data.get("pushed_at"),
        "open_issues": repo_data.get("open_issues_count"),
        "archived": bool(repo_data.get("archived")),
        "disabled": bool(repo_data.get("disabled")),
        "owner_type": (repo_data.get("owner") or {}).get("type"),
        "stargazers_count": repo_data.get("stargazers_count"),
        "forks_count": repo_data.get("forks_count"),
        "rate_limit_remaining": repository.headers.get("x-ratelimit-remaining"),
        "evidence_limit": "Public GitHub metadata cannot prove maintainer trust or absence of vulnerabilities; static/dependency review is still required.",
    }


async def _github_requests(client: httpx.AsyncClient, base: str, pinned_ref: str):
    repository = await client.get(base)
    if repository.status_code != 200:
        raise PluginSecurityError(f"GitHub repository inspection failed ({repository.status_code})")
    license_response = await client.get(f"{base}/license")
    commit_response = await client.get(f"{base}/commits/{quote(pinned_ref, safe='')}")
    if commit_response.status_code != 200:
        raise PluginSecurityError(f"Pinned GitHub commit/release could not be resolved ({commit_response.status_code})")
    return repository, license_response, commit_response

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
SUPPORTED_FORMATS = {"PNG": ".png", "JPEG": ".jpg"}


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedImage:
    content_hash: str
    suffix: str
    media_type: str
    size_bytes: int
    width: int
    height: int


@dataclass(frozen=True)
class OcrResult:
    text: str
    lines: list[str]
    provider: str
    metadata: dict


class OCRProvider(Protocol):
    name: str

    def status(self) -> dict: ...

    def recognize(self, image_path: Path) -> OcrResult: ...


def validate_image(data: bytes) -> ValidatedImage:
    if not data:
        raise OcrError("截图为空，请重新选择图片")
    if len(data) > MAX_IMAGE_BYTES:
        raise OcrError("截图超过 15MB，请压缩后重试")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image_format = image.format or ""
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise OcrError("文件不是有效的 PNG 或 JPEG 图片") from exc
    if image_format not in SUPPORTED_FORMATS:
        raise OcrError("仅支持 PNG 或 JPEG 截图")
    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
        raise OcrError("截图尺寸无效或像素超过 2500 万")
    return ValidatedImage(
        content_hash=hashlib.sha256(data).hexdigest(),
        suffix=SUPPORTED_FORMATS[image_format],
        media_type="image/png" if image_format == "PNG" else "image/jpeg",
        size_bytes=len(data),
        width=width,
        height=height,
    )


def _normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    for _ in range(2):
        value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff，。！？；：、“”‘’])", "", value)
        value = re.sub(r"(?<=[，。！？；：、“”‘’])\s+(?=[\u3400-\u9fff])", "", value)
    return "\n".join(line.strip() for line in value.splitlines() if line.strip()).strip()


class WindowsOCRProvider:
    name = "windows-media-ocr"

    def __init__(self, language: str = "zh-Hans-CN", timeout_seconds: int = 30) -> None:
        self.language = language
        self.timeout_seconds = timeout_seconds
        self.script = Path(__file__).with_name("windows_ocr.ps1")

    def _run(self, arguments: list[str]) -> dict:
        if os.name != "nt" or not self.script.is_file():
            raise OcrError("当前系统不支持 Windows 本地 OCR")
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
        }
        try:
            completed = subprocess.run(
                [str(executable), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.script), *arguments],
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrError("本地 OCR 超过 30 秒，已停止且不会自动重试") from exc
        output = completed.stdout
        if len(output) > MAX_OUTPUT_BYTES:
            raise OcrError("本地 OCR 输出超过安全上限")
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
            raise OcrError(f"Windows 本地 OCR 失败：{detail[-1] if detail else '未知错误'}")
        try:
            return json.loads(output.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OcrError("Windows 本地 OCR 返回了无法解析的结果") from exc

    def status(self) -> dict:
        if os.name != "nt":
            return {"available": False, "provider": self.name, "local_only": True, "languages": [], "reason": "仅支持 Windows"}
        try:
            result = self._run(["-Language", self.language, "-Check"])
            return {**result, "provider": self.name}
        except OcrError as exc:
            return {"available": False, "provider": self.name, "local_only": True, "languages": [], "reason": str(exc)}

    def recognize(self, image_path: Path) -> OcrResult:
        result = self._run(["-Path", str(image_path.resolve()), "-Language", self.language])
        text = _normalize_text(str(result.get("text", "")))
        lines = [_normalize_text(str(line)) for line in result.get("lines", [])]
        lines = [line for line in lines if line]
        if not text:
            raise OcrError("本地 OCR 未识别出文字，请换一张更清晰的截图")
        return OcrResult(text=text, lines=lines, provider=self.name, metadata={"language": self.language, "local_only": True})


def build_ocr_provider() -> OCRProvider:
    return WindowsOCRProvider()


def _metric_number(value: str, *, ratio: bool = False) -> int | float:
    cleaned = value.replace(",", "").strip()
    multiplier = 10_000 if cleaned.endswith("万") else 1
    cleaned = cleaned.removesuffix("万").removesuffix("%").strip()
    number = float(cleaned) * multiplier
    if ratio:
        return round(number / 100, 6)
    return int(number) if number.is_integer() else round(number, 2)


def parse_analytics_metrics(text: str) -> dict[str, int | float]:
    normalized = text.replace("％", "%")
    normalized = re.sub(r"(?<=\d)\s*[·•]\s*(?=\d)", ".", normalized)
    normalized = re.sub(r"[ \t]", "", normalized)
    patterns: dict[str, tuple[str, bool]] = {
        "impressions": (r"(?:曝光量|曝光)[：:]?([0-9][0-9,.]*万?)", False),
        "views": (r"(?:浏览量|阅读量|浏览|阅读)[：:]?([0-9][0-9,.]*万?)", False),
        "likes": (r"(?:点赞量|点赞|赞)[：:]?([0-9][0-9,.]*万?)", False),
        "favorites": (r"(?:收藏量|收藏|藏)[：:]?([0-9][0-9,.]*万?)", False),
        "comments": (r"(?:评论量|评论|评)[：:]?([0-9][0-9,.]*万?)", False),
        "shares": (r"(?:分享量|分享|转发)[：:]?([0-9][0-9,.]*万?)", False),
        "new_followers": (r"(?:新增关注|新增粉丝|涨粉)[：:]?([0-9][0-9,.]*万?)", False),
        "profile_visits": (r"(?:主页访问量|主页访问)[：:]?([0-9][0-9,.]*万?)", False),
        "completion_rate": (r"(?:完读率|阅读完成率)[：:]?([0-9][0-9,.]*)%", True),
        "average_read_seconds": (r"(?:平均阅读时长|阅读时长)[：:]?([0-9][0-9,.]*)秒", False),
        "follower_view_ratio": (r"(?:粉丝占比|粉丝阅读占比)[：:]?([0-9][0-9,.]*)%", True),
        "non_follower_view_ratio": (r"(?:非粉丝占比|非粉丝阅读占比)[：:]?([0-9][0-9,.]*)%", True),
    }
    parsed: dict[str, int | float] = {}
    for key, (pattern, ratio) in patterns.items():
        match = re.search(pattern, normalized)
        if match:
            parsed[key] = _metric_number(match.group(1), ratio=ratio)
    return parsed


def parse_comment_lines(text: str) -> list[dict[str, str | None]]:
    comments: list[dict[str, str | None]] = []
    section_headers = {"评论区", "全部评论", "最新评论", "评论"}
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = re.sub(r"^[\s•·●○\-*—]+", "", raw_line).strip()
        if (
            not line
            or line in section_headers
            or re.fullmatch(r"(?:\d+\s*)?(?:秒|分钟|小时|天|周|月|年)前", line)
        ):
            continue
        author_label: str | None = None
        comment_text = line
        match = re.match(r"^([^：:]{1,20})[：:]\s*(.+)$", line)
        if match and not re.search(r"[。！？!?]", match.group(1)):
            author_label = match.group(1).strip()
            comment_text = match.group(2).strip()
        if comment_text:
            comments.append({"author_label": author_label, "text": comment_text[:2000]})
        if len(comments) >= 50:
            break
    return comments

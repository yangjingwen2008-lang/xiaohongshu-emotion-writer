import { useEffect, useState } from 'react'
import { LoaderCircle, Search, ShieldCheck } from 'lucide-react'
import type { PluginManifest, PluginRegistryItem, PluginAssessment, PluginHistory } from '../types'
import { request } from '../lib/api'

const candidateManifestTemplate = JSON.stringify({
  plugin_id: 'example-search', name: 'Example reviewed search provider', version: '1.0.0',
  provider_type: 'SearchProvider', source_repo: 'https://github.com/OWNER/REPO',
  pinned_ref: '请替换为不可变 commit SHA 或 release tag', license: 'MIT', maintenance_status: 'maintained',
  permissions: ['network:https://api.example.com'], allowed_domains: ['api.example.com'],
  read_dirs: ['data/plugin_data/example-search'], write_dirs: ['data/plugin_data/example-search/cache'],
  secret_names: [], needs_secret: false, retention: '本地缓存随插件移除而删除', timeout_seconds: 20,
  health_check: 'manifest-only schema and checksum validation', rollback_version: '0.9.0',
  enabled: true, built_in: false,
  tools: [{ tool_id: 'example.search', description: '查询已登记的公开 API', input_schema: { type: 'object' }, output_schema: { type: 'object' }, permissions: ['network:https://api.example.com'], timeout_seconds: 20, max_output_bytes: 100000 }],
}, null, 2)

export function PluginSecurityPanel() {
  const [registry, setRegistry] = useState<PluginRegistryItem[]>([])
  const [assessments, setAssessments] = useState<PluginAssessment[]>([])
  const [manifestText, setManifestText] = useState(candidateManifestTemplate)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [githubEvidence, setGithubEvidence] = useState<Record<string, any> | null>(null)
  const [history, setHistory] = useState<Record<string, PluginHistory[]>>({})
  const [reviewEvidence, setReviewEvidence] = useState({ commits_90d: '', dependency_count: '', maintainer_trust: 'unknown' })
  const [risk, setRisk] = useState({
    known_high_vulnerabilities: 0, has_install_script: false, has_start_script: false,
    reads_browser_data: false, requires_password_cookie_or_captcha: false,
    bypasses_captcha_or_anti_scrape: false, uses_private_api: false, obfuscated_code: false,
    suspicious_binaries: false, changes_security_settings: false,
  })
  async function load() {
    const [manifests, rows] = await Promise.all([
      request<PluginRegistryItem[]>('/plugins/manifests'), request<PluginAssessment[]>('/plugins/assessments'),
    ])
    setRegistry(manifests); setAssessments(rows)
  }
  useEffect(() => { void Promise.resolve().then(load).catch((e) => setError((e as Error).message)) }, [])
  function parsedManifest() { return JSON.parse(manifestText) as PluginManifest }
  async function inspectGithub() {
    setBusy('github'); setError(''); setGithubEvidence(null)
    try {
      const manifest = parsedManifest()
      const result = await request<Record<string, any>>('/plugins/github/inspect', { method: 'POST', body: JSON.stringify({ source_repo: manifest.source_repo, pinned_ref: manifest.pinned_ref }) })
      setGithubEvidence(result)
      setManifestText(JSON.stringify({ ...manifest, license: result.license || manifest.license, pinned_ref: result.resolved_commit || manifest.pinned_ref }, null, 2))
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function assess(event: React.FormEvent) {
    event.preventDefault(); setBusy('assess'); setError('')
    try {
      const manifest = parsedManifest()
      await request('/plugins/assessments', {
        method: 'POST',
        body: JSON.stringify({
          manifest,
          evidence: {
            ...risk,
            last_update: githubEvidence?.last_update || null,
            commits_90d: reviewEvidence.commits_90d === '' ? null : Number(reviewEvidence.commits_90d),
            open_issues: githubEvidence?.open_issues ?? null,
            maintainer_trust: reviewEvidence.maintainer_trust,
            dependency_count: reviewEvidence.dependency_count === '' ? null : Number(reviewEvidence.dependency_count),
            network_targets: manifest.allowed_domains,
          },
          confirm: confirmed,
        }),
      })
      setConfirmed(false); await load()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function advance(id: string, action: 'isolate' | 'activate') {
    const wording = action === 'isolate' ? '在独立目录做清单校验和静态回归（不会执行代码）' : '激活这个注册清单版本（不会加载第三方代码）'
    if (!window.confirm(`确认${wording}？`)) return
    setBusy(`${action}-${id}`); setError('')
    try { await request(`/plugins/assessments/${id}/${action}`, { method: 'POST', body: JSON.stringify({ confirm: true }) }); await load() }
    catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function loadHistory(pluginId: string) {
    setBusy(`history-${pluginId}`); setError('')
    try {
      const rows = await request<PluginHistory[]>(`/plugins/${pluginId}/history`)
      setHistory((current) => ({ ...current, [pluginId]: rows }))
    }
    catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function rollback(pluginId: string, version: number) {
    if (!window.confirm(`确认把 ${pluginId} 的注册清单恢复到 R${version}？系统会保留全部历史。`)) return
    setBusy(`rollback-${pluginId}`); setError('')
    try { await request(`/plugins/${pluginId}/rollback/${version}`, { method: 'POST', body: JSON.stringify({ confirm: true }) }); await load(); await loadHistory(pluginId) }
    catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  const riskFields: Array<[keyof typeof risk, string]> = [
    ['has_install_script', '包含安装脚本'], ['has_start_script', '包含启动脚本'],
    ['reads_browser_data', '读取浏览器资料'], ['requires_password_cookie_or_captcha', '需要密码、Cookie 或验证码'],
    ['bypasses_captcha_or_anti_scrape', '绕过验证码或反爬'], ['uses_private_api', '使用私有 API'],
    ['obfuscated_code', '存在混淆代码'], ['suspicious_binaries', '包含可疑二进制'],
    ['changes_security_settings', '修改系统安全设置'],
  ]
  return <section className="plugin-security-panel">
    <div className="panel-title"><span>Provider 与插件安全中心</span><small>{registry.length} 个机器可读清单 · Manifest-only 第三方激活</small></div>
    <p className="constitution-note"><ShieldCheck size={16} />第三方候选只做公开元数据核验、静态清单扫描和隔离回归；不运行下载代码、安装/启动脚本，也不读取浏览器配置、Cookie 或社交账号。</p>
    {error && <div className="error-banner">{error}</div>}
    <div className="plugin-registry-grid">{registry.map(({ manifest, registry_version, activation_mode }) => <article key={manifest.plugin_id} className="plugin-card">
      <header><div><strong>{manifest.name}</strong><small>{manifest.provider_type}</small></div><span className={manifest.enabled ? 'status-ready' : 'status-off'}>{manifest.enabled ? '启用' : '未启用'}</span></header>
      <dl><dt>ID / 版本</dt><dd>{manifest.plugin_id} · {manifest.version} · R{registry_version}</dd><dt>来源 / 固定点</dt><dd>{manifest.source_repo}<br />{manifest.pinned_ref}</dd><dt>License / 维护</dt><dd>{manifest.license} · {manifest.maintenance_status}</dd><dt>域名白名单</dt><dd>{manifest.allowed_domains.join('、') || '无网络访问'}</dd><dt>读 / 写目录</dt><dd>{manifest.read_dirs.join('、') || '无'} / {manifest.write_dirs.join('、') || '无'}</dd><dt>权限</dt><dd>{manifest.permissions.join('、') || '无额外权限'}</dd><dt>密钥 / 保留</dt><dd>{manifest.needs_secret ? manifest.secret_names.join('、') : '不需要密钥'} · {manifest.retention}</dd><dt>超时 / 健康检查</dt><dd>{manifest.timeout_seconds}s · {manifest.health_check}</dd><dt>回滚 / 激活方式</dt><dd>{manifest.rollback_version} · {activation_mode}</dd></dl>
      {registry_version > 0 && <button className="ghost" disabled={!!busy} onClick={() => loadHistory(manifest.plugin_id)}>查看与回滚注册版本</button>}
      {(history[manifest.plugin_id] || []).map((row) => <div className="plugin-history-row" key={`${manifest.plugin_id}-${row.registry_version}`}><span>R{row.registry_version}</span><small>{row.plugin_version} · {row.change_type} · {row.status}</small>{row.status !== 'active' && <button className="ghost" onClick={() => rollback(manifest.plugin_id, row.registry_version)}>恢复</button>}</div>)}
    </article>)}</div>
    <details className="plugin-assessment-box"><summary>评估一个 GitHub 第三方候选</summary><form onSubmit={assess}>
      <label>机器可读 Manifest JSON<textarea className="manifest-editor" required value={manifestText} onChange={(e) => setManifestText(e.target.value)} /></label>
      <div className="proposal-actions"><button type="button" className="ghost" disabled={!!busy} onClick={inspectGithub}>{busy === 'github' ? <LoaderCircle className="spin" size={15} /> : <Search size={15} />}核验公开仓库、License 与固定提交</button></div>
      {githubEvidence && <div className="github-evidence"><strong>GitHub 公开证据</strong><p>固定提交：{githubEvidence.resolved_commit}</p><p>最近推送：{githubEvidence.last_update || '未知'} · Issues：{githubEvidence.open_issues ?? '未知'} · License：{githubEvidence.license}</p><small>{githubEvidence.evidence_limit}</small></div>}
      <div className="review-evidence-grid"><label>近 90 天 commit 数<input type="number" min="0" value={reviewEvidence.commits_90d} onChange={(e) => setReviewEvidence({ ...reviewEvidence, commits_90d: e.target.value })} placeholder="人工核对后填写" /></label><label>直接与间接依赖数<input type="number" min="0" value={reviewEvidence.dependency_count} onChange={(e) => setReviewEvidence({ ...reviewEvidence, dependency_count: e.target.value })} placeholder="审查依赖清单后填写" /></label><label>维护者可信度<select value={reviewEvidence.maintainer_trust} onChange={(e) => setReviewEvidence({ ...reviewEvidence, maintainer_trust: e.target.value })}><option value="unknown">未知</option><option value="known">已知维护者</option><option value="verified">已独立核验</option></select></label></div>
      <label>已知高危漏洞数<input type="number" min="0" value={risk.known_high_vulnerabilities} onChange={(e) => setRisk({ ...risk, known_high_vulnerabilities: Number(e.target.value) })} /></label>
      <div className="risk-grid">{riskFields.map(([key, label]) => <label className="confirm-line" key={key}><input type="checkbox" checked={Boolean(risk[key])} onChange={(e) => setRisk({ ...risk, [key]: e.target.checked })} />{label}</label>)}</div>
      <label className="confirm-line"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />我确认以上清单和安全证据真实；评估只保存记录，不安装或执行候选代码</label>
      <button className="primary" disabled={!confirmed || !!busy}>{busy === 'assess' ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}运行安全门禁评估</button>
    </form></details>
    <div className="assessment-list"><div className="panel-title"><span>评估与隔离记录</span><small>{assessments.length} 条</small></div>{assessments.length ? assessments.map((item) => <article key={item.id} className="assessment-row"><div><strong>{item.plugin_id} · {item.candidate_version}</strong><small>{item.status} · isolation: {item.isolation_status} · {new Date(item.created_at).toLocaleString('zh-CN')}</small></div><div className="finding-list">{item.findings.length ? item.findings.map((finding) => <p key={`${item.id}-${finding.code}`} className={finding.level}>{finding.level === 'blocking' ? '阻断' : '提醒'} · {finding.message}</p>) : <p className="pass">门禁未发现阻断项</p>}</div><div className="proposal-actions">{item.status === 'approved' && item.isolation_status === 'not_started' && <button className="ghost" disabled={!!busy} onClick={() => advance(item.id, 'isolate')}>隔离验证</button>}{item.status === 'approved' && item.isolation_status === 'passed' && <button className="primary" disabled={!!busy} onClick={() => advance(item.id, 'activate')}>人工激活清单</button>}</div></article>) : <div className="empty-note"><ShieldCheck size={20} /><p>还没有第三方候选评估记录。</p></div>}</div>
  </section>
}

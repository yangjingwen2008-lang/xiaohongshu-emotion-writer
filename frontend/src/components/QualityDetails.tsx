import { useEffect, useState } from 'react'
import { ExternalLink, LoaderCircle, Save, ShieldCheck } from 'lucide-react'
import { request } from '../lib/api'

export function MemoryDisclosure({ report }: { report: Record<string, any> }) {
  const rules = report.style_rules_used || []
  const avoided = report.avoid_history || []
  return <section className="memory-disclosure"><div className="panel-title"><span>本次风格记忆与历史避重</span><small>编辑宪法 V{report.editorial_constitution_version ?? 0} · 本地历史检索</small></div><p className="retrieval-scope"><ShieldCheck size={15} />{report.retrieval_scope}</p><div className="memory-columns"><div><h3>本次采用的风格规则</h3>{rules.length ? rules.map((rule: string) => <p key={rule}>{rule}</p>) : <p className="muted">尚无已确认的个性化规则，仅使用编辑宪法。</p>}</div><div><h3>本次要求避开的历史重复</h3>{avoided.length ? avoided.map((item: any) => <article key={item.version_id}><strong>{item.historical_title}</strong><small>{[...(item.scenes || []), ...(item.structure_tags || []), ...(item.imagery || []), item.ending_type].filter(Boolean).join(' · ')}</small></article>) : <p className="muted">没有检索到需要避开的历史写法。</p>}</div></div></section>
}

export function OriginalityDisclosure({ report }: { report: Record<string, any> }) {
  const externalMatches = [...(report.web_matches || []), ...(report.manual_matches || [])]
  const statusLabel = report.external_check_status === 'completed' ? '公网有限范围已完成' : report.external_check_status === 'failed' ? '公网检查失败' : '公网检查不可用'
  return <section className="originality-disclosure"><div className="panel-title"><span>原创度检测范围</span><small>{report.passes_gate ? '门禁通过' : '需要重构'} · {statusLabel}</small></div><div className="scope-grid"><p><b>标题</b>{report.title_risk}</p><p><b>开头</b>{report.opening_risk}</p><p><b>结构</b>{report.structure_risk}</p><p><b>场景</b>{report.scene_risk}</p><p><b>结尾</b>{report.ending_risk}</p><p><b>意象</b>{report.metaphor_risk}</p></div><div className="coverage-note"><span>本系统不宣称“全网原创”。已完成与不可用范围如下：</span>{(report.coverage_details || []).map((item: any, index: number) => <span key={`${item.source}-${index}`}>{item.source}：{item.status}</span>)}<span>未覆盖：{(report.uncovered_sources || []).join('、') || '无'}</span>{report.external_error_summary && <span>错误：{report.external_error_summary}</span>}</div>{report.matches?.length > 0 && <div className="similarity-list"><h3>本地历史相似项</h3>{report.matches.map((match: any) => <p key={`${match.content_id}-${match.version}`}><strong>{match.title}</strong><small>标题 {Math.round((match.title_similarity || 0) * 100)}% · 正文 n-gram {Math.round((match.body_ngram_similarity || 0) * 100)}% · 开头 {Math.round((match.opening_similarity || 0) * 100)}%</small></p>)}</div>}{externalMatches.length > 0 && <div className="similarity-list"><h3>公开网页或手工来源相似项</h3>{externalMatches.map((match: any, index: number) => <p key={match.url || match.source_id || index}><strong>{match.title || match.label}</strong><small>{match.risk}风险 · 片段 {Math.round(((match.fragment_similarity ?? match.body_ngram_similarity) || 0) * 100)}%{match.url && <> · <a href={match.url} target="_blank" rel="noreferrer">查看公开证据</a></>}</small></p>)}</div>}</section>
}

export function CitationDisclosure({ report }: { report: Record<string, any> }) {
  if (report.check_status === 'not_needed') return <section className="citation-disclosure"><div className="panel-title"><span>文化引用核验</span><small>本稿无需核验</small></div><p>{report.coverage_note}</p></section>
  return <section className="citation-disclosure"><div className="panel-title"><span>文化引用核验</span><small>{report.check_status === 'completed' ? '已完成有限公开来源核验' : report.check_status === 'failed' ? '中途失败并停止' : '公开来源不可用'}</small></div><p>{report.coverage_note}</p>{report.error_summary && <div className="error-banner">{report.error_summary}</div>}<div className="citation-items">{(report.items || []).map((item: any, index: number) => <article key={index}><strong>{item.reference?.quote || item.reference?.text || item.reference?.work || item.reference?.title || `引用 ${index + 1}`}</strong><small>{item.status === 'verified' ? '已找到支持证据' : item.status === 'partially_verified' ? '仅部分信息有证据' : '未核实'}</small><p>{item.recommendation}</p>{(item.evidence || []).map((evidence: any) => <a key={evidence.url} href={evidence.url} target="_blank" rel="noreferrer"><ExternalLink size={13} />{evidence.title}</a>)}</article>)}</div></section>
}

export function ManualOriginalityPanel({ contentId, onSaved, onRerun, busy }: { contentId: string; onSaved: () => Promise<void>; onRerun: () => void; busy: boolean }) {
  const [sources, setSources] = useState<any[]>([])
  const [sourceType, setSourceType] = useState<'url' | 'title' | 'body'>('body')
  const [label, setLabel] = useState('')
  const [sourceValue, setSourceValue] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { request<any[]>(`/contents/${contentId}/originality-sources`).then(setSources).catch((e) => setError((e as Error).message)) }, [contentId])
  async function save(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError('')
    try {
      await request(`/contents/${contentId}/originality-sources`, { method: 'POST', body: JSON.stringify({ source_type: sourceType, label, source_value: sourceValue, confirm: confirmed }) })
      setLabel(''); setSourceValue(''); setConfirmed(false)
      setSources(await request<any[]>(`/contents/${contentId}/originality-sources`))
      await onSaved()
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  return <section className="manual-source-panel"><div className="panel-title"><span>手工补充比对来源</span><small>不登录、不抓取私域内容</small></div><p>可粘贴公开链接、标题或正文。仅“标题/正文”会直接参与相似度比对；链接只作为范围记录。</p>{error && <div className="error-banner">{error}</div>}<form onSubmit={save}><label>来源类型<select value={sourceType} onChange={(e) => setSourceType(e.target.value as any)}><option value="body">粘贴正文</option><option value="title">粘贴标题</option><option value="url">公开链接</option></select></label><label>来源标签<input required maxLength={240} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="例如：我记得的一篇公开笔记" /></label><label>{sourceType === 'url' ? '公开链接' : sourceType === 'title' ? '标题内容' : '正文内容'}<textarea required maxLength={20000} value={sourceValue} onChange={(e) => setSourceValue(e.target.value)} /></label><label className="confirm-line"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />我确认保存这条手工来源，仅用于本地原创性比对</label><button className="primary" disabled={!confirmed || saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}保存来源</button></form>{sources.length > 0 && <div className="manual-source-list">{sources.map((item) => <p key={item.id}><strong>{item.label}</strong><small>{item.source_type === 'body' ? '正文' : item.source_type === 'title' ? '标题' : '链接'} · 已保存</small></p>)}</div>}<button className="quality-button" disabled={busy} onClick={onRerun}><ShieldCheck size={15} />用当前来源重新运行质量门禁</button></section>
}

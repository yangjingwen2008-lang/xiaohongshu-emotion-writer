import { useCallback, useEffect, useState } from 'react'
import { BarChart3, Check, ChevronRight, ExternalLink, FileText, LoaderCircle, Save, ShieldCheck, Sparkles, Trash2 } from 'lucide-react'
import type { OcrRun, Publication, DueSnapshot, AnalyticsReport, CommentRecord } from '../types'
import { API, request, uploadRequest } from '../lib/api'
import { suggestedCommentText } from '../lib/content'

export function AnalyticsPage() {
  const [publications, setPublications] = useState<Publication[]>([])
  const [due, setDue] = useState<DueSnapshot[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [dayOffset, setDayOffset] = useState<1 | 3 | 7>(1)
  const [metrics, setMetrics] = useState<Record<string, string>>({})
  const [note, setNote] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [ocrRuns, setOcrRuns] = useState<OcrRun[]>([])
  const [pendingOcr, setPendingOcr] = useState<OcrRun | null>(null)
  const [ocrText, setOcrText] = useState('')
  const [reports, setReports] = useState<AnalyticsReport[]>([])
  const [reportType, setReportType] = useState<'single' | 'weekly' | 'monthly'>('single')
  const [reportPublicationId, setReportPublicationId] = useState('')
  const [reportStart, setReportStart] = useState(() => { const value = new Date(); value.setDate(value.getDate() - 6); return value.toISOString().slice(0, 10) })
  const [reportEnd, setReportEnd] = useState(() => new Date().toISOString().slice(0, 10))
  const [reportSelections, setReportSelections] = useState<Record<string, string[]>>({})
  const [reportConfirmed, setReportConfirmed] = useState<Record<string, boolean>>({})
  const [commentPublicationId, setCommentPublicationId] = useState('')
  const [comments, setComments] = useState<CommentRecord[]>([])
  const [commentOcrRuns, setCommentOcrRuns] = useState<OcrRun[]>([])
  const [pendingCommentOcr, setPendingCommentOcr] = useState<OcrRun | null>(null)
  const [commentText, setCommentText] = useState('')
  const [commentsConfirmed, setCommentsConfirmed] = useState(false)
  const [replyConsent, setReplyConsent] = useState<Record<string, boolean>>({})
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({})
  const [copiedReplyId, setCopiedReplyId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const loadAnalytics = useCallback(async () => {
    const [nextPublications, nextDue, nextOcrRuns, nextReports, nextCommentOcrRuns] = await Promise.all([
      request<Publication[]>('/publications'),
      request<DueSnapshot[]>('/publications/due'),
      request<OcrRun[]>('/ocr/runs?purpose=analytics'),
      request<AnalyticsReport[]>('/analytics/reports'),
      request<OcrRun[]>('/ocr/runs?purpose=comments'),
    ])
    setPublications(nextPublications); setDue(nextDue); setOcrRuns(nextOcrRuns); setReports(nextReports); setCommentOcrRuns(nextCommentOcrRuns)
    if (!reportPublicationId && nextPublications[0]) setReportPublicationId(nextPublications[0].id)
    if (!commentPublicationId && nextPublications[0]) setCommentPublicationId(nextPublications[0].id)
  }, [commentPublicationId, reportPublicationId])
  useEffect(() => { void Promise.resolve().then(loadAnalytics).catch((e) => setError((e as Error).message)) }, [loadAnalytics])
  const loadComments = useCallback(async () => {
    if (!commentPublicationId) { setComments([]); return }
    const nextComments = await request<CommentRecord[]>(`/publications/${commentPublicationId}/comments`)
    setComments(nextComments)
    const pending = commentOcrRuns.find((item) => item.status === 'pending_confirmation' && item.engine_metadata?.publication_id === commentPublicationId) || null
    setPendingCommentOcr(pending)
    if (pending) setCommentText((current) => current || suggestedCommentText(pending))
  }, [commentOcrRuns, commentPublicationId])
  useEffect(() => { void Promise.resolve().then(loadComments).catch((e) => setError((e as Error).message)) }, [loadComments])
  function beginSnapshot(publicationId: string, suggestedDay?: 1 | 3 | 7) {
    const nextDay = suggestedDay || 1
    const pending = ocrRuns.find((item) => item.status === 'pending_confirmation' && item.engine_metadata?.publication_id === publicationId && item.engine_metadata?.day_offset === nextDay) || null
    setSelectedId(publicationId); setDayOffset(nextDay); setPendingOcr(pending); setOcrText(pending?.corrected_text || pending?.recognized_text || '')
    setMetrics(pending ? metricsFromOcr(pending) : {}); setNote(''); setConfirmed(false)
  }
  function metricsFromOcr(run: OcrRun) {
    const parsed = run.engine_metadata?.parsed_metrics || {}
    return Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, String(['completion_rate', 'follower_view_ratio', 'non_follower_view_ratio'].includes(key) ? Number(value) * 100 : value)]))
  }
  function selectSnapshotDay(day: 1 | 3 | 7) {
    const pending = ocrRuns.find((item) => item.status === 'pending_confirmation' && item.engine_metadata?.publication_id === selectedId && item.engine_metadata?.day_offset === day) || null
    setDayOffset(day); setPendingOcr(pending); setOcrText(pending?.corrected_text || pending?.recognized_text || ''); setMetrics(pending ? metricsFromOcr(pending) : {}); setConfirmed(false)
  }
  function payloadMetrics() {
    return Object.fromEntries(Object.entries(metrics).filter(([, value]) => value !== '').map(([key, value]) => [key, ['completion_rate', 'follower_view_ratio', 'non_follower_view_ratio'].includes(key) ? Number(value) / 100 : Number(value)]))
  }
  async function saveSnapshot(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (pendingOcr) await request(`/ocr/runs/${pendingOcr.id}/confirm-analytics`, { method: 'POST', body: JSON.stringify({ corrected_text: ocrText, metrics: payloadMetrics(), note: note || null, confirm: confirmed }) })
      else await request(`/publications/${selectedId}/snapshots`, { method: 'POST', body: JSON.stringify({ day_offset: dayOffset, metrics: payloadMetrics(), note: note || null, confirm: confirmed }) })
      setSelectedId(''); setPendingOcr(null); setOcrText(''); await loadAnalytics()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function uploadAnalyticsScreenshot(file?: File) {
    if (!file || !selectedId) return
    setBusy(true); setError('')
    const form = new FormData(); form.append('publication_id', selectedId); form.append('day_offset', String(dayOffset)); form.append('file', file)
    try {
      const run = await uploadRequest<OcrRun>('/ocr/analytics', form)
      setPendingOcr(run); setOcrText(run.corrected_text || run.recognized_text || ''); setMetrics(metricsFromOcr(run)); setConfirmed(false)
      await loadAnalytics()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function deleteAnalyticsScreenshot(run: OcrRun) {
    if (!window.confirm('永久删除这张数据后台截图？已确认的数据快照会保留。')) return
    setBusy(true); setError('')
    try { await request(`/ocr/runs/${run.id}/image`, { method: 'DELETE', body: JSON.stringify({ confirm: true }) }); await loadAnalytics() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function generateAnalyticsReport() {
    setBusy(true); setError('')
    try {
      const body: Record<string, string> = { report_type: reportType }
      if (reportType === 'single') body.publication_id = reportPublicationId
      else { body.period_start = reportStart; body.period_end = reportEnd }
      await request('/analytics/reports/generate', { method: 'POST', body: JSON.stringify(body) })
      await loadAnalytics()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  function toggleReportSuggestion(reportId: string, suggestionId: string) {
    const selected = reportSelections[reportId] || []
    setReportSelections({ ...reportSelections, [reportId]: selected.includes(suggestionId) ? selected.filter((item) => item !== suggestionId) : [...selected, suggestionId] })
  }
  async function confirmAnalyticsReport(reportId: string) {
    setBusy(true); setError('')
    try {
      await request(`/analytics/reports/${reportId}/confirm`, { method: 'POST', body: JSON.stringify({ selected_suggestion_ids: reportSelections[reportId] || [], confirm: reportConfirmed[reportId] || false }) })
      await loadAnalytics()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function dismissAnalyticsReport(reportId: string) {
    if (!window.confirm('确认忽略这份复盘？报告历史会保留，但建议不会进入后续创作记忆。')) return
    setBusy(true); setError('')
    try { await request(`/analytics/reports/${reportId}/dismiss`, { method: 'POST', body: JSON.stringify({ confirm: true }) }); await loadAnalytics() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  function parseCommentBatch(value: string) {
    const sectionHeaders = new Set(['评论区', '全部评论', '最新评论', '评论'])
    return value.split(/\r?\n/).map((line) => line.replace(/^[\s•·●○\-*—]+/, '').trim()).filter((line) => line && !sectionHeaders.has(line) && !/^(?:\d+\s*)?(?:秒|分钟|小时|天|周|月|年)前$/.test(line)).slice(0, 50).map((line) => {
      const match = line.match(/^([^：:]{1,20})[：:]\s*(.+)$/)
      return match ? { author_label: match[1].trim(), text: match[2].trim() } : { author_label: null, text: line }
    })
  }
  async function saveCommentBatch() {
    const parsed = parseCommentBatch(commentText)
    setBusy(true); setError('')
    try {
      if (pendingCommentOcr) await request(`/ocr/runs/${pendingCommentOcr.id}/confirm-comments`, { method: 'POST', body: JSON.stringify({ corrected_text: commentText, comments: parsed, confirm: commentsConfirmed }) })
      else await request(`/publications/${commentPublicationId}/comments`, { method: 'POST', body: JSON.stringify({ comments: parsed, confirm: commentsConfirmed }) })
      setCommentText(''); setCommentsConfirmed(false); setPendingCommentOcr(null); await loadAnalytics()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function uploadCommentScreenshot(file?: File) {
    if (!file || !commentPublicationId) return
    setBusy(true); setError('')
    const form = new FormData(); form.append('publication_id', commentPublicationId); form.append('file', file)
    try {
      const run = await uploadRequest<OcrRun>('/ocr/comments', form)
      setPendingCommentOcr(run); setCommentText(suggestedCommentText(run)); setCommentsConfirmed(false); await loadAnalytics()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function discardCommentScreenshot() {
    if (!pendingCommentOcr || !window.confirm('永久删除这张评论截图并放弃 OCR 结果？')) return
    setBusy(true); setError('')
    try { await request(`/ocr/runs/${pendingCommentOcr.id}/discard`, { method: 'POST', body: JSON.stringify({ confirm: true }) }); setPendingCommentOcr(null); setCommentText(''); setCommentsConfirmed(false); await loadAnalytics() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function generateCommentReply(commentId: string) {
    setBusy(true); setError('')
    try { await request(`/comments/${commentId}/reply-suggestions`, { method: 'POST', body: JSON.stringify({ confirm_send_to_model: replyConsent[commentId] || false }) }); setReplyConsent({ ...replyConsent, [commentId]: false }); await loadComments() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function copyCommentReply(commentId: string, fallback: string) {
    const value = replyDrafts[commentId] ?? fallback
    if (!value.trim()) return
    try { await navigator.clipboard.writeText(value); setCopiedReplyId(commentId); window.setTimeout(() => setCopiedReplyId(''), 1800) }
    catch { setError('复制失败，请手动选中回复文字复制。') }
  }
  async function removeSavedComment(commentId: string) {
    if (!window.confirm('永久删除这条本地评论和回复建议历史？')) return
    setBusy(true); setError('')
    try { await request(`/comments/${commentId}`, { method: 'DELETE', body: JSON.stringify({ confirm: true }) }); await loadComments() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const metricFields = [['views', '浏览量'], ['impressions', '曝光量'], ['likes', '点赞'], ['favorites', '收藏'], ['comments', '评论'], ['shares', '分享'], ['new_followers', '新增关注'], ['profile_visits', '主页访问'], ['completion_rate', '完读率 %'], ['average_read_seconds', '平均阅读秒数'], ['follower_view_ratio', '粉丝占比 %'], ['non_follower_view_ratio', '非粉丝占比 %']]
  const percent = (value: number | string | undefined) => typeof value === 'number' ? `${(value * 100).toFixed(2)}%` : '分母不足，未计算'
  return (
    <main className="page analytics-page">
      <header className="analytics-head"><div><div className="eyebrow">真实数据复盘</div><h1>发布记录与数据快照</h1><p>只记录你手动发布后的公开链接和确认数据，不读取账号后台或 Cookie。</p></div><strong>{publications.length}<small>篇已发布</small></strong></header>
      {error && <div className="error-banner">{error}</div>}
      {due.length > 0 && <section className="due-panel"><div className="panel-title"><span>现在需要录入</span><small>{due.length} 个快照</small></div>{due.map((item) => <button key={`${item.publication_id}-${item.day_offset}`} onClick={() => beginSnapshot(item.publication_id, item.day_offset)}><span><b>第 {item.day_offset} 天</b><strong>{item.final_title}</strong></span><small>{item.overdue_days ? `已逾期 ${item.overdue_days} 天` : '今天到期'}</small><ChevronRight size={16} /></button>)}</section>}
      {selectedId && <form className="snapshot-form" onSubmit={saveSnapshot}>
        <div className="panel-title"><span>录入第 {dayOffset} 天数据</span><button type="button" className="ghost" onClick={() => { setSelectedId(''); setPendingOcr(null) }}>关闭</button></div>
        <div className="day-tabs">{([1, 3, 7] as const).map((day) => <button type="button" className={dayOffset === day ? 'active' : ''} key={day} onClick={() => selectSnapshotDay(day)}>第 {day} 天</button>)}</div>
        <section className="analytics-ocr-box">
          <div><strong>数据后台截图本地 OCR</strong><small>不读取账号后台、Cookie 或私人接口</small></div>
          <p>截图只在本机识别。识别文字和指标必须人工核对后才保存；确认后截图长期保留，可随时手动永久删除。</p>
          {!pendingOcr && <label className="analytics-ocr-file">上传 PNG/JPEG 截图<input aria-label="上传数据后台截图" type="file" accept="image/png,image/jpeg" disabled={busy} onChange={(e) => uploadAnalyticsScreenshot(e.target.files?.[0])} /></label>}
          {pendingOcr && <div className="analytics-ocr-review"><img src={`${API}/ocr/runs/${pendingOcr.id}/image`} alt="待确认的数据后台截图" /><label>OCR 文字（请核对并修正）<textarea required maxLength={20000} value={ocrText} onChange={(e) => setOcrText(e.target.value)} /></label><small>已尝试提取 {Object.keys(pendingOcr.engine_metadata?.parsed_metrics || {}).length} 项指标；下面每个数字仍需人工核对。</small></div>}
        </section>
        <div className="metric-inputs">{metricFields.map(([key, label]) => <label key={key}>{label}<input type="number" min="0" step={key.includes('rate') || key.includes('ratio') ? '0.01' : '1'} value={metrics[key] || ''} onChange={(e) => setMetrics({ ...metrics, [key]: e.target.value })} /></label>)}</div>
        <label>备注（可选）<textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <label className="confirm-line"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />我已逐项核对，并确认这些数字来自真实数据</label>
        <button className="primary" disabled={!confirmed || !Object.values(metrics).some((value) => value !== '') || busy || (!!pendingOcr && !ocrText.trim())}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}{pendingOcr ? '确认 OCR 并保存独立快照' : '保存独立快照'}</button>
      </form>}
      {ocrRuns.some((item) => item.purpose === 'analytics' && item.status === 'confirmed' && !item.deleted_at) && <section className="retained-screenshots"><div className="panel-title"><span>已保留的数据后台截图</span><small>仅本地 · 可永久删除</small></div><div>{ocrRuns.filter((item) => item.purpose === 'analytics' && item.status === 'confirmed' && !item.deleted_at).map((run) => <article key={run.id}><img src={`${API}/ocr/runs/${run.id}/image`} alt="已确认的数据后台截图" /><span>第 {run.engine_metadata?.day_offset} 天<br /><small>{new Date(run.created_at).toLocaleString('zh-CN')}</small></span><button className="ghost" disabled={busy} onClick={() => deleteAnalyticsScreenshot(run)}><Trash2 size={13} />永久删除原图</button></article>)}</div></section>}
      <section className="analytics-ai-panel">
        <div className="panel-title"><span>AI 单篇 / 周度 / 月度复盘</span><small>只读已确认快照</small></div>
        <p className="analytics-ai-boundary"><ShieldCheck size={15} />模型只分析你已确认的数字，不读取账号后台。建议默认不会改风格档案；只有你逐条选择并再次确认的建议，才会作为最近 3 条“可逆小实验”进入后续创作，每篇最多采用一条。</p>
        <div className="report-type-tabs">{([['single', '单篇'], ['weekly', '周报'], ['monthly', '月报']] as const).map(([value, label]) => <button className={reportType === value ? 'active' : ''} key={value} onClick={() => setReportType(value)}>{label}</button>)}</div>
        <div className="report-generator">
          {reportType === 'single' ? <label>选择已发布文章<select aria-label="选择单篇复盘文章" value={reportPublicationId} onChange={(e) => setReportPublicationId(e.target.value)}><option value="">请选择</option>{publications.map((item) => <option key={item.id} value={item.id}>{item.final_title}（{item.snapshots.length} 个快照）</option>)}</select></label> : <><label>开始日期<input aria-label="复盘开始日期" type="date" value={reportStart} onChange={(e) => setReportStart(e.target.value)} /></label><label>结束日期<input aria-label="复盘结束日期" type="date" value={reportEnd} onChange={(e) => setReportEnd(e.target.value)} /></label></>}
          <button className="primary" disabled={busy || (reportType === 'single' && !reportPublicationId)} onClick={generateAnalyticsReport}>{busy ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}生成{reportType === 'single' ? '单篇复盘' : reportType === 'weekly' ? '周报' : '月报'}</button>
        </div>
        <div className="report-history">
          {reports.length ? reports.map((report) => <article className="report-card" key={report.id}>
            <header><div><b>{report.report_type === 'single' ? '单篇复盘' : report.report_type === 'weekly' ? '周度复盘' : '月度复盘'}</b><small>{new Date(report.created_at).toLocaleString('zh-CN')} · {report.payload.sample_size || 0} 篇样本 · {report.input_snapshot_ids.length} 个快照</small></div><span className={`report-status ${report.status}`}>{report.status === 'generated' ? '待确认' : report.status === 'confirmed' ? '已确认建议' : report.status === 'dismissed' ? '已忽略' : report.status === 'failed' ? '生成失败' : '生成中'}</span></header>
            {report.error_summary ? <p className="report-error">{report.error_summary}</p> : <>
              <p>{report.payload.period_summary}</p>
              <div className="report-observations">{report.payload.observations?.map((item, index) => <div key={`${report.id}-observation-${index}`}><b>{item.label} · {item.confidence}置信</b><p>{item.finding}</p><small>{item.caveat} · 证据 {item.snapshot_ids.length} 个快照</small></div>)}</div>
              <div className="identity-guard"><b>必须保留</b>{report.payload.preserve_identity?.map((item) => <span key={item}>{item}</span>)}</div>
              {!!report.payload.suggestions?.length && <div className="report-suggestions"><b>可逆小实验</b>{report.payload.suggestions.map((suggestion) => <label key={suggestion.suggestion_id}><input type="checkbox" disabled={report.status !== 'generated'} checked={report.status === 'confirmed' ? report.confirmed_suggestion_ids.includes(suggestion.suggestion_id) : (reportSelections[report.id] || []).includes(suggestion.suggestion_id)} onChange={() => toggleReportSuggestion(report.id, suggestion.suggestion_id)} /><span><strong>{suggestion.applies_to} · {suggestion.experiment}</strong><small>{suggestion.rationale} · {suggestion.confidence}置信 · {suggestion.evidence_snapshot_ids.length} 个证据快照</small></span></label>)}</div>}
              {report.status === 'generated' && <><label className="confirm-line"><input type="checkbox" checked={reportConfirmed[report.id] || false} onChange={(e) => setReportConfirmed({ ...reportConfirmed, [report.id]: e.target.checked })} />我确认只把选中建议作为可选实验，不把它变成固定流量模板</label><div className="report-actions"><button className="ghost" disabled={busy} onClick={() => dismissAnalyticsReport(report.id)}>忽略并保留历史</button><button className="primary" disabled={busy || !(reportSelections[report.id] || []).length || !reportConfirmed[report.id]} onClick={() => confirmAnalyticsReport(report.id)}><Check size={14} />确认选中建议</button></div></>}
              {report.status === 'confirmed' && <p className="report-confirmed-note"><Check size={14} />已确认 {report.confirmed_suggestion_ids.length} 条；只作为可选实验进入创作记忆，不覆盖风格档案。</p>}
              {report.status === 'dismissed' && <p className="muted">报告已保留，建议没有进入创作记忆。</p>}
              <details><summary>样本限制与结论</summary><ul>{report.payload.limitations?.map((item) => <li key={item}>{item}</li>)}</ul><p>{report.payload.conclusion}</p></details>
            </>}
          </article>) : <div className="empty-note"><Sparkles size={22} /><p>录入真实快照后，可生成单篇、7 天周报或最多 31 天月报。所有历史报告都会保留。</p></div>}
        </div>
      </section>
      <section className="comment-assistant-panel">
        <div className="panel-title"><span>评论回复助手</span><small>只建议 · 不自动发送</small></div>
        <p className="comment-boundary"><ShieldCheck size={15} />可一次粘贴多条评论，或上传评论截图在本机 OCR。截图确认/放弃后永久删除。生成回复时只会在你主动勾选同意后，把这一条已确认评论发送给 DeepSeek；应用没有登录、评论或发送接口。</p>
        <label>选择已发布文章<select aria-label="选择评论所属文章" value={commentPublicationId} onChange={(e) => { setCommentPublicationId(e.target.value); setCommentText(''); setPendingCommentOcr(null); setCommentsConfirmed(false) }}><option value="">请选择</option>{publications.map((item) => <option key={item.id} value={item.id}>{item.final_title}</option>)}</select></label>
        {commentPublicationId && <div className="comment-intake">
          <div className="comment-intake-toolbar"><label className="analytics-ocr-file">上传评论截图<input aria-label="上传评论截图" type="file" accept="image/png,image/jpeg" disabled={busy || !!pendingCommentOcr} onChange={(e) => uploadCommentScreenshot(e.target.files?.[0])} /></label><small>{pendingCommentOcr ? '截图待核对，确认保存后原图会永久删除。' : '也可直接在下方粘贴；每行一条。'}</small></div>
          {pendingCommentOcr && <div className="comment-ocr-preview"><img src={`${API}/ocr/runs/${pendingCommentOcr.id}/image`} alt="待确认的评论截图" /><span>Windows 本地 OCR · 已建议拆分 {parseCommentBatch(commentText).length} 条</span></div>}
          <label>{pendingCommentOcr ? 'OCR 评论文字（请逐行修正）' : '粘贴评论（每行一条，可写“昵称：内容”）'}<textarea aria-label="评论文字" placeholder={'小雨：看到这里很想哭\n谢谢你写出来'} maxLength={20000} value={commentText} onChange={(e) => setCommentText(e.target.value)} /></label>
          <div className="comment-intake-summary">将保存 {parseCommentBatch(commentText).length} 条人工核对评论；时间标签空行会被忽略。</div>
          <label className="confirm-line"><input type="checkbox" checked={commentsConfirmed} onChange={(e) => setCommentsConfirmed(e.target.checked)} />我已逐条核对评论文字和昵称，确认保存到本机</label>
          <div className="comment-intake-actions">{pendingCommentOcr && <button className="ghost" disabled={busy} onClick={discardCommentScreenshot}>放弃并删除截图</button>}<button className="primary" disabled={busy || !commentsConfirmed || !parseCommentBatch(commentText).length} onClick={saveCommentBatch}>{busy ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}{pendingCommentOcr ? '确认评论并删除截图' : '保存多条评论'}</button></div>
        </div>}
        <div className="comment-list">
          {comments.length ? comments.map((comment) => { const latest = [...comment.reply_suggestions].reverse().find((item) => item.status === 'generated'); const failed = [...comment.reply_suggestions].reverse().find((item) => item.status === 'failed'); const replyValue = replyDrafts[comment.id] ?? latest?.payload.reply_text ?? ''; return <article key={comment.id}>
            <header><div><b>{comment.author_label || '未记录昵称'}</b><small>{comment.source_type === 'screenshot' ? '截图 OCR 后人工确认' : '人工粘贴'} · {new Date(comment.created_at).toLocaleString('zh-CN')}</small></div><button className="ghost" disabled={busy} onClick={() => removeSavedComment(comment.id)}><Trash2 size={13} />删除本地记录</button></header>
            <p>{comment.comment_text}</p>
            {latest ? <div className="reply-suggestion"><div><b>{latest.payload.tone}回复建议</b><small>{latest.payload.safety_note}</small></div><textarea aria-label={`回复建议 ${comment.author_label || '未记录昵称'}`} value={replyValue} maxLength={300} onChange={(e) => setReplyDrafts({ ...replyDrafts, [comment.id]: e.target.value })} /><button className="primary" onClick={() => copyCommentReply(comment.id, latest.payload.reply_text || '')}>{copiedReplyId === comment.id ? <Check size={14} /> : <FileText size={14} />}{copiedReplyId === comment.id ? '已复制，请手动发送' : '复制回复，手动发送'}</button></div> : <div className="reply-consent">
              {failed && <p className="report-error">上次生成失败：{failed.error_summary}</p>}
              <label className="confirm-line"><input type="checkbox" checked={replyConsent[comment.id] || false} onChange={(e) => setReplyConsent({ ...replyConsent, [comment.id]: e.target.checked })} />我确认只把这一条评论发送给 DeepSeek 生成建议</label>
              <button className="ghost" disabled={busy || !replyConsent[comment.id]} onClick={() => generateCommentReply(comment.id)}>{busy ? <LoaderCircle className="spin" size={14} /> : <Sparkles size={14} />}生成一条回复建议</button>
            </div>}
          </article> }) : <div className="empty-note"><FileText size={22} /><p>还没有已确认评论。粘贴或本地 OCR 后会显示在这里；应用不会自动发送任何回复。</p></div>}
        </div>
      </section>
      <section className="publication-list"><div className="panel-title"><span>已发布内容</span><small>第 1、3、7 天独立保存</small></div>{publications.length ? publications.map((item) => { const maxViews = Math.max(1, ...item.snapshots.map((snapshot) => snapshot.metrics.views || snapshot.metrics.impressions || 0)); return <article className="publication-card" key={item.id}><header><div><small>{new Date(item.published_at).toLocaleString('zh-CN')}</small><h2>{item.final_title}</h2><p>{item.final_tags.map((tag) => `#${tag}`).join(' ') || '没有标签记录'}</p></div><a href={item.note_url} target="_blank" rel="noreferrer">查看公开笔记 <ExternalLink size={14} /></a></header><div className="snapshot-curve">{item.snapshots.length ? item.snapshots.map((snapshot) => { const value = snapshot.metrics.views || snapshot.metrics.impressions || 0; return <div className="curve-column" key={snapshot.id}><div className="curve-bar"><i style={{ height: `${Math.max(6, value / maxViews * 100)}%` }} /></div><strong>{value}</strong><small>第 {snapshot.day_offset} 天</small></div> }) : <p className="muted">尚未录入数据快照</p>}</div>{item.snapshots.map((snapshot) => <div className="snapshot-row" key={snapshot.id}><b>第 {snapshot.day_offset} 天</b><span>赞 {snapshot.metrics.likes ?? '-'} · 藏 {snapshot.metrics.favorites ?? '-'} · 评 {snapshot.metrics.comments ?? '-'}</span><small>点赞率 {percent(snapshot.calculated_rates.like_rate)} · 收藏率 {percent(snapshot.calculated_rates.favorite_rate)}</small></div>)}<button className="ghost" onClick={() => beginSnapshot(item.id)}>录入或更新数据</button></article> }) : <div className="empty-note"><BarChart3 size={24} /><p>还没有发布记录。文章通过审核并由你手动发布后，可以在文章页粘贴笔记链接。</p></div>}</section>
    </main>
  )
}

import { useEffect, useState } from 'react'
import { ArrowLeft, Check, ChevronRight, FileText, LoaderCircle, ShieldCheck, Sparkles } from 'lucide-react'
import type { Content } from '../types'
import { request } from '../lib/api'
import { latest } from '../lib/content'
import { ActionButton } from '../components/ActionButton'
import { RichEditor } from '../components/RichEditor'
import { MemoryDisclosure, OriginalityDisclosure, CitationDisclosure, ManualOriginalityPanel } from '../components/QualityDetails'
import { CoverStudio } from '../components/CoverStudio'

export function Composer({ content, refresh, goHome, goSettings, writingConfigured = true, goWritingSettings }: {
  content: Content; refresh: () => Promise<void>; goHome: () => void; goSettings?: () => void
  writingConfigured?: boolean; goWritingSettings?: () => void
}) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [customDetail, setCustomDetail] = useState('')
  const [versions, setVersions] = useState<any[]>([])
  const [exportPath, setExportPath] = useState('')
  const [publishUrl, setPublishUrl] = useState('')
  const [publishedAt, setPublishedAt] = useState('')
  const [publishConfirmed, setPublishConfirmed] = useState(false)
  const plans = latest(content, 'NarrativePlanSet')?.payload.plans || []
  const detail = latest(content, 'DetailQuestion')?.payload
  const draft = latest(content, 'EssayDraft')?.payload
  const styleReview = latest(content, 'StyleReview')?.payload
  const aiToneReview = latest(content, 'AIToneReview')?.payload
  const originality = latest(content, 'OriginalityReport')?.payload
  const citationReport = latest(content, 'CitationVerificationReport')?.payload
  const citationBlocks = (citationReport?.items || []).some((item: any) => item.status !== 'verified')
  const riskReport = latest(content, 'RiskReport')?.payload
  const memoryReport = latest(content, 'GenerationMemoryReport')?.payload

  useEffect(() => { request<any[]>(`/contents/${content.id}/versions`).then(setVersions).catch((cause) => setError((cause as Error).message)) }, [content.id, content.current_step, content.updated_at])
  const activeVersion = versions[0]

  async function action(name: string, path: string, body?: any) {
    if (busy) return
    setBusy(name); setError('')
    try { await request(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }); await refresh() }
    catch (e) { setError((e as Error).message) }
    finally { setBusy('') }
  }

  async function choosePlan(planId: string) {
    if (busy) return
    setBusy(planId); setError('')
    try {
      await request(`/contents/${content.id}/workflow/select-plan`, { method: 'POST', body: JSON.stringify({ plan_id: planId }) })
      await request(`/contents/${content.id}/workflow/detail-question`, { method: 'POST' })
      await refresh()
    } catch (e) { setError((e as Error).message); await refresh().catch(() => undefined) } finally { setBusy('') }
  }

  async function chooseDetail(value: string, mode: 'real' | 'fictional') {
    if (busy) return
    setBusy(value); setError('')
    try {
      await request(`/contents/${content.id}/workflow/select-detail`, { method: 'POST', body: JSON.stringify({ mode, detail: value }) })
      await request(`/contents/${content.id}/workflow/draft`, { method: 'POST' })
      await refresh()
    } catch (e) { setError((e as Error).message); await refresh().catch(() => undefined) } finally { setBusy('') }
  }

  async function makeExport() {
    setBusy('export'); setError(''); setExportPath('')
    try {
      if (!latest(content, 'CoverPNG')) await request(`/contents/${content.id}/cover/render`, { method: 'POST', body: JSON.stringify({ template: 'whitespace', copy: draft?.cover_copy }) })
      const result = await request<{ folder: string }>(`/contents/${content.id}/export`, { method: 'POST' })
      setExportPath(result.folder)
      await refresh()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function recordPublished(event: React.FormEvent) {
    event.preventDefault(); setBusy('publish'); setError('')
    try {
      await request(`/contents/${content.id}/publish`, {
        method: 'POST',
        body: JSON.stringify({ note_url: publishUrl, published_at: publishedAt ? new Date(publishedAt).toISOString() : null, confirm: publishConfirmed }),
      })
      setPublishUrl(''); setPublishConfirmed(false); await refresh()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  return (
    <main className="page composer">
      <button className="back" onClick={goHome}><ArrowLeft size={15} />返回工作台</button>
      <header className="composer-head"><div><h1>{content.title || content.theme}</h1><p>{content.emotion}{content.extra_requirements ? ` · ${content.extra_requirements}` : ''}</p></div></header>
      <ol className="workflow-steps" aria-label="创作步骤">{['生成方案', '选择入口', '补充细节', '编辑与检查', '导出与记录'].map((label, index) => { const stage = content.status !== 'draft' ? 4 : draft ? 3 : content.selected_plan_id ? 2 : plans.length ? 1 : 0; return <li key={label} aria-current={index === stage ? 'step' : undefined} className={index < stage ? 'done' : index === stage ? 'current' : ''}><span>{index + 1}</span>{label}</li> })}</ol>
      {!writingConfigured && content.status === 'draft' && <div className="desk-connection">
        <p>这篇稿件已保存在内容库。生成方案、初稿或质量报告前，请连接写作服务。</p>
        <button className="ghost" onClick={goWritingSettings}>配置 API Key <ChevronRight size={16} /></button>
      </div>}
      {error && <div className="error-banner">{error}</div>}
      {content.selected_plan_id && !detail && !draft && <section className="focus-card recovery-card"><div><h2>方案已保存，继续补充细节</h2><p>上一步尚未完成。点击后只重新请求细节问题，不会重新选择方案。</p><ActionButton busy={busy === 'detail-retry'} busyLabel="正在生成问题…" disabled={!!busy} onClick={() => action('detail-retry', `/contents/${content.id}/workflow/detail-question`)}>重新生成细节问题</ActionButton></div></section>}
      {content.selected_detail && !draft && <section className="focus-card recovery-card"><div><h2>细节已确认，继续写出初稿</h2><p>已保存你的选择，可以从这里重新请求初稿。</p><ActionButton busy={busy === 'draft-retry'} busyLabel="正在写出初稿…" disabled={!!busy} onClick={() => action('draft-retry', `/contents/${content.id}/workflow/draft`)}>重新生成初稿</ActionButton></div></section>}
      {memoryReport && <details className="writing-context"><summary>写作依据与历史避重（展开查看）</summary><MemoryDisclosure report={memoryReport} /></details>}
      {originality && <OriginalityDisclosure report={originality} />}
      {citationReport && <CitationDisclosure report={citationReport} />}
      {citationBlocks && <div className="error-banner">存在未核实或仅部分核实的文化引用，提交时会被阻止。请按核验建议改写后重新运行质量门禁。</div>}
      {!plans.length && !content.selected_plan_id && <section className="focus-card"><div><h2>先看三个不同的入口</h2><p>先确定切口，再进入写作。系统会从私人关系、女性经验和文化联想等不同思想切口给出方案。</p><ActionButton busy={busy === 'plans'} busyLabel="正在构思方案…" icon={<Sparkles size={17} />} disabled={!!busy} onClick={() => action('plans', `/contents/${content.id}/workflow/plans`)}>生成三个方案</ActionButton></div></section>}
      {plans.length > 0 && !content.selected_plan_id && <section><h2 className="workflow-section-title">选择思想入口</h2><div className="plans-grid">{plans.map((plan: any, index: number) => <article className="plan-card" key={plan.plan_id}><span>0{index + 1}</span><small>{plan.angle}</small><h3>{plan.title}</h3><blockquote>{plan.opening_example}</blockquote><p>{plan.core_view}</p><div className="plan-meta"><b>场景</b>{plan.scenes.join(' · ')}</div><button onClick={() => choosePlan(plan.plan_id)} disabled={!!busy} aria-busy={busy === plan.plan_id}>{busy === plan.plan_id ? <><LoaderCircle className="spin" size={16} />正在准备细节…</> : <>选择这个方案 <ChevronRight size={15} /></>}</button></article>)}</div></section>}
      {content.selected_plan_id && detail && !content.selected_detail && <section className="detail-card"><h2>{detail.question}</h2><p>你可以写真实细节，也可以选一个安全的虚构细节。参考内容不会进入长期风格库。</p><div className="detail-options">{detail.virtual_details.map((item: string) => <button key={item} disabled={!!busy} aria-busy={busy === item} onClick={() => chooseDetail(item, 'fictional')}>{busy === item ? <><LoaderCircle className="spin" size={16} />正在写出初稿…</> : <>{item}<ChevronRight size={15} /></>}</button>)}</div><div className="custom-detail"><textarea value={customDetail} onChange={(e) => setCustomDetail(e.target.value)} placeholder="或者写下你自己的真实细节……" /><ActionButton busy={!!busy && busy === customDetail} busyLabel="正在写出初稿…" disabled={!customDetail || !!busy} onClick={() => chooseDetail(customDetail, 'real')}>确认这个细节</ActionButton></div></section>}
      {(content.current_step === 'human_edit' || content.current_step === 'review_submission') && draft && <><section className="draft-section"><div className="draft-aside"><h2>初稿已经保存</h2><p>原始生成稿不会被覆盖。每次保存都会形成新的版本。</p><dl><dt>备用标题</dt><dd>{draft.alternate_titles?.join(' / ')}</dd><dt>封面短句</dt><dd>{draft.cover_copy}</dd><dt>置顶评论</dt><dd>{draft.pinned_comment}</dd><dt>发布时间</dt><dd>{draft.recommended_publish_time} · {draft.recommendation_confidence}可信度</dd></dl><div className="memory-note"><ShieldCheck size={16} /><span>本次未注入历史全文，也没有自动发布权限。</span></div>{!styleReview && content.status === 'draft' && <ActionButton className="quality-button" busy={busy === 'quality'} busyLabel="正在检查文稿…" icon={<ShieldCheck size={16} />} disabled={!!busy} onClick={() => action('quality', `/contents/${content.id}/quality`)}>运行五项质量门禁</ActionButton>}{styleReview && <div className="quality-summary"><div className="section-kicker">质量门禁</div><p><b>风格</b>{styleReview.summary}</p><p><b>AI 味</b>{aiToneReview?.summary}</p><p><b>原创度</b>{originality?.passes_gate ? '当前检测范围通过' : '需要重构'}<small>{originality?.external_check_status === 'completed' ? '已检查 Tavily 可访问的公开网页与公开小红书页面' : originality?.external_check_status === 'failed' ? '公网检查失败，已停止且未自动重试' : '公网检查不可用；界面不会宣称全网原创'}</small></p><p><b>文化引用</b>{citationReport?.check_status === 'not_needed' ? '本稿无需核验' : citationReport?.check_status === 'completed' ? '已完成有限公开来源核验' : '存在未核实引用，请查看上方说明'}</p><p><b>风险</b>{riskReport?.blocks_submission ? '存在阻止项' : '无阻止提交项'}</p>{content.status === 'draft' && <ActionButton busy={busy === 'submit'} busyLabel="正在提交…" disabled={!originality?.passes_gate || riskReport?.blocks_submission || !!busy} onClick={() => action('submit', `/contents/${content.id}/submit-review`, { confirm: true })}>人工确认提交审核</ActionButton>}{content.status === 'pending_review' && <><div className="submitted"><Check size={15} />已进入待审核</div><ActionButton className="export-button" busy={busy === 'export'} busyLabel="正在整理发布包…" success={!!exportPath} successLabel="发布包已生成" icon={<FileText size={15} />} disabled={!!busy} onClick={makeExport}>生成封面与发布包</ActionButton>{exportPath && <div className="export-path">已导出到<br />{exportPath}</div>}</>}</div>}</div><RichEditor title={activeVersion?.title || draft.title} html={activeVersion?.body_html || draft.body.split('\n').map((p: string) => `<p>${p}</p>`).join('')} onSave={async (title, body_html, body_text) => { await request(`/contents/${content.id}/draft`, { method: 'PATCH', body: JSON.stringify({ title, body_html, body_text }) }); await refresh() }} /></section><ManualOriginalityPanel contentId={content.id} onSaved={refresh} onRerun={() => { void action('quality', `/contents/${content.id}/quality`) }} busy={!!busy} /></>}
      {(content.status === 'draft' || content.status === 'pending_review') && draft && <CoverStudio content={content} suggestedCopy={draft.cover_copy || content.title || content.theme} onChanged={refresh} onSettings={goSettings} />}
      {content.status === 'pending_review' && <form className="publication-form" onSubmit={recordPublished}><h2>粘贴公开笔记链接</h2><p>这里不会登录或控制小红书。请先由你本人完成发布，再把公开链接和实际发布时间记录进来。</p><label>小红书笔记链接<input type="url" required value={publishUrl} onChange={(e) => setPublishUrl(e.target.value)} placeholder="https://www.xiaohongshu.com/explore/..." /></label><label>实际发布时间（留空则使用当前时间）<input type="datetime-local" value={publishedAt} onChange={(e) => setPublishedAt(e.target.value)} /></label><label className="confirm-line"><input type="checkbox" checked={publishConfirmed} onChange={(e) => setPublishConfirmed(e.target.checked)} />我确认这篇文章已经由我手动发布</label><ActionButton busy={busy === 'publish'} busyLabel="正在记录…" icon={<Check size={16} />} disabled={!publishUrl || !publishConfirmed || !!busy}>标记为已发布</ActionButton></form>}
      {content.status === 'published' && <section className="published-confirmation"><Check size={22} /><div><h2>已记录为手动发布</h2><p>最终版本已经冻结到发布记录。请前往“复盘”录入第 1、3、7 天真实数据。</p></div></section>}
    </main>
  )
}

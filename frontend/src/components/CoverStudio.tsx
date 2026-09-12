import { useCallback, useEffect, useRef, useState } from 'react'
import { ImagePlus, LoaderCircle, Trash2 } from 'lucide-react'
import type { Content, CoverState } from '../types'
import { request, uploadRequest } from '../lib/api'
import { ImageGenerationPanel } from './ImageGenerationPanel'

export function CoverStudio({ content, suggestedCopy, onChanged, onSettings }: { content: Content; suggestedCopy: string; onChanged: () => Promise<void>; onSettings?: () => void }) {
  const [state, setState] = useState<CoverState | null>(null)
  const [template, setTemplate] = useState<'whitespace' | 'magazine' | 'subtitle'>('whitespace')
  const [copy, setCopy] = useState(suggestedCopy.slice(0, 18))
  const [focusX, setFocusX] = useState(0.5)
  const [focusY, setFocusY] = useState(0.5)
  const [zoom, setZoom] = useState(1)
  const [width, setWidth] = useState(900)
  const [height, setHeight] = useState(1200)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const previousUpload = useRef<string | null | undefined>(undefined)
  const previousRendered = useRef<string | undefined>(undefined)
  const loadVersion = useRef(0)

  const loadCover = useCallback(async () => {
    const current = ++loadVersion.current
    const next = await request<CoverState>(`/contents/${content.id}/cover`)
    if (current !== loadVersion.current) return
    setState(next)
    if (next.rendered && previousRendered.current !== next.rendered.id) {
      setTemplate(next.rendered.template || 'whitespace'); setCopy(next.rendered.copy || suggestedCopy.slice(0, 18))
      setFocusX(next.rendered.focus_x ?? 0.5); setFocusY(next.rendered.focus_y ?? 0.5); setZoom(next.rendered.zoom ?? 1)
      setWidth(next.rendered.width || 900); setHeight(next.rendered.height || 1200)
    } else if (!next.rendered && previousUpload.current !== next.upload?.id) {
      setFocusX(0.5); setFocusY(0.5); setZoom(1)
    }
    previousUpload.current = next.upload?.id
    previousRendered.current = next.rendered?.id
  }, [content.id, suggestedCopy])
  useEffect(() => { void Promise.resolve().then(loadCover).catch((e) => setError((e as Error).message)) }, [loadCover])
  useEffect(() => {
    if (!state?.image_generation_busy) return
    const timer = window.setInterval(() => { void loadCover().catch((cause) => setError((cause as Error).message)) }, 3000)
    return () => window.clearInterval(timer)
  }, [state?.image_generation_busy, loadCover])

  async function reloadImages() {
    await loadCover()
    await onChanged()
  }

  async function upload(file?: File) {
    if (!file) return
    setBusy('upload'); setError('')
    const form = new FormData(); form.append('file', file)
    try { await uploadRequest(`/contents/${content.id}/cover/upload`, form); await loadCover(); await onChanged() }
    catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function renderPreview() {
    setBusy('render'); setError('')
    try {
      await request(`/contents/${content.id}/cover/render`, { method: 'POST', body: JSON.stringify({ template, copy, focus_x: focusX, focus_y: focusY, zoom, output_width: width, output_height: height }) })
      await loadCover(); await onChanged()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function removeCover() {
    if (!window.confirm('删除封面原图和已生成预览？已经导出的历史发布包不会被修改。')) return
    setBusy('delete'); setError('')
    try {
      await request(`/contents/${content.id}/cover`, { method: 'DELETE', body: JSON.stringify({ confirm: true }) })
      setState((value) => value ? { ...value, upload: null, rendered: null } : value); await onChanged()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  return <section className="cover-studio">
    <div className="panel-title"><span>封面与效果预览</span><small>原图本地保留 · 导出生成新 PNG</small></div>
    <ImageGenerationPanel contentId={content.id} state={state} busy={busy} setBusy={setBusy} reload={reloadImages} onSettings={onSettings}
      onGenerated={(candidate) => setState((value) => value ? { ...value, candidates: [candidate, ...(value.candidates || [])] } : value)} />
    <div className="cover-studio-grid">
      <div className="cover-preview">{state?.rendered ? <img src={state.rendered.preview_url} alt="当前封面预览" /> : state?.upload ? <img src={state.upload.preview_url} alt="封面原图预览" /> : <div><ImagePlus size={30} /><span>上传一张图片，或直接使用纯文字模板</span></div>}{state?.rendered && <small>{state.rendered.width} × {state.rendered.height} · PNG</small>}</div>
      <div className="cover-controls">
        {error && <div className="error-banner">{error}</div>}
        <div className="cover-upload-row"><label className="cover-file">{state?.upload ? '替换原图' : '上传封面图片'}<input aria-label="上传封面图片" type="file" accept="image/png,image/jpeg,image/webp" disabled={!!busy} onChange={(e) => upload(e.target.files?.[0])} /></label>{(state?.upload || state?.rendered) && <button className="ghost" type="button" disabled={!!busy} onClick={removeCover}><Trash2 size={14} />删除</button>}</div>
        {busy === 'upload' && <span className="cover-note"><LoaderCircle className="spin" size={14} />正在校验并保存原图……</span>}
        {state?.upload && <p className={`cover-quality ${state.upload.quality_status}`}>{state.upload.original_name} · {state.upload.width}×{state.upload.height} · {Math.round((state.upload.size_bytes || 0) / 1024)}KB<br />{state.upload.quality_note}（清晰度分数 {state.upload.sharpness_score}）</p>}
        <label>封面文案（不超过 18 个汉字）<input maxLength={18} value={copy} onChange={(e) => setCopy(e.target.value)} /></label>
        <div className="cover-templates"><button type="button" aria-pressed={template === 'whitespace'} onClick={() => setTemplate('whitespace')}>纯文字留白型</button><button type="button" aria-pressed={template === 'magazine'} onClick={() => setTemplate('magazine')}>杂志标题型</button><button type="button" aria-pressed={template === 'subtitle'} onClick={() => setTemplate('subtitle')}>电影字幕型</button></div>
        {state?.upload && <div className="crop-controls"><label>横向焦点 <input type="range" min="0" max="1" step="0.01" value={focusX} onChange={(e) => setFocusX(Number(e.target.value))} /></label><label>纵向焦点 <input type="range" min="0" max="1" step="0.01" value={focusY} onChange={(e) => setFocusY(Number(e.target.value))} /></label><label>裁剪缩放 {zoom.toFixed(1)}× <input type="range" min="1" max="3" step="0.1" value={zoom} onChange={(e) => setZoom(Number(e.target.value))} /></label></div>}
        <div className="cover-size"><label>宽度<input type="number" min="450" max="2160" value={width} onChange={(e) => setWidth(Number(e.target.value))} /></label><span>×</span><label>高度<input type="number" min="600" max="2880" value={height} onChange={(e) => setHeight(Number(e.target.value))} /></label><button type="button" className="ghost" onClick={() => { setWidth(900); setHeight(1200) }}>恢复 3:4</button></div>
        <button type="button" className="primary" disabled={!copy.trim() || !!busy} onClick={renderPreview}>{busy === 'render' ? <LoaderCircle className="spin" size={15} /> : <ImagePlus size={15} />}生成真实 PNG 预览</button>
        <p className="cover-note">裁剪、排版和 PNG 预览均在本地完成，不产生模型调用费用。</p>
      </div>
    </div>
  </section>
}

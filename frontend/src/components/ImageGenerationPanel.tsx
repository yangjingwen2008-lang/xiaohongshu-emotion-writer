import { useRef, useState } from 'react'
import { Download, LoaderCircle, Sparkles, Trash2 } from 'lucide-react'
import type { CoverCandidate, CoverState } from '../types'
import { request } from '../lib/api'

type Props = {
  contentId: string; state: CoverState | null; busy: string
  setBusy: (value: string) => void; reload: () => Promise<void>
  onGenerated: (candidate: CoverCandidate) => void; onSettings?: () => void
}

export function ImageGenerationPanel({ contentId, state, busy, setBusy, reload, onGenerated, onSettings }: Props) {
  const [prompt, setPrompt] = useState('')
  const [sizeMode, setSizeMode] = useState('default')
  const [size, setSize] = useState('1024x1536')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const pending = useRef(false)
  const waiting = busy === 'generate' || !!state?.image_generation_busy
  const disabled = !!busy || !!state?.image_generation_busy
  const root = `/contents/${contentId}/cover`

  async function generate(event: React.FormEvent) {
    event.preventDefault()
    if (pending.current || disabled || !prompt.trim() || !state?.auto_image_generation) return
    pending.current = true; setBusy('generate'); setError(''); setMessage('')
    try {
      const result = await request<CoverCandidate>(`${root}/generate`, { method: 'POST', body: JSON.stringify({ prompt: prompt.trim(), size: sizeMode === 'default' ? null : size }) })
      onGenerated(result)
      setMessage('图片已保存。预览后选择“用作封面”，再调整裁剪和文字。')
    } catch (cause) { setError(`${(cause as Error).message} 未自动重试。若连接中断，请重新载入查看结果，上游可能已计费。`) }
    finally {
      // Reload even after a lost response, without repeating the paid request.
      await reload().catch(() => setError('结果暂时无法刷新，请点击“重新载入图片”；不要重复提交生成。'))
      pending.current = false; setBusy('')
    }
  }

  async function candidateAction(id: string, action: 'use' | 'delete') {
    if (pending.current || disabled) return
    if (action === 'delete' && !window.confirm('删除这张候选图片？已选作封面的副本和历史发布包会保留。')) return
    pending.current = true; setBusy(`${action}:${id}`); setError(''); setMessage('')
    try {
      await request(`${root}/candidates/${id}${action === 'use' ? '/use' : ''}`, {
        method: action === 'use' ? 'POST' : 'DELETE', body: action === 'delete' ? JSON.stringify({ confirm: true }) : undefined,
      })
      setMessage(action === 'use' ? '已用作封面。请调整裁剪与文字，再生成 PNG 预览。' : '候选图片已删除。')
      await reload()
    } catch (cause) { setError((cause as Error).message) }
    finally { pending.current = false; setBusy('') }
  }

  return <div className="image-generation">
    <div className="panel-title"><span><Sparkles size={16} /> 描述生成图片</span><small>每次一张 · 先预览，再选用</small></div>
    {!state ? <p className="cover-note">正在读取图像配置……</p> : !state.auto_image_generation && <div className="image-empty"><p>配置图像模型后，可以把你描述的画面生成封面图片。</p>{onSettings && <button type="button" className="ghost" onClick={onSettings}>前往图像设置</button>}</div>}
    <form onSubmit={generate}>
      <label>画面描述<textarea rows={4} maxLength={4000} required value={prompt} disabled={disabled} onChange={(e) => setPrompt(e.target.value)} placeholder="例如：雨后的窗边，一杯咖啡，暖灰色调，胶片质感；上方留出标题空间，不添加文字。" /></label>
      <div className="image-size-row"><label>生成尺寸<select value={sizeMode} disabled={disabled} onChange={(e) => setSizeMode(e.target.value)}><option value="default">服务默认</option><option value="custom">自定义尺寸</option></select></label>{sizeMode === 'custom' && <label>宽 × 高<input aria-label="自定义生成尺寸" required pattern="[1-9][0-9]{1,4}x[1-9][0-9]{1,4}" value={size} disabled={disabled} onChange={(e) => setSize(e.target.value)} placeholder="1024x1536" /></label>}</div>
      {sizeMode === 'custom' && <p className="cover-note">填写模型支持的尺寸，例如 1024x1536。最终封面的比例和大小可在下方裁剪时调整。</p>}
      <button className="primary" disabled={!state?.auto_image_generation || !prompt.trim() || disabled}>{waiting ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}{waiting ? '正在生成图片……' : '生成图片'}</button>
      <p className="cover-note">点击后将向你配置的服务发送这段描述，可能产生费用。生成不会自动替换当前封面。</p>
    </form>
    {waiting && <p className="message" role="status">图片生成需要一些时间，请勿重复提交。离开后重新打开文章可查看已保存的结果。</p>}
    {error && <p className="error-banner" role="alert">{error}</p>}
    {message && <p className="message" role="status">{message}</p>}
    <div className="image-candidate-heading"><span>候选图片 · {state?.candidates?.length || 0}</span><button className="ghost" type="button" disabled={!!busy} onClick={() => { setError(''); void reload().catch((cause) => setError((cause as Error).message)) }}>重新载入图片</button></div>
    {!!state?.candidates?.length && <div className="image-candidates">{state.candidates.map((candidate) => <article className="image-candidate" key={candidate.id}>
      <a href={candidate.preview_url} target="_blank" rel="noreferrer" aria-label="查看生成图片大图"><img src={candidate.preview_url} alt={candidate.prompt} loading="lazy" /></a>
      <div className="image-candidate-body"><p>{candidate.prompt}</p><small>{candidate.model} · {candidate.width}×{candidate.height}<br />{new Date(candidate.created_at).toLocaleString('zh-CN')}</small><div className="image-candidate-actions">
        <button className="primary" type="button" disabled={disabled} onClick={() => void candidateAction(candidate.id, 'use')}>用作封面</button>
        <a className="ghost" href={candidate.download_url} download><Download size={14} />下载</a>
        <button className="ghost" type="button" aria-label="删除候选图片" disabled={disabled} onClick={() => void candidateAction(candidate.id, 'delete')}><Trash2 size={14} /></button>
      </div></div>
    </article>)}</div>}
  </div>
}

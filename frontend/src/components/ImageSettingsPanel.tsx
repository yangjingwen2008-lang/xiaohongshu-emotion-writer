import { useCallback, useEffect, useState } from 'react'
import { Check, LoaderCircle } from 'lucide-react'
import type { ImageSetup } from '../types'
import { request } from '../lib/api'

export function ImageSettingsPanel() {
  const [config, setConfig] = useState<ImageSetup | null>(null)
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setError('')
    try { setConfig(await request<ImageSetup>('/setup/image')) }
    catch (cause) { setError((cause as Error).message) }
  }, [])
  useEffect(() => { void Promise.resolve().then(load) }, [load])

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!config || busy) return
    setBusy(true); setMessage(''); setError('')
    try {
      const next = await request<ImageSetup>('/setup/image', { method: 'POST', body: JSON.stringify({
        enabled: config.enabled, base_url: config.base_url, model: config.model,
        timeout_seconds: config.timeout_seconds, api_key: key || null,
      }) })
      setConfig(next); setKey(''); setMessage('图像配置已保存。到文章的封面工作台输入描述即可生成图片。')
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  return <form id="image-settings" className="setup-card image-settings" onSubmit={save}>
    <div className="panel-title"><span>图像生成</span><small>描述一幅画面，让它成为封面</small></div>
    {error && <p className="error-banner" role="alert">{error}</p>}
    {config?.configuration_error && <p className="error-banner" role="alert">{config.configuration_error}</p>}
    {!config ? <button type="button" className="ghost" onClick={() => void load()}>重新读取图像配置</button> : <>
      <fieldset disabled={busy}>
        <label className="image-toggle"><input type="checkbox" checked={config.enabled} onChange={(e) => setConfig({ ...config, enabled: e.target.checked })} />启用图像生成</label>
        <label>图像 API Base URL<input type="url" required={config.enabled} maxLength={1000} value={config.base_url} onChange={(e) => setConfig({ ...config, base_url: e.target.value })} placeholder="https://服务地址/v1" /></label>
        <p className="form-note">填写服务文档中的 HTTPS 基础地址，通常以 /v1 结尾；无需添加 /images/generations。仅支持同步 Images 兼容接口。</p>
        <label>图像模型名称<input required={config.enabled} maxLength={120} value={config.model} onChange={(e) => setConfig({ ...config, model: e.target.value })} placeholder="填写服务支持的图像模型名称" /></label>
        <label>图像 API 密钥<input type="password" autoComplete="new-password" maxLength={4096} value={key} onChange={(e) => setKey(e.target.value)} placeholder={config.key_configured ? '已配置 · 留空保留原密钥' : '本地输入'} /></label>
        <label>生成超时（秒）<input type="number" min={30} max={600} required value={config.timeout_seconds} onChange={(e) => setConfig({ ...config, timeout_seconds: Number(e.target.value) })} /></label>
      </fieldset>
      <p className="form-note">密钥保存在本机。保存不会调用模型；每次点击“生成图片”才会发送画面描述，并可能由所选服务计费。更换服务地址时需重新填写密钥。</p>
      <button className="primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}保存图像配置</button>
    </>}
    {message && <p className="message" role="status">{message}</p>}
  </form>
}

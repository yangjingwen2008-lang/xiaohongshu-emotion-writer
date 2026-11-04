import { useState } from 'react'
import { ArrowRight, ShieldCheck } from 'lucide-react'
import { ActionButton } from './ActionButton'
import { request } from '../lib/api'
import type { SetupStatus } from '../types'

export function WritingConnection({ status, onSaved, onboarding = false }: {
  status: SetupStatus
  onSaved: () => void
  onboarding?: boolean
}) {
  const active = status.writing_provider ?? 'deepseek'
  const presets = status.writing_providers ?? [
    { id: 'deepseek', label: 'DeepSeek', model: status.deepseek_model, configured: status.deepseek_configured },
  ]
  const [provider, setProvider] = useState(active)
  const [key, setKey] = useState('')
  const [pending, setPending] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const preset = presets.find((item) => item.id === provider) ?? presets[0]

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending('save'); setMessage(''); setError('')
    try {
      await request('/setup/writing', { method: 'POST', body: JSON.stringify({ provider, api_key: key.trim() || null }) })
      setKey('')
      setMessage('写作服务已保存。')
      onSaved()
    } catch (cause) { setError((cause as Error).message) }
    finally { setPending('') }
  }

  async function test() {
    if (pending) return
    setPending('test'); setError(''); setMessage('')
    try {
      const result = await request<{ ok: boolean }>('/setup/test/writing', { method: 'POST' })
      if (!result.ok) throw new Error('服务已响应，但未通过连通性测试。')
      setMessage('连通性测试通过。')
    } catch (cause) { setError((cause as Error).message) }
    finally { setPending('') }
  }

  return <form className="writing-connection" onSubmit={save} aria-busy={!!pending}>
    <label>写作服务<select value={provider} disabled={!!pending} onChange={(event) => {
      setProvider(event.target.value); setKey(''); setError(''); setMessage('')
    }}>{presets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
    <label>API Key<input type="password" autoComplete="off" spellCheck={false} maxLength={512}
      disabled={!!pending} required={!preset.configured} value={key} onChange={(event) => { setKey(event.target.value); setMessage('') }}
      placeholder={preset.configured ? '已保存，留空沿用' : '粘贴所选服务的 API Key'} /></label>
    <p className="connection-note">预设模型 {preset.model} · 密钥存放在本机</p>
    <div className="connection-actions">
      <ActionButton busy={pending === 'save'} busyLabel="正在保存…" success={message === '写作服务已保存。'} successLabel="已保存" icon={<ArrowRight size={16} />} disabled={!!pending || (!preset.configured && !key.trim())}>
        {onboarding ? '保存并继续' : '保存写作服务'}
      </ActionButton>
      {!onboarding && <ActionButton type="button" className="ghost" busy={pending === 'test'} busyLabel="正在连接…" success={message === '连通性测试通过。'} successLabel="连接正常" icon={<ShieldCheck size={16} />} disabled={!!pending || provider !== active || !preset.configured || !!key} onClick={() => void test()}>测试连接</ActionButton>}
    </div>
    {message && <p className="connection-success" role="status">{message}</p>}
    {error && <p className="error-banner" role="alert">{error}</p>}
  </form>
}

import { useEffect, useState } from 'react'
import { Check, LoaderCircle, Search, ShieldCheck } from 'lucide-react'
import type { SetupStatus } from '../types'
import { request } from '../lib/api'
import { EditorialConstitutionPanel } from '../components/EditorialConstitutionPanel'
import { PluginSecurityPanel } from '../components/PluginSecurityPanel'
import { ImageSettingsPanel } from '../components/ImageSettingsPanel'

export function SetupPage({ status, onSaved, focusImageSettings = false }: { status: SetupStatus | null; onSaved: () => void; focusImageSettings?: boolean }) {
  const [model, setModel] = useState(status?.deepseek_model || 'deepseek-v4-flash')
  const [deepseek, setDeepseek] = useState('')
  const [tavily, setTavily] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [testBusy, setTestBusy] = useState('')
  const [testMessages, setTestMessages] = useState<Record<string, string>>({})
  useEffect(() => {
    if (focusImageSettings) document.getElementById('image-settings')?.scrollIntoView?.({ block: 'start' })
  }, [focusImageSettings])

  async function testProvider(provider: 'deepseek' | 'tavily') {
    setTestBusy(provider)
    setTestMessages((current) => ({ ...current, [provider]: '' }))
    try {
      const result = await request<{ ok: boolean }>(`/setup/test/${provider}`, { method: 'POST' })
      if (!result.ok) throw new Error('服务已响应，但连通性验证未通过，请检查模型配置。')
      setTestMessages((current) => ({ ...current, [provider]: '连通性测试通过' }))
    } catch (error) {
      setTestMessages((current) => ({ ...current, [provider]: (error as Error).message }))
    } finally { setTestBusy('') }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true); setMessage('')
    try {
      await request('/setup', {
        method: 'POST',
        body: JSON.stringify({
          deepseek_api_key: deepseek || null,
          tavily_api_key: tavily || null,
          deepseek_model: model,
        }),
      })
      setDeepseek(''); setTavily(''); setMessage('配置已安全保存。')
      onSaved()
    } catch (error) { setMessage((error as Error).message) }
    finally { setBusy(false) }
  }

  return (
    <main className="page setup-page">
      <div className="eyebrow">本地设置</div>
      <h1>{status?.deepseek_configured ? <>配置与写作边界。</> : <>先把钥匙收好，<br />再开始写作。</>}</h1>
      <p className="lead">API Key 默认进入 Windows 凭据管理器，不写入数据库、前端或日志。留空表示保留已有配置。</p>
      <nav className="section-nav" aria-label="设置分组"><a href="#provider-settings">模型与连接</a><a href="#image-settings">图像生成</a><a href="#constitution-settings">写作边界</a><a href="#plugin-settings">高级插件设置</a></nav>
      <form id="provider-settings" className="setup-card" onSubmit={save}>
        <div className="panel-title"><span>模型与连接</span><small>{status?.deepseek_configured ? '写作服务已配置' : '需要配置写作服务'}</small></div>
        <label>DeepSeek API Key<input type="password" value={deepseek} onChange={(e) => setDeepseek(e.target.value)} placeholder={status?.deepseek_configured ? '已配置 · 留空不修改' : '本地输入'} /></label>
        <label>Tavily API Key<input type="password" value={tavily} onChange={(e) => setTavily(e.target.value)} placeholder={status?.tavily_configured ? '已配置 · 留空不修改' : '本地输入'} /></label>
        <label>全局 DeepSeek 模型<input value={model} onChange={(e) => setModel(e.target.value)} /></label>
        <div className="form-note">请填写你的 DeepSeek 账号可用的模型名称。保存配置不会发起模型调用；点击连通性测试可能产生用量。</div>
        <button className="primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}保存配置</button>
        {message && <p className="message" role="status">{message}</p>}
        <div className="provider-tests">
          <button type="button" className="ghost" disabled={!status?.deepseek_configured || !!testBusy} onClick={() => testProvider('deepseek')}>{testBusy === 'deepseek' ? <LoaderCircle className="spin" size={15} /> : <ShieldCheck size={15} />}测试 DeepSeek</button>
          <button type="button" className="ghost" disabled={!status?.tavily_configured || !!testBusy} onClick={() => testProvider('tavily')}>{testBusy === 'tavily' ? <LoaderCircle className="spin" size={15} /> : <Search size={15} />}测试 Tavily</button>
        </div>
        {(testMessages.deepseek || testMessages.tavily) && <div className="provider-test-results">{testMessages.deepseek && <p>DeepSeek：{testMessages.deepseek}</p>}{testMessages.tavily && <p>Tavily：{testMessages.tavily}</p>}</div>}
      </form>
      <ImageSettingsPanel />
      <div id="constitution-settings"><EditorialConstitutionPanel /></div>
      <div id="plugin-settings"><PluginSecurityPanel /></div>
    </main>
  )
}

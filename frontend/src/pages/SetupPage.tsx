import { useState } from 'react'
import { Check, LoaderCircle, Search, Palette, Plug, Image, ShieldCheck, Puzzle, Keyboard } from 'lucide-react'
import type { SetupStatus } from '../types'
import { request } from '../lib/api'
import { EditorialConstitutionPanel } from '../components/EditorialConstitutionPanel'
import { PluginSecurityPanel } from '../components/PluginSecurityPanel'
import { ImageSettingsPanel } from '../components/ImageSettingsPanel'
import { WritingConnection } from '../components/WritingConnection'
import { ReadingPreferences } from '../components/ReadingPreferences'
import { usePreferences } from '../lib/preferences'

const groups = [['connection', '模型与连接', Plug], ['appearance', '阅读与外观', Palette], ['image', '图像生成', Image], ['constitution', '写作边界', ShieldCheck], ['plugins', '高级插件设置', Puzzle], ['shortcuts', '快捷键与引导', Keyboard]] as const

export function SetupPage({ status, onSaved, focusImageSettings = false, onReplay, onResetOpening }: { status: SetupStatus | null; onSaved: () => void; focusImageSettings?: boolean; onReplay?: () => void; onResetOpening?: () => void }) {
  const [group, setGroup] = useState(focusImageSettings ? 'image' : 'connection')
  const [visited, setVisited] = useState<string[]>([focusImageSettings ? 'image' : 'connection'])
  const [prefs, setPrefs] = usePreferences()
  function selectGroup(id: string) { setGroup(id); setVisited((old) => old.includes(id) ? old : [...old, id]) }
  const [model, setModel] = useState(status?.deepseek_model || 'deepseek-v4-flash')
  const [tavily, setTavily] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [testBusy, setTestBusy] = useState('')
  const [testMessages, setTestMessages] = useState<Record<string, string>>({})


  async function testProvider(provider: 'tavily') {
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
          tavily_api_key: tavily || null,
          deepseek_model: model,
        }),
      })
      setTavily(''); setMessage('配置已安全保存。')
      onSaved()
    } catch (error) { setMessage((error as Error).message) }
    finally { setBusy(false) }
  }

  return (
    <main className="page setup-page">
      <h1>配置与写作边界</h1>
      <p className="lead">写作服务、封面生成与资料检索都可以分别设置。</p>
      <div className="settings-layout">
      <nav className="settings-nav" role="tablist" aria-label="设置分组" aria-orientation="vertical">{groups.map(([id, label, Icon], index) => <button key={id} id={`settings-tab-${id}`} role="tab" aria-selected={group === id} aria-controls={`settings-panel-${id}`} tabIndex={group === id ? 0 : -1} onClick={() => selectGroup(id)} onKeyDown={(event) => {
        let next = index
        if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % groups.length
        else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (index + groups.length - 1) % groups.length
        else if (event.key === 'Home') next = 0
        else if (event.key === 'End') next = groups.length - 1
        else return
        event.preventDefault(); selectGroup(groups[next][0]); document.getElementById(`settings-tab-${groups[next][0]}`)?.focus()
      }}><Icon size={17} /><span>{label}</span></button>)}</nav>
      <div className="settings-content">
      <div role="tabpanel" id="settings-panel-connection" aria-labelledby="settings-tab-connection" hidden={group !== 'connection'}>
      {visited.includes('connection') && <>
      <section id="provider-settings" className="setup-card">
        <div className="panel-title"><span>模型与连接</span><small>{(status?.writing_configured ?? status?.deepseek_configured) ? '写作服务已配置' : '写作服务未配置'}</small></div>
        {status && <WritingConnection status={status} onSaved={onSaved} />}
      </section>
      <details className="setup-card connection-advanced"><summary>检索服务与 DeepSeek 高级设置</summary>
      <form onSubmit={save}>
        <label>Tavily API Key<input type="password" value={tavily} onChange={(e) => setTavily(e.target.value)} placeholder={status?.tavily_configured ? '已配置 · 留空不修改' : '本地输入'} /></label>
        <label>全局 DeepSeek 模型<input value={model} onChange={(e) => setModel(e.target.value)} /></label>
        <div className="form-note">请填写你的 DeepSeek 账号可用的模型名称。保存配置不会发起模型调用；点击连通性测试可能产生用量。</div>
        <button className="primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}保存配置</button>
        {message && <p className="message" role="status">{message}</p>}
        <div className="provider-tests">
          <button type="button" className="ghost" disabled={!status?.tavily_configured || !!testBusy} onClick={() => testProvider('tavily')}>{testBusy === 'tavily' ? <LoaderCircle className="spin" size={15} /> : <Search size={15} />}测试 Tavily</button>
        </div>
        {testMessages.tavily && <p role="status">Tavily：{testMessages.tavily}</p>}
      </form>
      </details>
      </>}
      </div>
      <div role="tabpanel" id="settings-panel-appearance" aria-labelledby="settings-tab-appearance" hidden={group !== 'appearance'}>
        {visited.includes('appearance') && <section className="setup-card"><h2>让文字读起来更舒服</h2><p className="form-note">调整编辑器的排版与纸色，随时预览。</p><ReadingPreferences /><label>界面动态效果<select value={prefs.motion} onChange={(e) => setPrefs((p) => ({ ...p, motion: e.target.value === 'reduce' ? 'reduce' : 'system' }))}><option value="system">跟随系统</option><option value="reduce">减少动态效果</option></select></label></section>}
      </div>
      <div role="tabpanel" id="settings-panel-image" aria-labelledby="settings-tab-image" hidden={group !== 'image'}>{visited.includes('image') && <ImageSettingsPanel />}</div>
      <div role="tabpanel" id="settings-panel-constitution" aria-labelledby="settings-tab-constitution" hidden={group !== 'constitution'}>{visited.includes('constitution') && <EditorialConstitutionPanel />}</div>
      <div role="tabpanel" id="settings-panel-plugins" aria-labelledby="settings-tab-plugins" hidden={group !== 'plugins'}>{visited.includes('plugins') && <PluginSecurityPanel />}</div>
      <div role="tabpanel" id="settings-panel-shortcuts" aria-labelledby="settings-tab-shortcuts" hidden={group !== 'shortcuts'}>
        <section className="setup-card"><h2>把常用操作留在手边</h2><dl className="shortcut-list"><div><dt>搜索与跳转</dt><dd><kbd>Ctrl / ⌘ K</kbd></dd></div><div><dt>展开 / 收起侧栏</dt><dd><kbd>Ctrl / ⌘ Shift P</kbd></dd></div><div><dt>保存文章新版本</dt><dd><kbd>Ctrl / ⌘ S</kbd></dd></div><div><dt>退出专注 / 关闭搜索</dt><dd><kbd>Esc</kbd></dd></div></dl>
        <label>启动动画<select value={prefs.opening} onChange={(e) => setPrefs((p) => ({ ...p, opening: e.target.value as typeof p.opening }))}><option value="first">首次打开时播放</option><option value="always">每次打开时播放</option><option value="never">不自动播放</option></select></label><p className="form-note">减少动态效果时跳过自动动画。重看引导不会清除已有文章和连接设置。</p><div className="settings-actions"><button className="ghost" onClick={onReplay} disabled={!onReplay}>重播欢迎动画</button><button className="ghost" onClick={onResetOpening} disabled={!onResetOpening}>重新查看首次引导</button></div></section>
      </div>
      </div></div>
    </main>
  )
}

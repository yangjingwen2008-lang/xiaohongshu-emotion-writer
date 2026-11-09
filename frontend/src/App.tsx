import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { LoaderCircle, RotateCcw, PanelLeftClose, PanelLeftOpen, Search } from 'lucide-react'
import type { Content, SetupStatus } from './types'
import { request } from './lib/api'
import { Sidebar } from './components/Sidebar'
import { PageBoundary } from './components/PageBoundary'
import { Dashboard } from './pages/Dashboard'
import { LaunchMark, Opening } from './components/Opening'
import { QuickOpen } from './components/QuickOpen'
import { LeaveEditorDialog } from './components/LeaveEditorDialog'
import { stringValue, usePreferences, useStoredState } from './lib/preferences'
import './index.css'
import './usability.css'
import './studio.css'
import './reader.css'

const SetupPage = lazy(() => import('./pages/SetupPage').then((m) => ({ default: m.SetupPage })))
const Composer = lazy(() => import('./pages/Composer').then((m) => ({ default: m.Composer })))
const ContentLibrary = lazy(() => import('./pages/ContentLibrary').then((m) => ({ default: m.ContentLibrary })))
const StyleTrainingPage = lazy(() => import('./pages/StyleTrainingPage').then((m) => ({ default: m.StyleTrainingPage })))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })))
const openingKey = 'chaoshi-yuji.opening.v1'

function hasSeenOpening() {
  try { return localStorage.getItem(openingKey) === 'seen' }
  catch { return false }
}

export default function App() {
  const [prefs] = usePreferences()
  const [collapsed, setCollapsed] = useStoredState('chaoshi-yuji.sidebar.v1', false, (v) => v === true)
  const [, setLastContent] = useStoredState('chaoshi-yuji.last-content.v1', '', stringValue)
  const [quickOpen, setQuickOpen] = useState(false)
  const [page, setPage] = useState('home')
  const [focusImageSettings, setFocusImageSettings] = useState(false)
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [contents, setContents] = useState<Content[]>([])
  const [selected, setSelected] = useState<Content | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [opening, setOpening] = useState(false)
  const [seenOpening, setSeenOpening] = useState(hasSeenOpening)
  const [launching, setLaunching] = useState(() => prefs.motion !== 'reduce' && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches && (prefs.opening === 'always' || (prefs.opening === 'first' && !hasSeenOpening())))
  const editorDirty = useRef(false)
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null)
  const onDirtyChange = useCallback((dirty: boolean) => { editorDirty.current = dirty }, [])
  const navigation = useRef(0)
  const selectedId = useRef<string | null>(null)
  const loadVersion = useRef(0)

  async function load() {
    const current = ++loadVersion.current
    setError('')
    try {
      const [nextStatus, nextContents] = await Promise.all([
        request<SetupStatus>('/setup/status'), request<Content[]>('/contents'),
      ])
      if (current !== loadVersion.current) return
      setStatus(nextStatus)
      setContents(nextContents)
    } catch (cause) { if (current === loadVersion.current) setError((cause as Error).message) }
    finally { if (current === loadVersion.current) setLoading(false) }
  }
  useEffect(() => { void Promise.resolve().then(load) }, [])
  useEffect(() => {
    document.documentElement.dataset.motion = prefs.motion
    return () => { delete document.documentElement.dataset.motion }
  }, [prefs.motion])
  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if (event.isComposing || event.repeat) return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); if (seenOpening && !launching) setQuickOpen((v) => !v) }
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'p') { event.preventDefault(); setCollapsed((v) => !v) }
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [seenOpening, launching, setCollapsed])

  function finishOpening() {
    try { localStorage.setItem(openingKey, 'seen') } catch { /* Storage may be disabled. */ }
    setSeenOpening(true)
    void load()
  }

  function navigate(next: string) {
    if (editorDirty.current) { setPendingNavigation(() => () => performNavigate(next)); return }
    performNavigate(next)
  }
  function performNavigate(next: string) {
    editorDirty.current = false
    navigation.current += 1
    selectedId.current = null
    setOpening(false)
    setSelected(null)
    setFocusImageSettings(false)
    setError('')
    setPage(next)
    window.scrollTo?.({ top: 0 })
  }

  async function openContent(id: string) {
    if (editorDirty.current) { setPendingNavigation(() => () => void readContent(id)); return }
    await readContent(id)
  }
  async function readContent(id: string) {
    const current = ++navigation.current
    selectedId.current = id
    setOpening(true)
    setError('')
    try {
      const detail = await request<Content>(`/contents/${id}`)
      if (current !== navigation.current) return
      setSelected(detail)
      setLastContent(id)
      setPage('composer')
    } catch (cause) {
      if (current === navigation.current) setError((cause as Error).message)
    } finally { if (current === navigation.current) setOpening(false) }
  }

  function openCreated(content: Content) {
    setContents((current) => [content, ...current.filter((item) => item.id !== content.id)])
    void openContent(content.id)
  }

  async function refreshSelected() {
    if (!selected || selectedId.current !== selected.id) return
    const current = navigation.current
    const detail = await request<Content>(`/contents/${selected.id}`)
    if (current !== navigation.current || selectedId.current !== selected.id) return
    setSelected(detail)
    await load()
  }

  const loadingView = <main className="page loading-page" role="status"><LoaderCircle className="spin" size={22} /><p>正在打开工作台……</p></main>
  const activePage = page
  if (launching) return <LaunchMark returning={seenOpening} onDone={() => setLaunching(false)} />
  if (status && !seenOpening) return <Opening status={status} onDone={finishOpening} />
  return (
    <div className={`app-shell${collapsed ? ' sidebar-collapsed' : ''}`}>
      <a className="skip-link" href="#workspace-content">跳到主要内容</a>
      <Sidebar page={activePage} setPage={navigate} collapsed={collapsed} />
      <div className="workspace" aria-busy={loading || opening}>
        <header className="workspace-bar"><button className="icon-button sidebar-toggle" aria-label={collapsed ? '展开侧栏' : '收起侧栏'} aria-expanded={!collapsed} title="切换侧栏 · Ctrl+Shift+P" onClick={() => setCollapsed(!collapsed)}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button><span>{({ home: '工作台', drafts: '内容库', settings: '设置', composer: '创作', style: '风格训练', analytics: '复盘' } as Record<string, string>)[activePage]}</span><button className="quick-trigger" onClick={() => setQuickOpen(true)}><Search size={16} /><span>搜索与跳转</span><kbd>Ctrl K</kbd></button></header>
        {error && <div className="error-banner app-feedback" role="alert"><span>{error}</span><button className="ghost" onClick={() => void load()}><RotateCcw size={15} />重新连接</button></div>}
        {opening && <div className="app-feedback" role="status"><LoaderCircle className="spin" size={16} />正在读取文章……</div>}
        <PageBoundary key={activePage}>
          <Suspense fallback={loadingView}>
            <div className="page-arrival" id="workspace-content" tabIndex={-1} key={activePage}>
            {loading ? loadingView : !status ? <main className="page"><h1>暂时无法连接工作台</h1><p>请确认启动脚本已运行，然后点击上方“重新连接”。</p></main>
              : activePage === 'settings' ? <SetupPage status={status} onSaved={load} focusImageSettings={focusImageSettings} onReplay={() => setLaunching(true)} onResetOpening={() => { try { localStorage.removeItem(openingKey) } catch { /* State still resets for this session. */ } setSeenOpening(false) }} />
              : activePage === 'composer' && selected ? <Composer onDirtyChange={onDirtyChange} key={selected.id} content={selected} refresh={refreshSelected} goHome={() => navigate('home')} goSettings={() => { navigate('settings'); setFocusImageSettings(true) }} writingConfigured={status.writing_configured ?? status.deepseek_configured} goWritingSettings={() => navigate('settings')} />
              : activePage === 'drafts' ? <ContentLibrary contents={contents} onOpen={openContent} goHome={() => navigate('home')} />
              : activePage === 'style' ? <StyleTrainingPage />
              : activePage === 'analytics' ? <AnalyticsPage />
              : <Dashboard contents={contents} status={status} onCreated={openCreated} onOpen={openContent} onAnalytics={() => navigate('analytics')} onSettings={() => navigate('settings')} />}
            </div>
          </Suspense>
        </PageBoundary>
      </div>
      {quickOpen && <QuickOpen contents={contents} onClose={() => setQuickOpen(false)} onOpen={(id) => void openContent(id)} navigate={navigate} />}
      {pendingNavigation && <LeaveEditorDialog onStay={() => setPendingNavigation(null)} onLeave={() => { const next = pendingNavigation; setPendingNavigation(null); next() }} />}
    </div>
  )
}

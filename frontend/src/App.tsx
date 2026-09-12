import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { LoaderCircle, RotateCcw } from 'lucide-react'
import type { Content, SetupStatus } from './types'
import { request } from './lib/api'
import { Sidebar } from './components/Sidebar'
import { PageBoundary } from './components/PageBoundary'
import { Dashboard } from './pages/Dashboard'
import './index.css'
import './usability.css'

const SetupPage = lazy(() => import('./pages/SetupPage').then((m) => ({ default: m.SetupPage })))
const Composer = lazy(() => import('./pages/Composer').then((m) => ({ default: m.Composer })))
const ContentLibrary = lazy(() => import('./pages/ContentLibrary').then((m) => ({ default: m.ContentLibrary })))
const StyleTrainingPage = lazy(() => import('./pages/StyleTrainingPage').then((m) => ({ default: m.StyleTrainingPage })))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })))

export default function App() {
  const [page, setPage] = useState('home')
  const [focusImageSettings, setFocusImageSettings] = useState(false)
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [contents, setContents] = useState<Content[]>([])
  const [selected, setSelected] = useState<Content | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [opening, setOpening] = useState(false)
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

  function navigate(next: string) {
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
    const current = ++navigation.current
    selectedId.current = id
    setOpening(true)
    setError('')
    try {
      const detail = await request<Content>(`/contents/${id}`)
      if (current !== navigation.current) return
      setSelected(detail)
      setPage('composer')
    } catch (cause) {
      if (current === navigation.current) setError((cause as Error).message)
    } finally { if (current === navigation.current) setOpening(false) }
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
  const activePage = page === 'home' && status && !status.deepseek_configured ? 'settings' : page
  return (
    <div className="app-shell">
      <Sidebar page={activePage} setPage={navigate} />
      <div className="workspace" aria-busy={loading || opening}>
        {error && <div className="error-banner app-feedback" role="alert"><span>{error}</span><button className="ghost" onClick={() => void load()}><RotateCcw size={15} />重新连接</button></div>}
        {opening && <div className="app-feedback" role="status"><LoaderCircle className="spin" size={16} />正在读取文章……</div>}
        <PageBoundary key={activePage}>
          <Suspense fallback={loadingView}>
            {loading ? loadingView : !status ? <main className="page"><h1>暂时无法连接工作台</h1><p>请确认启动脚本已运行，然后点击上方“重新连接”。</p></main>
              : activePage === 'settings' ? <SetupPage status={status} onSaved={load} focusImageSettings={focusImageSettings} />
              : activePage === 'composer' && selected ? <Composer key={selected.id} content={selected} refresh={refreshSelected} goHome={() => navigate('home')} goSettings={() => { navigate('settings'); setFocusImageSettings(true) }} />
              : activePage === 'drafts' ? <ContentLibrary contents={contents} onOpen={openContent} goHome={() => navigate('home')} />
              : activePage === 'style' ? <StyleTrainingPage />
              : activePage === 'analytics' ? <AnalyticsPage />
              : <Dashboard contents={contents} status={status} onCreated={(content) => void openContent(content.id)} onOpen={openContent} onAnalytics={() => navigate('analytics')} />}
          </Suspense>
        </PageBoundary>
      </div>
    </div>
  )
}

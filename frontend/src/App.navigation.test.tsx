import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Content } from './types'
import App from './App'

const callbacks = vi.hoisted(() => ({ refreshA: undefined as (() => Promise<void>) | undefined }))
vi.mock('./pages/Dashboard', () => ({ Dashboard: ({ onOpen }: { onOpen: (id: string) => void }) => <><button onClick={() => onOpen('A')}>打开 A</button><button onClick={() => onOpen('B')}>打开 B</button></> }))
vi.mock('./pages/Composer', () => ({ Composer: ({ content, refresh, goHome }: { content: Content; refresh: () => Promise<void>; goHome: () => void }) => {
  if (content.id === 'A') callbacks.refreshA = refresh
  return <><h1>文章 {content.id}</h1><button onClick={() => void refresh()}>刷新文章</button><button onClick={goHome}>返回首页</button></>
} }))
afterEach(() => { cleanup(); vi.unstubAllGlobals(); callbacks.refreshA = undefined })

it('keeps article B open when an earlier refresh or mutation of article A finishes', async () => {
  let readsA = 0
  let resolveOld!: (value: Response) => void
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/setup/status')) return new Response(JSON.stringify({ deepseek_configured: true }))
    if (url.endsWith('/contents/A') && ++readsA === 2) return new Promise<Response>((resolve) => { resolveOld = resolve })
    const id = url.endsWith('/contents/A') ? 'A' : 'B'
    return new Response(JSON.stringify(url.endsWith('/contents') ? [] : { id, title: id }))
  }))
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: '打开 A' }))
  await screen.findByRole('heading', { name: '文章 A' })
  const delayedMutationRefresh = callbacks.refreshA!
  fireEvent.click(screen.getByRole('button', { name: '刷新文章' }))
  fireEvent.click(screen.getByRole('button', { name: '返回首页' }))
  fireEvent.click(await screen.findByRole('button', { name: '打开 B' }))
  await screen.findByRole('heading', { name: '文章 B' })
  await act(async () => { resolveOld(new Response(JSON.stringify({ id: 'A', title: 'updated A' }))) })
  expect(screen.getByRole('heading', { name: '文章 B' })).toBeInTheDocument()
  await act(async () => { await delayedMutationRefresh() })
  expect(readsA).toBe(2)
  expect(screen.getByRole('heading', { name: '文章 B' })).toBeInTheDocument()
})

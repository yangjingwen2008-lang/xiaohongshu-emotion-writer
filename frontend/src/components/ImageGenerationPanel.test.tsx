import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { ImageGenerationPanel } from './ImageGenerationPanel'
import type { CoverCandidate, CoverState } from '../types'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const candidate: CoverCandidate = { id: 'image-1', preview_url: '/api/image-1', download_url: '/api/image-1?download=true', prompt: '雨后窗边', model: 'example-model', width: 900, height: 1200, size_bytes: 1200, created_at: '2026-09-11T10:00:00Z' }
const empty: CoverState = { upload: null, rendered: null, auto_image_generation: true, candidates: [], defaults: { width: 900, height: 1200, ratio: '3:4', format: 'PNG' } }

function Harness({ initial = empty, reload = vi.fn().mockResolvedValue(undefined), settings = vi.fn() }: { initial?: CoverState; reload?: () => Promise<void>; settings?: () => void }) {
  const [state, setState] = useState(initial)
  const [busy, setBusy] = useState('')
  return <ImageGenerationPanel contentId="article" state={state} busy={busy} setBusy={setBusy} reload={reload} onSettings={settings}
    onGenerated={(image) => setState((value) => ({ ...value, candidates: [image] }))} />
}

it('blocks repeated submission and keeps generation separate from selecting a cover', async () => {
  let resolve!: (response: Response) => void
  const fetch = vi.fn((_input: RequestInfo | URL, _options?: RequestInit) => new Promise<Response>((done) => { resolve = done }))
  vi.stubGlobal('fetch', fetch)
  render(<Harness />)
  fireEvent.change(screen.getByLabelText('画面描述'), { target: { value: '雨后窗边' } })
  fireEvent.click(screen.getByRole('button', { name: '生成图片' }))
  fireEvent.click(screen.getByRole('button', { name: '正在生成图片……' }))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(JSON.parse(fetch.mock.calls[0][1]?.body as string)).toEqual({ prompt: '雨后窗边', size: null })
  resolve(new Response(JSON.stringify(candidate)))
  expect(await screen.findByRole('button', { name: '用作封面' })).toBeVisible()
  expect(screen.getByRole('link', { name: '下载' })).toHaveAttribute('href', candidate.download_url)
  await waitFor(() => expect(screen.getByRole('button', { name: '生成图片' })).toBeEnabled())
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('surfaces a failure and only retries when the user explicitly generates again', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '图像生成超时，上游可能已计费' }), { status: 504 }))
  vi.stubGlobal('fetch', fetch)
  render(<Harness />)
  fireEvent.change(screen.getByLabelText('画面描述'), { target: { value: '雨后窗边' } })
  fireEvent.click(screen.getByRole('button', { name: '生成图片' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('可能已计费')
  await waitFor(() => expect(screen.getByRole('button', { name: '生成图片' })).toBeEnabled())
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('shows saved candidates when reopened and applies a candidate without a model call', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('{}'))
  const reload = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('fetch', fetch)
  render(<Harness initial={{ ...empty, candidates: [candidate] }} reload={reload} />)
  fireEvent.click(screen.getByRole('button', { name: '用作封面' }))
  await waitFor(() => expect(reload).toHaveBeenCalledOnce())
  expect(fetch).toHaveBeenCalledWith('/api/contents/article/cover/candidates/image-1/use', expect.objectContaining({ method: 'POST' }))
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('offers settings and prevents generation when no model is configured', () => {
  const settings = vi.fn()
  render(<Harness initial={{ ...empty, auto_image_generation: false }} settings={settings} />)
  fireEvent.change(screen.getByLabelText('画面描述'), { target: { value: '雨后窗边' } })
  expect(screen.getByRole('button', { name: '生成图片' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '前往图像设置' }))
  expect(settings).toHaveBeenCalledOnce()
})

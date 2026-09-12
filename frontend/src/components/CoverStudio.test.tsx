import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CoverStudio } from './CoverStudio'
import type { Content, CoverState } from '../types'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const content: Content = { id: 'article', theme: '雨后', emotion: '想念', status: 'draft', current_step: 'human_edit', updated_at: '' }
const saved: CoverState = {
  upload: { id: 'original', preview_url: '/original.png', width: 1200, height: 1600 },
  rendered: { id: 'render-1', preview_url: '/render.png', template: 'whitespace', copy: '已保存文案', width: 900, height: 1200, focus_x: 0.5, focus_y: 0.5, zoom: 1 },
  defaults: { width: 900, height: 1200, ratio: '3:4', format: 'PNG' }, auto_image_generation: true, candidates: [],
}

it('preserves unsaved cover edits when candidates refresh, and restores a new rendered version', async () => {
  let state = saved
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(state))))
  const changed = vi.fn().mockResolvedValue(undefined)
  render(<CoverStudio content={content} suggestedCopy="建议文案" onChanged={changed} />)
  const copy = await screen.findByDisplayValue('已保存文案')
  fireEvent.change(copy, { target: { value: '我正在编辑的文案' } })
  fireEvent.change(screen.getByLabelText('横向焦点'), { target: { value: '0.8' } })
  fireEvent.change(screen.getByLabelText('宽度'), { target: { value: '1000' } })
  fireEvent.click(screen.getByRole('button', { name: '杂志标题型' }))
  fireEvent.click(screen.getByRole('button', { name: '重新载入图片' }))
  await waitFor(() => expect(changed).toHaveBeenCalledOnce())
  expect(copy).toHaveValue('我正在编辑的文案')
  expect(screen.getByLabelText('横向焦点')).toHaveValue('0.8')
  expect(screen.getByLabelText('宽度')).toHaveValue(1000)
  expect(screen.getByRole('button', { name: '杂志标题型' })).toHaveAttribute('aria-pressed', 'true')
  state = { ...saved, rendered: { ...saved.rendered!, id: 'render-2', copy: '另一窗口保存的封面' } }
  fireEvent.click(screen.getByRole('button', { name: '重新载入图片' }))
  expect(await screen.findByDisplayValue('另一窗口保存的封面')).toBeInTheDocument()
})

it('does not let an older cover request overwrite a newer response', async () => {
  let resolveOld!: (value: Response) => void
  let calls = 0
  vi.stubGlobal('fetch', vi.fn(() => {
    calls += 1
    if (calls === 2) return new Promise<Response>((resolve) => { resolveOld = resolve })
    return Promise.resolve(new Response(JSON.stringify(calls === 1 ? saved : { ...saved, rendered: { ...saved.rendered!, id: 'render-2', copy: '最新封面' } })))
  }))
  render(<CoverStudio content={content} suggestedCopy="建议文案" onChanged={vi.fn().mockResolvedValue(undefined)} />)
  await screen.findByDisplayValue('已保存文案')
  fireEvent.click(screen.getByRole('button', { name: '重新载入图片' }))
  fireEvent.click(screen.getByRole('button', { name: '重新载入图片' }))
  await screen.findByDisplayValue('最新封面')
  await act(async () => { resolveOld(new Response(JSON.stringify(saved))) })
  expect(screen.getByDisplayValue('最新封面')).toBeInTheDocument()
})

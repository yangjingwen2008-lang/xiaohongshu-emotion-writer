import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Composer } from './Composer'
import type { Content } from '../types'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('recovers from a failed draft without reselecting the confirmed detail', async () => {
  const fetch = vi.fn(async (_input: RequestInfo | URL, _options?: RequestInit) => new Response('[]'))
  vi.stubGlobal('fetch', fetch)
  const content: Content = { id: 'sample', theme: '主题', emotion: '情绪', status: 'draft', current_step: 'draft_generation',
    selected_plan_id: 'p1', selected_detail: '已确认细节', updated_at: '2026-09-11T10:00:00Z',
    artifacts: [{ id: 'd1', artifact_type: 'DetailQuestion', step_id: 's1', version: 1, confirmed: true,
      payload: { question: '什么细节？', virtual_details: [] }, created_at: '2026-09-11T10:00:00Z' }] }
  render(<Composer content={content} refresh={vi.fn().mockResolvedValue(undefined)} goHome={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '重新生成初稿' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/contents/sample/workflow/draft', expect.objectContaining({ method: 'POST' })))
  expect(fetch.mock.calls.filter(([, options]) => (options as RequestInit)?.method === 'POST')).toHaveLength(1)
  expect(fetch.mock.calls.some(([path]) => String(path).includes('select-detail'))).toBe(false)
})

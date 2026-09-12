import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CreateCard } from './CreateCard'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('shows creation errors while preserving the entered article information', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '暂时无法保存文章，请重试。' }), { status: 503 }))
  const created = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(<CreateCard onCreated={created} />)
  fireEvent.click(screen.getByRole('button', { name: /写下一个念头/ }))
  fireEvent.change(screen.getByLabelText('今日主题'), { target: { value: '雨后回家' } })
  fireEvent.change(screen.getByLabelText('主要情绪'), { target: { value: '平静' } })
  fireEvent.click(screen.getByRole('button', { name: '生成创作流程' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法保存文章')
  expect(screen.getByLabelText('今日主题')).toHaveValue('雨后回家')
  expect(screen.getByRole('button', { name: '生成创作流程' })).toBeEnabled()
  expect(created).not.toHaveBeenCalled()
  expect(fetch).toHaveBeenCalledOnce()
})

it('rejects whitespace-only fields before creating an article', async () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(<CreateCard onCreated={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: /写下一个念头/ }))
  fireEvent.change(screen.getByLabelText('今日主题'), { target: { value: '   ' } })
  fireEvent.change(screen.getByLabelText('主要情绪'), { target: { value: '平静' } })
  fireEvent.click(screen.getByRole('button', { name: '生成创作流程' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('不能只输入空格')
  expect(fetch).not.toHaveBeenCalled()
})

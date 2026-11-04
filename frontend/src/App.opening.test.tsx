import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

function start() {
  localStorage.clear()
  let active = 'deepseek'
  const fetch = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/setup/writing')) active = JSON.parse(String(options?.body)).provider
    const presets = [
      { id: 'deepseek', label: 'DeepSeek', model: 'deepseek-v4-flash', configured: false },
      { id: 'openai', label: 'OpenAI', model: 'gpt-4o-mini', configured: active === 'openai' },
    ]
    return new Response(JSON.stringify(url.endsWith('/setup/status') ? {
      deepseek_configured: false,
      writing_provider: active,
      writing_configured: active === 'openai',
      writing_providers: presets,
    } : url.endsWith('/setup/writing') ? { saved: true } : []))
  })
  vi.stubGlobal('fetch', fetch)
  render(<App />)
  return fetch
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

it('skips setup, opens the desk without a key, and remembers completion on relaunch', async () => {
  const fetch = start()
  fireEvent.click(await screen.findByRole('button', { name: '跳过引导' }))
  expect(screen.getByRole('heading', { name: '欢迎' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '进入工作台' }))
  expect(await screen.findByRole('heading', { name: '今天想写什么？' })).toBeVisible()
  expect(screen.getByRole('button', { name: '配置 API Key' })).toBeVisible()
  expect(fetch.mock.calls.some(([input]) => String(input).endsWith('/setup/writing'))).toBe(false)
  cleanup()
  render(<App />)
  expect(await screen.findByRole('heading', { name: '今天想写什么？' })).toBeVisible()
})

it('pages through onboarding and saves only the selected supplier and key', async () => {
  const fetch = start()
  fireEvent.click(await screen.findByRole('button', { name: '继续' }))
  fireEvent.click(screen.getByRole('button', { name: '继续' }))
  fireEvent.change(screen.getByLabelText('写作服务'), { target: { value: 'openai' } })
  fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'test-openai-key' } })
  fireEvent.click(screen.getByRole('button', { name: '保存并继续' }))
  expect(await screen.findByRole('heading', { name: '欢迎' })).toBeVisible()
  const call = fetch.mock.calls.find(([input]) => String(input).endsWith('/setup/writing'))
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ provider: 'openai', api_key: 'test-openai-key' })
  fireEvent.click(screen.getByRole('button', { name: '进入工作台' }))
  expect(await screen.findByRole('heading', { name: '今天想写什么？' })).toBeVisible()
  await screen.findByText('草稿与待审核')
  expect(screen.queryByRole('button', { name: '配置 API Key' })).toBeNull()
})

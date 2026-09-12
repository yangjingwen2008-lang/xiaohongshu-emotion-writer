import { afterEach, describe, expect, it, vi } from 'vitest'
import { request, uploadRequest } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('API feedback', () => {
  it('explains structured validation errors without rendering objects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ['body', 'theme'], msg: '不能为空' }] }), { status: 422 })))
    await expect(request('/contents')).rejects.toThrow('theme：不能为空')
  })

  it('reports a lost connection and never retries a mutation', async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetch)
    await expect(request('/contents', { method: 'POST', body: '{}' })).rejects.toThrow('无法连接本地服务')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('rejects an HTML fallback masquerading as a successful API response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>app</html>')))
    await expect(request('/missing')).rejects.toThrow('无法读取的数据')
  })

  it('leaves multipart boundaries to the browser', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"id":"image-1"}'))
    vi.stubGlobal('fetch', fetch)
    const form = new FormData()
    form.set('file', new Blob(['image']), 'sample.png')
    await expect(uploadRequest('/ocr/trends', form)).resolves.toEqual({ id: 'image-1' })
    expect(fetch).toHaveBeenCalledWith('/api/ocr/trends', { method: 'POST', body: form })
  })
})

export const API = '/api'

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (!item || typeof item !== 'object' || typeof item.msg !== 'string') return ''
      const field = Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== 'body').join(' / ') : ''
      return `${field ? `${field}：` : ''}${item.msg}`
    }).filter(Boolean)
    if (messages.length) return `请检查输入：${messages.join('；')}`
  }
  return fallback
}

async function send<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API}${path}`, options)
  } catch {
    throw new Error('无法连接本地服务，请确认工作台已启动后重试。')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(errorMessage(body?.detail, `请求失败（${response.status}），请稍后重试。`))
  if (body === null && response.status !== 204) throw new Error('服务返回了无法读取的数据，请刷新页面后重试。')
  return body as T
}

export function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  if (options?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  return send<T>(path, { ...options, headers })
}

export function uploadRequest<T>(path: string, body: FormData): Promise<T> {
  return send<T>(path, { method: 'POST', body })
}

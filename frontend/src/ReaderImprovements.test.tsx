import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ContentLibrary } from './pages/ContentLibrary'
import { ReadingPreferences } from './components/ReadingPreferences'
import { SetupPage } from './pages/SetupPage'
import { QuickOpen } from './components/QuickOpen'
import { RichEditor } from './components/RichEditor'
import { defaults, normalizePreferences, preferenceKey } from './lib/preferences'
import { markdownDocument } from './lib/editor-export'
import type { Content } from './types'

beforeEach(() => {
  localStorage.clear()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
})
afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks() })
const contents: Content[] = [
  { id: 'one', title: '雨停之前', theme: '城市', emotion: '想念', status: 'draft', current_step: 'human_edit', updated_at: '2026-11-01T10:00:00Z' },
  { id: 'two', title: '下班以后', theme: '夜路', emotion: '平静', status: 'published', current_step: 'review_submission', updated_at: '2026-11-08T10:00:00Z' },
  { id: 'three', title: '路口的灯', theme: '城市', emotion: '想念', status: 'pending_review', current_step: 'review_submission', updated_at: '2026-11-07T10:00:00Z' },
]
function library() { const open = vi.fn(); render(<ContentLibrary contents={contents} onOpen={open} goHome={vi.fn()} />); return open }

it('combines status, emotion, whitespace-trimmed search and resets the filters', () => {
  library()
  fireEvent.change(screen.getByRole('textbox', { name: '搜索内容' }), { target: { value: '  城市  ' } })
  fireEvent.change(screen.getByLabelText('情绪'), { target: { value: '想念' } })
  fireEvent.click(screen.getByRole('button', { name: /^待审核/ }))
  expect(screen.getByRole('status')).toHaveTextContent('显示 1 / 3 篇')
  expect(screen.getByRole('button', { name: '打开文章：路口的灯' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '清除筛选' }))
  expect(screen.getByRole('status')).toHaveTextContent('显示 3 / 3 篇')
})
it('sorts articles, remembers grid and favorites, and keeps favorite actions separate from opening', () => {
  const open = library()
  expect(screen.getAllByRole('button', { name: /^打开文章/ })[0]).toHaveAccessibleName('打开文章：下班以后')
  fireEvent.change(screen.getByLabelText('排序'), { target: { value: 'oldest' } })
  expect(screen.getAllByRole('button', { name: /^打开文章/ })[0]).toHaveAccessibleName('打开文章：雨停之前')
  fireEvent.click(screen.getByRole('button', { name: '收藏：雨停之前' }))
  expect(open).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '卡片视图' }))
  cleanup(); library()
  expect(screen.getByRole('button', { name: '卡片视图' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: '收藏' }))
  expect(screen.getAllByRole('button', { name: /^打开文章/ })).toHaveLength(1)
  expect(screen.getByRole('button', { name: '取消收藏：雨停之前' })).toBeVisible()
})
it('resumes an existing article and ignores stale recent IDs', () => {
  localStorage.setItem('chaoshi-yuji.last-content.v1', JSON.stringify('one'))
  const open = library(); fireEvent.click(screen.getByRole('button', { name: '继续查看' }))
  expect(open).toHaveBeenCalledWith('one')
  cleanup(); localStorage.setItem('chaoshi-yuji.last-content.v1', JSON.stringify('deleted')); library()
  expect(screen.queryByRole('button', { name: '继续查看' })).not.toBeInTheDocument()
})
it('handles malformed preferences and clamps out-of-range numeric settings', () => {
  expect(normalizePreferences(null)).toEqual(defaults)
  expect(normalizePreferences({ fontSize: 1000, paper: 'invalid', lineHeight: 12 })).toEqual({ ...defaults, fontSize: 24 })
  localStorage.setItem(preferenceKey, '{broken')
  render(<ReadingPreferences />)
  expect(screen.getByLabelText('正文字体')).toHaveValue('serif')
})
it('persists typography and restores display defaults without resetting motion preferences', () => {
  localStorage.setItem(preferenceKey, JSON.stringify({ ...defaults, motion: 'reduce' }))
  render(<ReadingPreferences />)
  fireEvent.change(screen.getByLabelText('编辑纸色'), { target: { value: 'night' } })
  fireEvent.change(screen.getByLabelText('正文字体'), { target: { value: 'sans' } })
  cleanup(); render(<ReadingPreferences />)
  expect(screen.getByLabelText('编辑纸色')).toHaveValue('night')
  expect(screen.getByLabelText('正文字体')).toHaveValue('sans')
  fireEvent.click(screen.getByRole('button', { name: '恢复默认排版' }))
  expect(JSON.parse(localStorage.getItem(preferenceKey)!)).toEqual({ ...defaults, motion: 'reduce' })
})
it('opens the requested image settings and navigates grouped settings using the keyboard', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ enabled: false, key_configured: false, base_url: '', model: '', timeout_seconds: 180 }))))
  render(<SetupPage status={null} onSaved={vi.fn()} focusImageSettings />)
  expect(screen.getByRole('tab', { name: '图像生成' })).toHaveAttribute('aria-selected', 'true')
  fireEvent.keyDown(screen.getByRole('tab', { name: '图像生成' }), { key: 'ArrowUp' })
  expect(screen.getByRole('tab', { name: '阅读与外观' })).toHaveFocus()
  expect(screen.getByLabelText('编辑纸色')).toBeVisible()
  await waitFor(() => expect(fetch).toHaveBeenCalled())
  vi.unstubAllGlobals()
})
it('quick search supports keyboard selection and opening the intended article', () => {
  const open = vi.fn(); const close = vi.fn()
  render(<QuickOpen contents={contents} onOpen={open} onClose={close} navigate={vi.fn()} />)
  const input = screen.getByRole('combobox')
  expect(input).toHaveFocus()
  fireEvent.change(input, { target: { value: '雨停' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(open).toHaveBeenCalledWith('one'); expect(close).toHaveBeenCalled()
})
it('exports nested block structure and escapes Markdown syntax in literal text', () => {
  expect(markdownDocument('标题*', { type: 'doc', content: [
    { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: '小节' }] },
    { type: 'paragraph', content: [{ type: 'text', text: '细节', marks: [{ type: 'bold' }] }] },
    { type: 'blockquote', content: [{ type: 'paragraph', content: [{ type: 'text', text: '引用' }] }] },
    { type: 'bulletList', content: [{ type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: '第一项' }] }] }] },
  ] })).toBe('# 标题\\*\n\n## 小节\n\n**细节**\n\n> 引用\n\n- 第一项\n')
})
it('keeps temporary edits after failed save and removes recovery only after a successful save', async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error('网络暂时不可用')).mockResolvedValueOnce(undefined)
  render(<RichEditor contentId="test" title="原题" html="<p>正文</p>" onSave={save} />)
  await screen.findByRole('textbox', { name: '文章正文' })
  fireEvent.change(screen.getByLabelText('文章标题'), { target: { value: '修改后的标题' } })
  expect(JSON.parse(localStorage.getItem('chaoshi-yuji.recovery.test')!).title).toBe('修改后的标题')
  fireEvent.keyDown(window, { key: 's', ctrlKey: true })
  expect(await screen.findByText('网络暂时不可用')).toBeVisible()
  expect(localStorage.getItem('chaoshi-yuji.recovery.test')).not.toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '保存新版本' }))
  expect(await screen.findByText('新版本已保存。')).toBeVisible()
  expect(localStorage.getItem('chaoshi-yuji.recovery.test')).toBeNull()
  expect(save).toHaveBeenCalledTimes(2)
})
it('offers explicit recovery without overwriting the server version and blocks editing until a choice', async () => {
  localStorage.setItem('chaoshi-yuji.recovery.test', JSON.stringify({ title: '临时标题', html: '<p>未保存的段落</p>', savedAt: new Date().toISOString() }))
  const save = vi.fn().mockResolvedValue(undefined)
  render(<RichEditor contentId="test" title="已保存标题" html="<p>已保存正文</p>" onSave={save} />)
  await screen.findByRole('textbox', { name: '文章正文' })
  expect(screen.getByLabelText('文章标题')).toHaveValue('已保存标题')
  expect(screen.getByLabelText('文章标题')).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '恢复临时修改' }))
  expect(screen.getByLabelText('文章标题')).toHaveValue('临时标题')
  expect(screen.getByText('未保存的段落')).toBeVisible()
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '保存新版本' }))
  await waitFor(() => expect(save).toHaveBeenCalledWith('临时标题', '<p>未保存的段落</p>', '未保存的段落'))
})
it('does not replace unsaved typing when a late server refresh arrives', async () => {
  const save = vi.fn()
  const { rerender } = render(<RichEditor contentId="test" title="原题" html="<p>原文</p>" onSave={save} />)
  await screen.findByRole('textbox', { name: '文章正文' })
  fireEvent.change(screen.getByLabelText('文章标题'), { target: { value: '正在修改' } })
  rerender(<RichEditor contentId="test" title="服务器迟到的标题" html="<p>服务器迟到的正文</p>" onSave={save} />)
  expect(screen.getByLabelText('文章标题')).toHaveValue('正在修改')
  expect(screen.getByText('原文')).toBeVisible()
  expect(screen.queryByText('服务器迟到的正文')).toBeNull()
})
it('exits focus mode with Escape and copies the current unsaved title', async () => {
  const copy = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: copy } })
  render(<RichEditor title="标题" html="<p>正文</p>" onSave={vi.fn()} />)
  await screen.findByRole('textbox', { name: '文章正文' })
  fireEvent.click(screen.getByRole('button', { name: '进入专注模式' }))
  expect(screen.getByRole('button', { name: '退出专注模式' })).toBeVisible()
  fireEvent.keyDown(window, { key: 'Escape' })
  expect(screen.getByRole('button', { name: '进入专注模式' })).toBeVisible()
  fireEvent.change(screen.getByLabelText('文章标题'), { target: { value: '当前标题' } })
  fireEvent.click(screen.getByRole('button', { name: '复制全文' }))
  await waitFor(() => expect(copy).toHaveBeenCalledWith('当前标题\n\n正文'))
})

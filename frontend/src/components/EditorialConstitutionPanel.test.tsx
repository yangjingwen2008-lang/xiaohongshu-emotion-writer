import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { EditorialConstitutionPanel } from './EditorialConstitutionPanel'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('allows recovery when the first constitution request fails', async () => {
  const current = { version: 0, change_note: '初始规则', sections: { core_principles: ['具体场景'], title_structure_rules: [], ai_tone_prohibitions: [], evaluation_dimensions: [] } }
  let failed = true
  vi.stubGlobal('fetch', vi.fn(async (input) => {
    if (failed) throw new Error('offline')
    return new Response(JSON.stringify(String(input).endsWith('/versions') ? [current] : current))
  }))
  render(<EditorialConstitutionPanel />)
  const retry = await screen.findByRole('button', { name: '重新读取编辑宪法' })
  expect(screen.queryByText('正在读取编辑宪法……')).not.toBeInTheDocument()
  failed = false
  fireEvent.click(retry)
  expect(await screen.findByText('具体场景')).toBeInTheDocument()
})

it('resets an abandoned edit and requires fresh confirmation', async () => {
  const current = { version: 0, change_note: '初始规则', sections: { core_principles: ['具体场景'], title_structure_rules: ['短随笔'], ai_tone_prohibitions: ['不堆金句'], evaluation_dimensions: ['准确'] } }
  vi.stubGlobal('fetch', vi.fn(async (input) => new Response(JSON.stringify(String(input).endsWith('/versions') ? [current] : current))))
  render(<EditorialConstitutionPanel />)
  fireEvent.click(await screen.findByRole('button', { name: '编辑宪法' }))
  fireEvent.change(screen.getByLabelText('核心风格边界（每行一条）'), { target: { value: '未保存的修改' } })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  fireEvent.click(screen.getByRole('button', { name: '编辑宪法' }))
  expect(screen.getByLabelText('核心风格边界（每行一条）')).toHaveValue('具体场景')
  expect(screen.getByRole('checkbox')).not.toBeChecked()
  expect(screen.getByRole('button', { name: '确认并保存新版本' })).toBeDisabled()
})

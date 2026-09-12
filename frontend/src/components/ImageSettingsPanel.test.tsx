import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ImageSettingsPanel } from './ImageSettingsPanel'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('saves image configuration without a generation call and clears the entered key', async () => {
  const config = { enabled: false, base_url: '', model: '', timeout_seconds: 180, key_configured: false, available: false }
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(config)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...config, enabled: true, base_url: 'https://image.example/v1', model: 'image-model', key_configured: true, available: true })))
  vi.stubGlobal('fetch', fetch)
  render(<ImageSettingsPanel />)
  fireEvent.click(await screen.findByRole('checkbox', { name: '启用图像生成' }))
  fireEvent.change(screen.getByLabelText('图像 API Base URL'), { target: { value: 'https://image.example/v1' } })
  fireEvent.change(screen.getByLabelText('图像模型名称'), { target: { value: 'image-model' } })
  fireEvent.change(screen.getByLabelText('图像 API 密钥'), { target: { value: 'private-test-key' } })
  fireEvent.click(screen.getByRole('button', { name: '保存图像配置' }))
  expect(await screen.findByRole('status')).toHaveTextContent('图像配置已保存')
  expect(screen.getByLabelText('图像 API 密钥')).toHaveValue('')
  expect(fetch).toHaveBeenCalledTimes(2)
  await waitFor(() => expect(fetch).toHaveBeenLastCalledWith('/api/setup/image', expect.objectContaining({ method: 'POST' })))
})

it('keeps the settings form editable when a saved configuration is invalid', async () => {
  const message = '图像配置无效，已暂停生图；请重新填写服务地址、模型和密钥并保存。'
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ enabled: false, base_url: '', model: '', timeout_seconds: 180, key_configured: true, available: false, configuration_error: message }))))
  render(<ImageSettingsPanel />)
  expect(await screen.findByRole('alert')).toHaveTextContent(message)
  expect(screen.getByLabelText('图像 API Base URL')).toBeEnabled()
  expect(screen.getByRole('button', { name: '保存图像配置' })).toBeEnabled()
})

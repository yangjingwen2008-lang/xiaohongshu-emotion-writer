import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { WelcomeScene, welcomeExitMs, welcomeHoldMs } from './WelcomeScene'

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('shows punctuation-free welcome and lets the exit finish before opening the desk', () => {
  const onEnter = vi.fn()
  render(<WelcomeScene automatic onEnter={onEnter} />)
  expect(screen.getByRole('heading', { name: '欢迎' })).toBeVisible()
  act(() => vi.advanceTimersByTime(welcomeHoldMs - 1))
  expect(onEnter).not.toHaveBeenCalled()
  act(() => vi.advanceTimersByTime(1))
  expect(screen.getByRole('button', { name: '进入工作台' })).toBeDisabled()
  act(() => vi.advanceTimersByTime(welcomeExitMs))
  expect(onEnter).toHaveBeenCalledTimes(1)
})

it('replays a full sequence and permits early entry without a second callback', () => {
  const onEnter = vi.fn()
  render(<WelcomeScene automatic onEnter={onEnter} />)
  act(() => vi.advanceTimersByTime(1800))
  fireEvent.click(screen.getByRole('button', { name: '重播动画' }))
  act(() => vi.advanceTimersByTime(1000))
  expect(onEnter).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '进入工作台' }))
  act(() => vi.advanceTimersByTime(welcomeExitMs))
  expect(onEnter).toHaveBeenCalledTimes(1)
  act(() => vi.advanceTimersByTime(4000))
  expect(onEnter).toHaveBeenCalledTimes(1)
})

it('cancels auto entry when the scene is removed', () => {
  const onEnter = vi.fn()
  const { unmount } = render(<WelcomeScene automatic onEnter={onEnter} />)
  unmount()
  act(() => vi.advanceTimersByTime(5000))
  expect(onEnter).not.toHaveBeenCalled()
})

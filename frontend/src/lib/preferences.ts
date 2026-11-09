import type { CSSProperties } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

const changed = 'chaoshi-preference-change'
export function useStoredState<T>(key: string, initial: T, validate: (value: unknown) => T) {
  const [value, setValue] = useState<T>(() => {
    try { return validate(JSON.parse(localStorage.getItem(key) ?? 'null')) }
    catch { return initial }
  })
  const current = useRef(value)
  useEffect(() => {
    const read = () => {
      try { return validate(JSON.parse(localStorage.getItem(key) ?? 'null')) }
      catch { return initial }
    }
    const sync = (event: Event) => {
      if (event instanceof StorageEvent && event.key !== key && event.key !== null) return
      if (event instanceof CustomEvent && event.detail.key !== key) return
      const next = event instanceof CustomEvent ? event.detail.value as T : read()
      current.current = next; setValue(next)
    }
    window.addEventListener('storage', sync)
    window.addEventListener(changed, sync)
    return () => { window.removeEventListener('storage', sync); window.removeEventListener(changed, sync) }
  }, [key, initial, validate])
  const update = useCallback((next: T | ((old: T) => T)) => {
    const result = typeof next === 'function' ? (next as (old: T) => T)(current.current) : next
    current.current = result; setValue(result)
    try { localStorage.setItem(key, JSON.stringify(result)) } catch { /* Session changes still work. */ }
    window.dispatchEvent(new CustomEvent(changed, { detail: { key, value: result } }))
  }, [key])
  return [value, update] as const
}

export type Preferences = {
  font: 'serif' | 'sans'; fontSize: number; lineHeight: number; width: 'standard' | 'wide'
  paper: 'white' | 'warm' | 'night'; motion: 'system' | 'reduce'; opening: 'first' | 'always' | 'never'
}
export const defaults: Preferences = { font: 'serif', fontSize: 17, lineHeight: 2.1, width: 'standard', paper: 'white', motion: 'system', opening: 'always' }
export function normalizePreferences(value: unknown): Preferences {
  const p = value && typeof value === 'object' ? value as Partial<Preferences> : {}
  return {
    font: p.font === 'sans' ? 'sans' : 'serif',
    fontSize: typeof p.fontSize === 'number' && Number.isFinite(p.fontSize) ? Math.max(14, Math.min(24, p.fontSize)) : 17,
    lineHeight: [1.7, 1.9, 2.1, 2.3].includes(p.lineHeight ?? 0) ? p.lineHeight! : 2.1,
    width: p.width === 'wide' ? 'wide' : 'standard',
    paper: p.paper === 'warm' || p.paper === 'night' ? p.paper : 'white',
    motion: p.motion === 'reduce' ? 'reduce' : 'system',
    opening: p.opening === 'first' || p.opening === 'never' ? p.opening : 'always',
  }
}
export const preferenceKey = 'chaoshi-yuji.preferences.v1'
export function usePreferences() { return useStoredState(preferenceKey, defaults, normalizePreferences) }
export const stringIds = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').slice(0, 1000) : []
export const stringValue = (value: unknown) => typeof value === 'string' ? value : ''

export function paperStyle(p: Preferences): CSSProperties {
  return { '--prose-font': p.font === 'serif' ? 'var(--display)' : 'var(--text)', '--prose-weight': p.font === 'serif' ? 500 : 400, '--prose-size': `${p.fontSize}px`, '--prose-leading': p.lineHeight, '--prose-width': p.width === 'wide' ? '960px' : '760px' } as CSSProperties
}

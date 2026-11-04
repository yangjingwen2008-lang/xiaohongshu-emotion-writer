import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

window.scrollTo = vi.fn()
window.matchMedia = vi.fn((query) => ({ matches: query.includes('prefers-reduced-motion') } as MediaQueryList))

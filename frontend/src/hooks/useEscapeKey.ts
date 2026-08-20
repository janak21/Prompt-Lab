import { useEffect } from 'react'

/** esc closes drawers/dialogs — wired centrally so every overlay gets it for free. */
export function useEscapeKey(active: boolean, onEscape: () => void) {
  useEffect(() => {
    if (!active) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onEscape()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [active, onEscape])
}

/** cmd+enter submits forms. */
export function useSubmitShortcut(active: boolean, onSubmit: () => void) {
  useEffect(() => {
    if (!active) return
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        onSubmit()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [active, onSubmit])
}

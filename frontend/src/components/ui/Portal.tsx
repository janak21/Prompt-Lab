import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

export function Portal({ children }: { children: ReactNode }) {
  const [container] = useState(() => {
    const el = document.createElement('div')
    el.setAttribute('data-portal', '')
    return el
  })

  useEffect(() => {
    document.body.appendChild(container)
    return () => {
      document.body.removeChild(container)
    }
  }, [container])

  return createPortal(children, container)
}

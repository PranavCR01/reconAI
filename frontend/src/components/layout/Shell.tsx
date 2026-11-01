import type { ReactNode, CSSProperties } from 'react'
import { useLocation } from 'react-router-dom'
import { TopBar } from './TopBar'
import type { TopBarProps } from './TopBar'

interface ShellProps {
  children: ReactNode
  style?: CSSProperties
  topBarCenter?: ReactNode
  topBarRight?: ReactNode
}

// Re-export TopBarProps type for consumers
export type { TopBarProps }

// Pages with their own navigation (no app header above them).
export const STANDALONE_ROUTES = ['/', '/benchmark']

export function Shell({ children, style, topBarCenter, topBarRight }: ShellProps) {
  const { pathname } = useLocation()
  const standalone = STANDALONE_ROUTES.includes(pathname)
  return (
    <>
      {!standalone && <TopBar center={topBarCenter} right={topBarRight} />}
      <main style={{ minHeight: standalone ? '100vh' : 'calc(100vh - 52px)', ...style }}>
        {children}
      </main>
    </>
  )
}

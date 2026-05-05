import type { ReactNode, CSSProperties } from 'react'
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

export function Shell({ children, style, topBarCenter, topBarRight }: ShellProps) {
  return (
    <>
      <TopBar center={topBarCenter} right={topBarRight} />
      <main style={{ minHeight: 'calc(100vh - 52px)', ...style }}>
        {children}
      </main>
    </>
  )
}

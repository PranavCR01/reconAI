import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { HEALTH_TEXT, HealthNotice } from './App'

afterEach(cleanup)

describe('HealthNotice', () => {
  it('down shows the outage text without promising anyone was notified', () => {
    render(<HealthNotice state="down" onDismiss={() => {}} />)
    const text = screen.getByTestId('health-banner').textContent ?? ''
    expect(text).toContain('temporarily unavailable. Please try again shortly.')
    expect(text).not.toMatch(/notified/i)
  })
  it('degraded shows the softer notice', () => {
    render(<HealthNotice state="degraded" onDismiss={() => {}} />)
    expect(screen.getByTestId('health-banner').dataset.state).toBe('degraded')
    expect(screen.getByTestId('health-banner').textContent).toContain(HEALTH_TEXT.degraded)
  })
  it('ok renders nothing', () => {
    const { container } = render(<HealthNotice state="ok" onDismiss={() => {}} />)
    expect(container.innerHTML).toBe('')
  })
})

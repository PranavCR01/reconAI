import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import Hypotheses from './Hypotheses'
import catalogue from '../data/hypothesis_catalogue.json'

describe('Hypotheses page', () => {
  it('shows every hypothesis of every discrepancy type, in check order', () => {
    render(<Hypotheses />)
    for (const t of catalogue.discrepancy_types) {
      const rows = within(screen.getByTestId(`catalogue-${t.type}`)).getAllByTestId('catalogue-row')
      expect(rows.map(r => r.children[1].textContent)).toEqual(t.hypotheses.map(h => h.id))
    }
  })

  it('marks below-threshold checks as going to review', () => {
    render(<Hypotheses />)
    const nullRows = within(screen.getAllByTestId('catalogue-NULL_DOWNSTREAM')[0]).getAllByTestId('catalogue-row')
    const apex = nullRows.find(r => r.children[1].textContent === 'H3c')!
    const fls = nullRows.find(r => r.children[1].textContent === 'H3a')!
    expect(apex.textContent).toContain('0.72 → review')
    expect(fls.textContent).not.toContain('review')
    const delivery = nullRows.find(r => r.children[1].textContent === 'H2')!
    expect(delivery.textContent).toContain('0.70 if 1 event → review')
  })
})

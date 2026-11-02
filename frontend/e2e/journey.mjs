// Browser journey against the fake backend (no real network).
//
//   python -m backend.tests.e2e_server            (terminal 1; E2E_REJECT_FIELD=TaxId__c for the critic case)
//   npm run dev                                    (terminal 2, proxies /api to :8000)
//   node e2e/journey.mjs [http://localhost:5173]
//
// Exits non-zero on the first failed check. Uses the `playwright` library already on the machine.
import { createRequire } from 'module'
const { chromium } = createRequire(import.meta.url)('playwright')

const BASE = process.argv[2] ?? 'http://localhost:5173'
const EXECUTABLE = process.env.PW_CHROMIUM ?? undefined
let failures = 0
const check = (ok, msg) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${msg}`); if (!ok) failures++ }

const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE, args: ['--no-sandbox'] } : {})
const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] })
await context.addInitScript(() => localStorage.setItem('recon_access', 'granted'))
const page = await context.newPage()
const consoleErrors = []
page.on('pageerror', e => consoleErrors.push(e.message))
page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) consoleErrors.push(m.text()) })

// Landing -> upload sample -> live view until done
await page.goto(`${BASE}/`)
check(await page.title() !== '', 'landing renders')
await page.goto(`${BASE}/upload`)
await page.getByText('Use sample FSC data').click()
await page.getByText('Start Analysis').click()
await page.waitForURL(/\/runs\/[0-9a-f-]+$/, { timeout: 15000 })
const runId = page.url().split('/runs/')[1]
check(!!runId, `run created ${runId}`)

const api = async path => (await page.request.get(`${BASE}/api/v1${path}`)).json()
let run
for (let i = 0; i < 60; i++) {
  run = await api(`/recon/runs/${runId}`)
  if (run.run?.status === 'complete' && run.incidents?.length >= 10) break
  await page.waitForTimeout(1000)
}
check(run.incidents.length === 10, `10 incidents analysed (got ${run.incidents.length})`)
await page.waitForTimeout(1500)
check(await page.getByText('Tool Sources').count() === 1, 'live view shows tool sources (simulated)')
check(await page.getByText('degraded').count() === 0, 'no fake "degraded" connection')

const find = field => run.incidents.find(i => i.sf_field === field)
const open = async inc => {
  await page.goto(`${BASE}/runs/${runId}/incidents/${inc.id}`)
  await page.getByText('Hypothesis Execution').waitFor({ timeout: 15000 })
}
const verdicts = async () => page.locator('[data-testid="timeline-step"]').evaluateAll(n => n.map(e => e.dataset.verdict))

// Confirmed incident: Contact.Phone (FLS stripped behind an unrelated missed event)
const phone = find('Phone')
await open(phone)
const pv = await verdicts()
check(JSON.stringify(pv) === JSON.stringify(['refuted', 'confirmed']), `Contact.Phone timeline refuted -> confirmed (got ${pv})`)
check(await page.getByText('CONFIRMED', { exact: true }).count() === 1, 'exactly one CONFIRMED step')
check(await page.getByText('get_field_permissions').count() >= 1, 'real tool name shown for the FLS check')
check(await page.getByText('schema_diff').count() === 0, 'no hardcoded tool chips')
check(await page.getByTestId('unconfirmed-banner').count() === 0, 'no unconfirmed banner on a confirmed incident')
check(await page.getByText('Contact.Phone').count() >= 1, 'header shows the real object.field')
check(await page.locator('[data-testid="trace-step"]').count() >= 7, 'trace tab lists the pipeline steps')
check(await page.getByTestId('app-bar').count() === 1 && await page.getByTestId('page-bar').count() === 1, 'one app header plus one page bar')
check(await page.locator('[data-testid="page-bar"] a[href="/"]').count() === 0, 'page bar carries no second logo')
check(await page.locator('select').first().inputValue() === 'fls_permission_grant', 'fix type defaults from the FLS category')
const phoneSimilar = await page.locator('[data-testid="similar"]').allTextContents()
check(phoneSimilar.length > 0 && phoneSimilar[0].includes('FLS_blocking'), `top similar incident is an FLS incident (got ${phoneSimilar[0]?.slice(0, 60)})`)

// Exhausted incident: Address__c.PostalCode (no fault in the simulated world)
const postal = find('PostalCode')
await open(postal)
const xv = await verdicts()
check(xv.length > 0 && xv.every(v => v !== 'confirmed'), `PostalCode: no confirmed step (got ${xv})`)
check(await page.getByTestId('unconfirmed-banner').count() === 1, 'unconfirmed banner shown')
check((await page.getByTestId('review-reasons').textContent() ?? '').includes('no hypothesis confirmed'), 'review reasons shown')
check((await page.getByTestId('confidence-fill').getAttribute('data-level')) !== 'high', 'unconfirmed confidence is not shown green')
check(postal.confidence <= 0.5, `unconfirmed confidence capped (got ${postal.confidence})`)
const banner = await page.getByTestId('unconfirmed-banner').textContent() ?? ''
check(/No similar past incidents were found|informed by \d+ similar/.test(banner), 'banner says what retrieval found')

// Critic rejection (only when the server scripts it)
if (process.env.E2E_REJECT_FIELD) {
  const rejected = find(process.env.E2E_REJECT_FIELD)
  await open(rejected)
  check(await page.locator('[data-testid="claim"][data-verdict="unsupported"]').count() >= 1, 'critic panel shows the rejected claim')
  check(await page.getByTestId('critic-reason').count() >= 1, 'critic reason shown')
}

// Resolve: "Resolved By" starts empty and is required
await open(phone)
const resolvedBy = page.locator('#resolved-by')
check(await resolvedBy.inputValue() === '', '"Resolved By" starts empty')

// Run summary: copy Jira summaries
await page.goto(`${BASE}/runs/${runId}/summary`)
await page.getByText('Copy Jira summaries').click()
await page.getByText('Copied ✓').waitFor({ timeout: 5000 })
const clip = await page.evaluate(() => navigator.clipboard.readText())
const lines = clip.split('\n')
check(lines.length === 10, `clipboard has one line per incident (got ${lines.length})`)
check(lines[0].startsWith('[P1]'), 'P1 incidents first')
check(await page.getByText('Coming Soon').count() === 0, 'no coming-soon modal')
check(await page.getByText('RAG Recall@k').count() === 0 && await page.getByText('LLM Comparison').count() === 0, 'weak recall panel and dead comparison panel removed')
const objects = await page.locator('table').filter({ hasText: 'SF OBJECT' }).locator('tbody tr').count().catch(() => 0)
const objText = await page.getByText('By Object').locator('xpath=../..').textContent()
check(['Contact', 'FinancialAccount__c', 'KYC_Record__c', 'Address__c'].every(o => objText.includes(o)), `by-object lists the real objects (${objects} rows)`)

// Analytics + benchmark render
await page.goto(`${BASE}/analytics`)
await page.waitForTimeout(1500)
await page.goto(`${BASE}/benchmark`)
await page.getByRole('heading', { name: 'Eval results' }).waitFor({ timeout: 10000 }).catch(() => {})
check(await page.getByRole('heading', { name: 'Eval results' }).count() === 1, 'benchmark page renders from eval results')
check(await page.getByTestId('app-bar').count() === 0, 'benchmark is standalone (no app header)')
check(await page.getByText('Delivery-first + noise').count() === 1, 'benchmark leads with the ablation')
await page.goto(`${BASE}/hypotheses`)
await page.getByText('What gets checked, and in what order').waitFor({ timeout: 10000 })
check(await page.locator('[data-testid="catalogue-row"]').count() === 15, 'hypotheses page lists all 15 checks')

// Mobile: no horizontal scroll on the six routes
const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } })
await mobile.addInitScript(() => localStorage.setItem('recon_access', 'granted'))
const m = await mobile.newPage()
for (const path of ['/', '/upload', '/hypotheses', `/runs/${runId}`, `/runs/${runId}/summary`, '/analytics', '/benchmark',
  `/runs/${runId}/incidents/${phone.id}`]) {
  await m.goto(`${BASE}${path}`)
  await m.waitForTimeout(1200)
  const over = await m.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check(over <= 0, `390px: no horizontal scroll on ${path} (overflow ${over}px)`)
}

check(consoleErrors.length === 0, `no console errors (${consoleErrors.slice(0, 3).join(' | ')})`)
await browser.close()
console.log(failures ? `\n${failures} check(s) failed` : '\nall checks passed')
process.exit(failures ? 1 : 0)

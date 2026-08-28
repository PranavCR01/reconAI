import { Link } from 'react-router-dom'

/* ── Design-system colours (mirrors CSS vars for inline use) ── */
const C = {
  bg:       'oklch(0.16 0.006 250)',
  bg1:      'oklch(0.19 0.006 250)',
  bg2:      'oklch(0.22 0.007 250)',
  bg3:      'oklch(0.26 0.008 250)',
  line:     'oklch(0.30 0.008 250)',
  lineSoft: 'oklch(0.25 0.007 250)',
  fg:       'oklch(0.96 0.005 250)',
  fg1:      'oklch(0.82 0.006 250)',
  fg2:      'oklch(0.66 0.008 250)',
  fg3:      'oklch(0.50 0.008 250)',
  ok:       'oklch(0.74 0.16 155)',
  info:     'oklch(0.74 0.12 220)',
  violet:   'oklch(0.72 0.14 295)',
  accent:   'oklch(0.42 0.10 220)',
  accentBd: 'oklch(0.55 0.13 220)',
  accentFg: 'oklch(0.97 0.02 220)',
}

/* ── BrandMark (matches existing BrandMark.tsx) ── */
function LandingMark({ size = 24 }: { size?: number }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: Math.round(size * 0.23),
      background: 'linear-gradient(135deg, oklch(0.55 0.14 250), oklch(0.42 0.12 295))',
      boxShadow: 'inset 0 0 0 1px oklch(0.70 0.10 250 / 0.3)',
      display: 'inline-grid', placeItems: 'center', position: 'relative', flexShrink: 0,
    }}>
      <span style={{
        position: 'absolute',
        inset: Math.round(size * 0.22),
        borderRadius: 2,
        border: '1.5px solid var(--fg)',
        borderRight: '1.5px solid transparent',
        borderBottom: '1.5px solid transparent',
        transform: 'rotate(45deg)',
      }} />
    </span>
  )
}

/* ── Section label (monospace uppercase with left accent bar) ── */
function SectionLabel({ children }: { children: string }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 10,
      font: `600 11px var(--mono)`,
      textTransform: 'uppercase', letterSpacing: '0.12em',
      color: C.fg3,
    }}>
      <span style={{ width: 3, height: 14, borderRadius: 2, background: C.info, flexShrink: 0 }} />
      {children}
    </div>
  )
}

export default function Landing() {
  return (
    <>
      {/* ── Responsive + hover styles ── */}
      <style>{`
        html { scroll-behavior: smooth; }

        .land-btn-primary {
          display: inline-flex; align-items: center; gap: 8px;
          height: 42px; padding: 0 20px; border-radius: 7px;
          font: 600 14px var(--sans);
          background: oklch(0.42 0.10 220);
          border: 1px solid oklch(0.55 0.13 220);
          color: oklch(0.97 0.02 220);
          text-decoration: none; cursor: pointer;
          transition: background 0.15s;
          box-shadow: inset 0 1px 0 oklch(0.65 0.13 220 / 0.3);
        }
        .land-btn-primary:hover { background: oklch(0.47 0.11 220); }

        .land-btn-ghost {
          display: inline-flex; align-items: center; gap: 8px;
          height: 42px; padding: 0 20px; border-radius: 7px;
          font: 600 14px var(--sans);
          background: transparent;
          border: 1px solid var(--line);
          color: var(--fg-1);
          text-decoration: none; cursor: pointer;
          transition: background 0.15s, border-color 0.15s;
        }
        .land-btn-ghost:hover { background: var(--bg-2); border-color: oklch(0.38 0.008 250); }

        .land-btn-sm {
          display: inline-flex; align-items: center; gap: 6px;
          height: 32px; padding: 0 14px; border-radius: 6px;
          font: 500 12px var(--mono);
          background: transparent;
          border: 1px solid var(--line);
          color: var(--fg-2);
          text-decoration: none; cursor: pointer;
          transition: background 0.12s, color 0.12s;
        }
        .land-btn-sm:hover { background: var(--bg-2); color: var(--fg); }

        .land-nav-cta {
          display: inline-flex; align-items: center; gap: 6px;
          height: 30px; padding: 0 14px; border-radius: 6px;
          font: 500 12.5px var(--sans);
          background: var(--bg-2); border: 1px solid var(--line);
          color: var(--fg-1); text-decoration: none;
          transition: background 0.12s;
        }
        .land-nav-cta:hover { background: var(--bg-3); }

        .land-stat-card {
          background: var(--bg-1);
          border: 1px solid var(--line);
          border-radius: 10px;
          padding: 28px 24px;
          transition: border-color 0.15s;
        }
        .land-stat-card:hover { border-color: oklch(0.38 0.010 250); }

        .land-arch-card {
          background: var(--bg-1);
          border: 1px solid var(--line);
          border-radius: 10px;
          padding: 20px 22px;
          transition: border-color 0.15s, background 0.15s;
        }
        .land-arch-card:hover { border-color: oklch(0.38 0.010 250); background: var(--bg-2); }

        .land-link-btn:hover { background: var(--bg-2); color: var(--fg); }

        /* Responsive */
        @media (max-width: 768px) {
          .land-hero-btns { flex-direction: column !important; align-items: flex-start !important; }
          .land-stat-grid { grid-template-columns: 1fr !important; }
          .land-steps-grid { grid-template-columns: 1fr !important; gap: 0 !important; }
          .land-step-connector { display: none !important; }
          .land-arch-grid { grid-template-columns: 1fr !important; }
          .land-links-row { flex-wrap: wrap !important; }
          .land-hero-headline { font-size: 32px !important; }
          .land-section { padding: 56px 20px !important; }
          .land-hero { padding: 40px 20px 60px !important; }
          .land-hero-inner { max-width: 100% !important; }
          .land-by-name { font-size: 32px !important; }
        }
      `}</style>

      <div style={{ background: C.bg, color: C.fg, fontFamily: 'var(--sans)', fontSize: 13, lineHeight: 1.5, WebkitFontSmoothing: 'antialiased', minHeight: '100vh' }}>

        {/* ═══════════════════════════════════════════════
            SECTION 1 — HERO
        ═══════════════════════════════════════════════ */}
        <section
          className="land-hero"
          id="hero"
          style={{
            minHeight: '100vh',
            display: 'flex', flexDirection: 'column',
            padding: '0 32px 80px',
            position: 'relative', overflow: 'hidden',
            /* Dot grid */
            backgroundImage: `
              radial-gradient(circle, oklch(0.30 0.008 250) 1px, transparent 1px),
              radial-gradient(circle at 20% -10%, oklch(0.25 0.04 250 / 0.45), transparent 50%),
              radial-gradient(circle at 85% 105%, oklch(0.24 0.05 295 / 0.30), transparent 50%)
            `,
            backgroundSize: '24px 24px, 100% 100%, 100% 100%',
          }}
        >
          {/* Top nav */}
          <nav style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            height: 60, flexShrink: 0,
          }}>
            <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
              <LandingMark size={22} />
              <span style={{ fontSize: 14, fontWeight: 600 }}>
                <b style={{ color: C.fg }}>reconAI</b>
              </span>
            </Link>
            <Link to="/upload" className="land-nav-cta">Open app →</Link>
          </nav>

          {/* Center content */}
          <div className="land-hero-inner" style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            justifyContent: 'center', alignItems: 'flex-start',
            maxWidth: 680, paddingTop: 48, paddingBottom: 48,
          }}>
            {/* Eyebrow */}
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              height: 26, padding: '0 12px', borderRadius: 6,
              background: C.bg2, border: `1px solid ${C.line}`,
              font: `500 11.5px var(--mono)`, color: C.fg3,
              marginBottom: 24, letterSpacing: '0.04em',
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.info, boxShadow: `0 0 0 3px oklch(0.74 0.12 220 / 0.2)` }} />
              Salesforce FSC · Integration Observability
            </div>

            {/* Headline */}
            <h1
              className="land-hero-headline"
              style={{
                margin: '0 0 20px',
                fontSize: 48, fontWeight: 700, letterSpacing: '-0.025em',
                lineHeight: 1.1, color: C.fg,
                maxWidth: 660,
              }}
            >
              Your Recon team spends 3 hours every morning on integration failures.
            </h1>

            {/* Sub */}
            <p style={{
              margin: '0 0 36px',
              fontSize: 18, fontWeight: 400,
              color: C.fg2, lineHeight: 1.6,
              maxWidth: 560,
            }}>
              ReconAI diagnoses root causes in just a couple of minutes — with cited evidence,
              suggested fixes, and a postmortem draft ready to send.
            </p>

            {/* CTAs */}
            <div className="land-hero-btns" style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <Link to="/upload" className="land-btn-primary">
                Run your first recon →
              </Link>
              <Link to="/analytics" className="land-btn-ghost">
                View analytics →
              </Link>
              <Link to="/benchmark" className="land-btn-ghost">
                Benchmark results →
              </Link>
            </div>
          </div>

          {/* Scroll indicator */}
          <div style={{
            display: 'flex', justifyContent: 'center',
            paddingBottom: 16,
          }}>
            <a href="#problem" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, textDecoration: 'none', color: C.fg3 }}>
              <span style={{ font: `500 10.5px var(--mono)`, letterSpacing: '0.10em', textTransform: 'uppercase' }}>scroll</span>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M8 3v10M4 9l4 4 4-4" />
              </svg>
            </a>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════
            SECTION 2 — THE PROBLEM
        ═══════════════════════════════════════════════ */}
        <section
          id="problem"
          className="land-section"
          style={{ padding: '80px 32px', background: C.bg1, borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }}
        >
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>The Problem</SectionLabel>
            <h2 style={{ margin: '16px 0 48px', fontSize: 28, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              What breaks every morning
            </h2>

            <div
              className="land-stat-grid"
              style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}
            >
              {[
                {
                  num: '3 hrs',
                  label: 'Avg time spent correlating SF↔DB2 discrepancies manually each morning',
                  color: 'oklch(0.65 0.20 25)',
                },
                {
                  num: '47 fields',
                  label: 'Avg fields checked per discrepancy across FLS, CDC, and transform logs',
                  color: 'oklch(0.78 0.15 75)',
                },
                {
                  num: 'Zero postmortem',
                  label: 'Manual recon produces no audit trail, no fix record, no pattern history',
                  color: C.fg3,
                },
              ].map(({ num, label, color }) => (
                <div key={num} className="land-stat-card">
                  <div style={{
                    font: `700 36px var(--mono)`, color,
                    letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 14,
                  }}>
                    {num}
                  </div>
                  <div style={{ fontSize: 13.5, color: C.fg2, lineHeight: 1.6 }}>{label}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════
            SECTION 3 — HOW IT WORKS
        ═══════════════════════════════════════════════ */}
        <section
          id="how"
          className="land-section"
          style={{ padding: '80px 32px', background: C.bg }}
        >
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>How It Works</SectionLabel>
            <h2 style={{ margin: '16px 0 56px', fontSize: 28, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              From CSV to root cause in three steps
            </h2>

            <div style={{ position: 'relative' }}>
              {/* Connector line */}
              <div
                className="land-step-connector"
                style={{
                  position: 'absolute', top: 28, left: '16.5%', right: '16.5%',
                  height: 1, background: `linear-gradient(90deg, transparent, ${C.line} 15%, ${C.line} 85%, transparent)`,
                  zIndex: 0,
                }}
              />

              <div
                className="land-steps-grid"
                style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 32, position: 'relative', zIndex: 1 }}
              >
                {[
                  {
                    n: '01',
                    title: 'Upload',
                    body: 'Drop your daily recon CSV. ReconAI parses SF object, field, and DB2 column mappings automatically.',
                  },
                  {
                    n: '02',
                    title: 'Analyze',
                    body: 'A LangGraph hypothesis graph tests FLS permissions, CDC channel config, DataWeave transforms, and Apex triggers — in parallel, with real tool calls.',
                  },
                  {
                    n: '03',
                    title: 'Fix',
                    body: 'Every incident gets cited evidence, a suggested fix, a postmortem draft, and a Jira summary. Ready to action in one click.',
                  },
                ].map(({ n, title, body }) => (
                  <div key={n} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                    {/* Step number with circle bg */}
                    <div style={{
                      width: 56, height: 56, borderRadius: '50%',
                      background: C.bg1, border: `1px solid ${C.line}`,
                      display: 'grid', placeItems: 'center',
                      marginBottom: 20, flexShrink: 0,
                    }}>
                      <span style={{ font: `700 14px var(--mono)`, color: C.info, letterSpacing: '-0.01em' }}>{n}</span>
                    </div>
                    <h3 style={{ margin: '0 0 10px', fontSize: 18, fontWeight: 700, letterSpacing: '-0.01em', color: C.fg }}>{title}</h3>
                    <p style={{ margin: 0, fontSize: 13.5, color: C.fg2, lineHeight: 1.65 }}>{body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════
            SECTION 4 — ARCHITECTURE
        ═══════════════════════════════════════════════ */}
        <section
          id="arch"
          className="land-section"
          style={{ padding: '80px 32px', background: C.bg1, borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }}
        >
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Under the Hood</SectionLabel>
            <h2 style={{ margin: '16px 0 8px', fontSize: 28, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              Built for Salesforce FSC integrations
            </h2>
            <p style={{ margin: '0 0 48px', fontSize: 14.5, color: C.fg2, maxWidth: 580, lineHeight: 1.6 }}>
              Built on the same multi-agent architecture as Microsoft RCACopilot —
              purpose-built for Salesforce FSC↔DB2 reconciliation pipelines.
            </p>

            <div
              className="land-arch-grid"
              style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}
            >
              {[
                {
                  title: 'LangGraph hypothesis graph',
                  detail: 'H1 DB2 history · H2 Splunk triage · H3a FLS · H3b CDC · H3c Apex · H4 transform · H5 RAG fallback',
                  color: C.info,
                },
                {
                  title: 'pgvector RAG',
                  detail: '23 FSC seed artifacts · HNSW similarity search · temporal weighting · LLM reranker',
                  color: C.ok,
                },
                {
                  title: 'Claude Sonnet synthesis',
                  detail: 'Cited evidence not hallucination · confidence calibration · postmortem generation',
                  color: C.violet,
                },
                {
                  title: 'Real-time SSE streaming',
                  detail: 'Incidents analyzed as they arrive · P1 prioritized · early termination on confirmation',
                  color: 'oklch(0.78 0.15 75)',
                },
              ].map(({ title, detail, color }) => (
                <div key={title} className="land-arch-card">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                    <span style={{ font: `600 13.5px var(--sans)`, color: C.fg }}>{title}</span>
                  </div>
                  <div style={{ font: `500 11.5px var(--mono)`, color: C.fg3, lineHeight: 1.7 }}>{detail}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════
            SECTION 5 — BUILT BY
        ═══════════════════════════════════════════════ */}
        <section
          id="about"
          className="land-section"
          style={{ padding: '80px 32px 64px', background: C.bg }}
        >
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Built By</SectionLabel>

            <h2
              className="land-by-name"
              style={{ margin: '16px 0 8px', fontSize: 40, fontWeight: 700, letterSpacing: '-0.02em', color: C.fg }}
            >
              Pranav Charakondala
            </h2>
            <p style={{ margin: '0 0 36px', fontSize: 14, color: C.fg2, lineHeight: 1.6 }}>
              Graduate Researcher · UIUC Information Management · ex-Deloitte Analyst · ML Intern at Drongo AI
            </p>

            <div className="land-links-row" style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 32 }}>
              {[
                { label: '→ LinkedIn', href: 'https://www.linkedin.com/in/pranav-c-r-852752202/' },
                { label: '→ Portfolio', href: 'https://pranavcr01.github.io/' },
                { label: '→ GitHub', href: 'https://github.com/PranavCR01' },
                { label: '→ Research Notes', href: 'https://www.notion.so/ReconAI-Research-Architecture-Notes-358a47a2b4cf8000944fefad0ddf1349?source=copy_link' },
                { label: '→ Dev Journal', href: 'https://www.notion.so/ReconAI-Project-Arc-358a47a2b4cf8004a38bee6d50283911?source=copy_link' },
                { label: '→ Demo', href: 'https://www.youtube.com/watch?v=cEzxQ1xfltU' },
              ].map(({ label, href }) => (
                <a
                  key={label}
                  href={href}
                  target={href.startsWith('http') ? '_blank' : undefined}
                  rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  className="land-btn-sm"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    height: 32, padding: '0 14px', borderRadius: 6,
                    font: `500 12px var(--mono)`,
                    background: 'transparent', border: `1px solid ${C.line}`,
                    color: C.fg2, textDecoration: 'none',
                    transition: 'background 0.12s, color 0.12s',
                  }}
                >
                  {label}
                </a>
              ))}
            </div>

            <p style={{ margin: 0, fontSize: 12.5, color: C.fg3, maxWidth: 520, lineHeight: 1.7, fontFamily: 'var(--mono)' }}>
              ReconAI is a portfolio project demonstrating production AI engineering
              patterns for Salesforce FSC integration observability. Built at UIUC
              Information Management, 2026.
            </p>
          </div>
        </section>

        {/* ═══════════════════════════════════════════════
            FOOTER
        ═══════════════════════════════════════════════ */}
        <footer style={{
          borderTop: `1px solid ${C.line}`,
          padding: '20px 32px',
          background: C.bg1,
          textAlign: 'center',
          font: `500 11px var(--mono)`,
          color: C.fg3,
          letterSpacing: '0.03em',
        }}>
          reconAI · LangGraph · Claude API · Supabase pgvector · UIUC 2026
        </footer>

      </div>
    </>
  )
}

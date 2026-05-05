import { useState, useRef, useEffect, useCallback } from 'react'
import type { DragEvent, ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import Papa from 'papaparse'
import { createRun } from '@/lib/api'
import { useReconStore, getRunHistory, saveRunToHistory } from '@/store/reconStore'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { StatusPill } from '@/components/ui/StatusPill'
import { fmtDate } from '@/lib/format'
import type { Environment, LlmConfig, RunHistoryEntry } from '@/types'
import type { SegOption } from '@/components/ui/SegmentedControl'

// ---- helpers ----------------------------------------------------------------

function hashInt(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

function sparkHeights(id: string): number[] {
  const h = hashInt(id)
  return Array.from({ length: 8 }, (_, i) => Math.max(0.12, ((h >> (i * 3)) & 0x7) / 7))
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const m = Math.floor(ms / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const STATUS_VARIANT: Record<RunHistoryEntry['status'], 'queued' | 'analyzing' | 'ok' | 'fail'> = {
  pending: 'queued',
  running: 'analyzing',
  complete: 'ok',
  error: 'fail',
}

// ---- shared inline-button style ---------------------------------------------

const btnBase: React.CSSProperties = {
  height: 34,
  padding: '0 14px',
  borderRadius: 6,
  fontFamily: 'var(--sans)',
  fontSize: 12.5,
  fontWeight: 500,
  background: 'var(--bg-2)',
  border: '1px solid var(--line)',
  color: 'var(--fg-1)',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
}

// ---- component --------------------------------------------------------------

export default function Upload() {
  const navigate = useNavigate()
  const store = useReconStore()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [rowCount, setRowCount] = useState<number | null>(null)
  const [env, setEnv] = useState<Environment>('PROD')
  const [model, setModel] = useState<LlmConfig>('claude')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<RunHistoryEntry[]>([])

  useEffect(() => {
    setHistory(getRunHistory().slice(0, 3))
  }, [])

  function parseFile(f: File) {
    Papa.parse(f, {
      header: true,
      skipEmptyLines: true,
      complete: (result) => setRowCount(result.data.length),
    })
  }

  const onDragEnter = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])
  const onDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }, [])
  const onDragLeave = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])
  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) {
      setFile(f)
      parseFile(f)
    }
  }, [])

  function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) {
      setFile(f)
      parseFile(f)
    }
  }

  async function loadSampleData() {
    try {
      const res = await fetch('/sample_fsc_recon.csv')
      const text = await res.text()
      const result = Papa.parse(text, { header: true, skipEmptyLines: true })
      const rows = result.data.length
      const blob = new Blob([text], { type: 'text/csv' })
      const f = new File([blob], 'sample_fsc_recon.csv', { type: 'text/csv' })
      setFile(f)
      setRowCount(rows)
    } catch (err) {
      console.error('Failed to load sample data:', err)
    }
  }

  async function handleStartAnalysis() {
    if (!file || loading) return
    setLoading(true)
    try {
      const res = await createRun(file, { environment: env })
      const entry: RunHistoryEntry = {
        runId: res.run_id,
        createdAt: new Date().toISOString(),
        environment: env,
        sfOrgId: 'sf-demo-org',
        rowCount: res.rows_accepted,
        status: 'running',
      }
      saveRunToHistory(entry)
      store.resetRun()
      store.setRunId(res.run_id)
      store.setEnvironment(env)
      store.setLlmConfig(model)
      navigate(`/runs/${res.run_id}`)
    } catch (err) {
      console.error('Failed to start run:', err)
    } finally {
      setLoading(false)
    }
  }

  const modelLabel = {
    claude: 'claude-sonnet-4.5',
    groq: 'groq-llama-3.3-70b',
    hybrid: 'hybrid (groq→claude)',
  }[model]

  const envOptions: SegOption[] = [
    {
      value: 'PROD',
      label: (
        <>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              flexShrink: 0,
              background: env === 'PROD' ? 'var(--p1)' : 'var(--fg-3)',
              boxShadow: env === 'PROD' ? '0 0 0 3px oklch(0.65 0.20 25 / 0.18)' : undefined,
            }}
          />
          PROD
        </>
      ),
      sub: 'db2-fsc-prod-01',
    },
    {
      value: 'UAT',
      label: (
        <>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              flexShrink: 0,
              background: env === 'UAT' ? 'var(--info)' : 'var(--fg-3)',
              boxShadow: env === 'UAT' ? '0 0 0 3px oklch(0.74 0.12 220 / 0.18)' : undefined,
            }}
          />
          UAT
        </>
      ),
      sub: 'db2-fsc-uat-02',
    },
  ]

  const modelOptions: SegOption[] = [
    { value: 'claude', label: 'Claude', sub: 'sonnet-4.5' },
    { value: 'groq', label: 'Groq', sub: 'llama-3.3-70b' },
    { value: 'hybrid', label: 'Hybrid', sub: 'groq → claude' },
  ]

  const canStart = !!file && !loading

  return (
    <div style={{ maxWidth: 940, margin: '0 auto', padding: '36px 24px 80px' }}>

      {/* ---- Page head ---- */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em' }}>
            New reconciliation run
          </h1>
          <div style={{ color: 'var(--fg-3)', fontSize: 12.5, fontFamily: 'var(--mono)', marginTop: 3 }}>
            Compare a Salesforce FSC export against the DB2 system of record.
          </div>
        </div>
        <div style={{ marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--fg-3)' }}>
          ready · agent-pool-3 · 12 workers idle
        </div>
      </div>

      {/* ---- Drop zone ---- */}
      <div
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        style={{
          position: 'relative',
          background: isDragging ? 'oklch(0.22 0.04 220 / 0.4)' : 'var(--bg-1)',
          border: `1.5px dashed ${isDragging ? 'var(--info)' : 'var(--line)'}`,
          borderRadius: 12,
          padding: '44px 32px 36px',
          textAlign: 'center',
          transition: 'border-color 0.15s, background 0.15s',
          overflow: 'hidden',
        }}
      >
        {/* Upload icon */}
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: 12,
            margin: '0 auto 16px',
            background: 'var(--bg-2)',
            border: '1px solid var(--line)',
            display: 'grid',
            placeItems: 'center',
            color: 'var(--info)',
            boxShadow: 'inset 0 0 0 4px oklch(0.20 0.006 250)',
          }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
            <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
          </svg>
        </div>

        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>Drop your FSC export here</div>
        <div style={{ color: 'var(--fg-2)', fontSize: 13, marginBottom: 18 }}>
          CSV exported from Salesforce FSC · or <b style={{ color: 'var(--fg-1)' }}>click to browse</b>
        </div>

        {/* Browse / SFDX buttons */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginBottom: 18 }}>
          <label style={btnBase}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 4h10v9H3zM3 7h10" />
            </svg>
            Browse files
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={onFileChange}
            />
          </label>
          <button style={{ ...btnBase, background: 'transparent' }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="8" cy="8" r="6" />
              <path d="M8 5v3l2 2" />
            </svg>
            Connect via SFDX
          </button>
        </div>

        {/* File spec */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 14,
            padding: '8px 14px',
            borderRadius: 8,
            background: 'var(--bg-2)',
            border: '1px solid var(--line-soft)',
            color: 'var(--fg-3)',
            fontFamily: 'var(--mono)',
            fontSize: 11.5,
            fontWeight: 500,
          }}
        >
          <span>
            <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>.csv</b> only
          </span>
          <span style={{ color: 'oklch(0.34 0.008 250)' }}>·</span>
          <span>
            max <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>500 MB</b>
          </span>
          <span style={{ color: 'oklch(0.34 0.008 250)' }}>·</span>
          <span>UTF-8 · RFC 4180</span>
          <span style={{ color: 'oklch(0.34 0.008 250)' }}>·</span>
          <span>
            required cols:{' '}
            <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>Id, Object, Field, Value, LastModifiedDate</b>
          </span>
        </div>

        {/* OR divider */}
        <div
          style={{
            margin: '18px 0 14px',
            color: 'var(--fg-3)',
            fontFamily: 'var(--mono)',
            fontSize: 10.5,
            fontWeight: 500,
            textTransform: 'uppercase',
            letterSpacing: '0.18em',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span style={{ flex: 1, height: 1, background: 'var(--line)' }} />
          or
          <span style={{ flex: 1, height: 1, background: 'var(--line)' }} />
        </div>

        {/* Sample data button */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
          <button onClick={loadSampleData} style={btnBase}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="2" y="3" width="12" height="10" rx="1" />
              <path d="M2 6h12M5 3v10" />
            </svg>
            Use sample FSC data
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-3)', marginLeft: 4 }}>
              10 rows · 4 objects
            </span>
          </button>
        </div>

        {/* File-loaded indicator */}
        {file && rowCount !== null && (
          <div
            style={{
              marginTop: 16,
              padding: '10px 16px',
              borderRadius: 8,
              background: 'oklch(0.28 0.06 220 / 0.4)',
              border: '1px solid oklch(0.40 0.08 220)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 10,
              color: 'oklch(0.85 0.10 220)',
              fontFamily: 'var(--mono)',
              fontSize: 12,
            }}
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              style={{ flexShrink: 0 }}
            >
              <path d="M3 8l4 4 6-7" />
            </svg>
            <span style={{ fontWeight: 500 }}>{file.name}</span>
            <span style={{ color: 'oklch(0.55 0.06 220)' }}>·</span>
            <span style={{ fontWeight: 600, color: 'oklch(0.92 0.12 220)' }}>
              {rowCount.toLocaleString()} rows
            </span>
            <button
              onClick={() => {
                setFile(null)
                setRowCount(null)
              }}
              style={{
                marginLeft: 4,
                background: 'transparent',
                border: 'none',
                color: 'oklch(0.55 0.06 220)',
                cursor: 'pointer',
                fontSize: 13,
                padding: '0 2px',
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* ---- Config block ---- */}
      <section
        style={{
          marginTop: 22,
          background: 'var(--bg-1)',
          border: '1px solid var(--line)',
          borderRadius: 12,
          overflow: 'hidden',
        }}
      >
        {/* Config header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '12px 16px',
            borderBottom: '1px solid var(--line)',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 11,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--fg-2)',
            }}
          >
            Run Configuration
          </span>
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--mono)',
              fontSize: 11,
              fontWeight: 500,
              color: 'var(--fg-3)',
            }}
          >
            presets · default-fsc-recon-v3
          </span>
        </div>

        {/* Config grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 1,
            background: 'var(--line)',
          }}
        >
          {/* Environment */}
          <div
            style={{
              background: 'var(--bg-1)',
              padding: '16px 18px',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 11,
                fontWeight: 500,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--fg-3)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              Environment
              <span
                style={{
                  fontFamily: 'var(--sans)',
                  textTransform: 'none',
                  letterSpacing: 0,
                  fontWeight: 400,
                  color: 'var(--fg-3)',
                }}
              >
                — which DB2 instance to compare against
              </span>
            </span>
            <SegmentedControl
              options={envOptions}
              value={env}
              onChange={(v) => setEnv(v as Environment)}
              size="lg"
              fullWidth
            />
            <div
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 11,
                fontWeight: 500,
                color: 'var(--fg-3)',
                display: 'flex',
                gap: 12,
              }}
            >
              <span>
                region <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>us-east-1</b>
              </span>
              <span>
                conn <b style={{ color: 'var(--ok)' }}>●</b> 31ms
              </span>
              <span>
                last sync <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>2026-05-03 01:02Z</b>
              </span>
            </div>
          </div>

          {/* LLM Model */}
          <div
            style={{
              background: 'var(--bg-1)',
              padding: '16px 18px',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 11,
                fontWeight: 500,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--fg-3)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              LLM Model
              <span
                style={{
                  fontFamily: 'var(--sans)',
                  textTransform: 'none',
                  letterSpacing: 0,
                  fontWeight: 400,
                  color: 'var(--fg-3)',
                }}
              >
                — agent backbone for hypothesis &amp; root-cause
              </span>
            </span>
            <SegmentedControl
              options={modelOptions}
              value={model}
              onChange={(v) => setModel(v as LlmConfig)}
              size="lg"
              fullWidth
            />
            <div
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 11,
                fontWeight: 500,
                color: 'var(--fg-3)',
                display: 'flex',
                gap: 12,
              }}
            >
              <span>
                est. cost <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>~$0.18 / incident</b>
              </span>
              <span>
                est. p50 latency <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>42s</b>
              </span>
              <span>
                budget cap <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>$5.00</b>
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Action bar ---- */}
      <div
        style={{
          marginTop: 22,
          background: 'var(--bg-1)',
          border: '1px solid var(--line)',
          borderRadius: 12,
          padding: '14px 18px',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <div
          style={{
            display: 'flex',
            gap: 18,
            fontFamily: 'var(--mono)',
            fontSize: 11.5,
            fontWeight: 500,
            color: 'var(--fg-3)',
            flexWrap: 'wrap',
          }}
        >
          <span>
            <span style={{ color: file ? 'var(--ok)' : 'var(--fg-3)' }}>●</span>{' '}
            {file ? 'ready' : 'no file queued'} ·{' '}
            <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>{file ? '1' : '0'}</b> files queued
          </span>
          <span style={{ color: 'oklch(0.34 0.008 250)' }}>|</span>
          <span>
            env <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>{env}</b>
          </span>
          <span>
            model <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>{modelLabel}</b>
          </span>
          <span>
            integrations <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>4</b>
          </span>
          <span>
            thresholds <b style={{ color: 'var(--fg-1)', fontWeight: 500 }}>default</b>
          </span>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10 }}>
          <button
            style={{
              height: 40,
              padding: '0 18px',
              borderRadius: 6,
              fontFamily: 'var(--sans)',
              fontSize: 13.5,
              fontWeight: 600,
              background: 'var(--bg-2)',
              border: '1px solid var(--line)',
              color: 'var(--fg-1)',
              cursor: 'pointer',
            }}
          >
            Save preset
          </button>
          <button
            onClick={handleStartAnalysis}
            disabled={!canStart}
            style={{
              height: 40,
              padding: '0 18px',
              borderRadius: 6,
              fontFamily: 'var(--sans)',
              fontSize: 13.5,
              fontWeight: 600,
              background: 'oklch(0.42 0.10 220)',
              border: '1px solid oklch(0.55 0.13 220)',
              color: 'oklch(0.97 0.02 220)',
              boxShadow: canStart ? 'inset 0 1px 0 oklch(0.65 0.13 220 / 0.3)' : undefined,
              cursor: canStart ? 'pointer' : 'not-allowed',
              opacity: canStart ? 1 : 0.5,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            {loading ? 'Starting…' : 'Start Analysis'}
            {!loading && (
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7">
                <path d="M5 3l7 5-7 5V3z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* ---- Recent runs ---- */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '36px 0 12px' }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, letterSpacing: '-0.005em', margin: 0 }}>Recent runs</h2>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 500, color: 'var(--fg-3)' }}>
          last {history.length || 0} ·{' '}
          <a
            href="#"
            style={{
              color: 'var(--info)',
              textDecoration: 'none',
              fontFamily: 'var(--mono)',
              fontSize: 11,
              fontWeight: 500,
            }}
          >
            view all →
          </a>
        </span>
        <div style={{ marginLeft: 'auto' }}>
          <button
            onClick={() => setHistory(getRunHistory().slice(0, 3))}
            style={btnBase}
          >
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 8a6 6 0 11-1.76-4.24L14 5" />
              <path d="M14 2v3h-3" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Runs table */}
      <div
        style={{
          background: 'var(--bg-1)',
          border: '1px solid var(--line)',
          borderRadius: 12,
          overflow: 'hidden',
        }}
      >
        {/* Table header */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '2.4fr 1.2fr 0.8fr 1fr 0.8fr 1fr 0.6fr',
            alignItems: 'center',
            padding: '10px 18px',
            gap: 14,
            background: 'var(--bg)',
            fontFamily: 'var(--mono)',
            fontSize: 10.5,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--fg-3)',
          }}
        >
          <div>Run ID</div>
          <div>Started</div>
          <div>Env</div>
          <div>Rows</div>
          <div>P1</div>
          <div>Status</div>
          <div />
        </div>

        {/* Empty state */}
        {history.length === 0 && (
          <div
            style={{
              padding: '28px 18px',
              textAlign: 'center',
              color: 'var(--fg-3)',
              fontFamily: 'var(--mono)',
              fontSize: 12,
            }}
          >
            No runs yet · start your first analysis above
          </div>
        )}

        {/* Rows */}
        {history.map((run, idx) => {
          const heights = sparkHeights(run.runId)
          const statusVariant = STATUS_VARIANT[run.status] ?? 'queued'
          const isProd = run.environment === 'PROD'

          return (
            <div
              key={run.runId}
              onClick={() => navigate(`/runs/${run.runId}`)}
              style={{
                display: 'grid',
                gridTemplateColumns: '2.4fr 1.2fr 0.8fr 1fr 0.8fr 1fr 0.6fr',
                alignItems: 'center',
                padding: '12px 18px',
                gap: 14,
                borderTop: '1px solid var(--line-soft)',
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-2)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              {/* Run ID */}
              <div
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 12.5,
                  fontWeight: 500,
                  color: 'var(--fg)',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  minWidth: 0,
                }}
              >
                <span style={{ color: 'var(--fg-3)', marginTop: 1 }}>›</span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {run.runId}
                  </span>
                  <small
                    style={{
                      display: 'block',
                      color: 'var(--fg-3)',
                      fontWeight: 400,
                      fontSize: 10.5,
                      marginTop: 1,
                    }}
                  >
                    {run.integrationName ?? run.sfOrgId} · {run.rowCount.toLocaleString()} rows accepted
                  </small>
                </span>
              </div>

              {/* Started */}
              <div style={{ fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 500, color: 'var(--fg-1)' }}>
                {fmtDate(run.createdAt)}
                <div style={{ color: 'var(--fg-3)', fontSize: 10.5, marginTop: 2 }}>{timeAgo(run.createdAt)}</div>
              </div>

              {/* Env */}
              <div>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    fontFamily: 'var(--mono)',
                    fontSize: 11,
                    fontWeight: 500,
                    color: isProd ? 'oklch(0.85 0.10 25)' : 'oklch(0.85 0.08 220)',
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: isProd ? 'var(--p1)' : 'var(--info)',
                      boxShadow: isProd
                        ? '0 0 0 3px oklch(0.65 0.20 25 / 0.18)'
                        : '0 0 0 3px oklch(0.74 0.12 220 / 0.18)',
                    }}
                  />
                  {run.environment}
                </span>
              </div>

              {/* Rows + sparkline */}
              <div>
                <span
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'var(--fg)',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {run.rowCount.toLocaleString()}
                </span>
                <div
                  style={{
                    height: 18,
                    display: 'flex',
                    gap: 1.5,
                    alignItems: 'flex-end',
                    width: 90,
                    marginTop: 4,
                  }}
                >
                  {heights.map((h, i) => (
                    <div
                      key={i}
                      style={{
                        flex: 1,
                        height: `${h * 100}%`,
                        background: h > 0.65 ? 'var(--p1)' : h > 0.35 ? 'var(--p2)' : 'var(--bg-3)',
                        borderRadius: 1,
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* P1 pill */}
              <div>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    height: 22,
                    padding: '0 8px',
                    borderRadius: 4,
                    fontFamily: 'var(--mono)',
                    fontSize: 11,
                    fontWeight: 600,
                    background: 'var(--bg-2)',
                    color: 'var(--fg-2)',
                    border: '1px solid var(--line)',
                  }}
                >
                  ● 0
                </span>
              </div>

              {/* Status */}
              <div>
                <StatusPill variant={statusVariant} />
              </div>

              {/* Action */}
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <span
                  style={{
                    color: 'var(--fg-3)',
                    fontFamily: 'var(--mono)',
                    fontSize: 11.5,
                    fontWeight: 500,
                  }}
                >
                  open →
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

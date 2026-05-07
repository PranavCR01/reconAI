import { create } from 'zustand'
import type { RCAIncident, LlmConfig, Environment, RunStatus, RunHistoryEntry } from '@/types'

interface RunStats {
  total: number
  resolved: number
  needsReview: number
  p1Count: number
  avgConfidence: number
  avgLatencyMs: number
  totalTokens: number
  totalToolCalls: number
  cacheHits: number
  spend: number
}

interface ReconStore {
  currentRunId: string | null
  incidents: Map<string, RCAIncident>
  runStatus: RunStatus
  llmConfig: LlmConfig
  environment: Environment
  sseConnected: boolean
  runStats: RunStats | null

  setRunId: (id: string) => void
  upsertIncident: (incident: RCAIncident) => void
  setRunStatus: (status: RunStatus) => void
  setLlmConfig: (config: LlmConfig) => void
  setEnvironment: (env: Environment) => void
  setSseConnected: (connected: boolean) => void
  updateRunStats: (patch: Partial<RunStats>) => void
  resetRun: () => void
  getIncidentsSorted: () => RCAIncident[]
}

const SEVERITY_ORDER = { P1: 0, P2: 1, P3: 2 } as const

export const useReconStore = create<ReconStore>((set, get) => ({
  currentRunId: null,
  incidents: new Map(),
  runStatus: 'idle',
  llmConfig: 'claude',
  environment: 'PROD',
  sseConnected: false,
  runStats: null,

  setRunId: (id) => set({ currentRunId: id }),

  upsertIncident: (incident) =>
    set((state) => {
      const key = incident.recon_row_id
      if (!key) return state
      const existing = state.incidents.get(key)
      const next = new Map(state.incidents)
      if (existing) {
        // Merge: only overwrite fields that are non-null in the incoming incident
        // so a running-state SSE event never blanks out data from a completed one
        const merged: RCAIncident = { ...existing }
        for (const k of Object.keys(incident) as (keyof RCAIncident)[]) {
          const v = incident[k]
          if (v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0)) {
            (merged as unknown as Record<string, unknown>)[k] = v
          }
        }
        next.set(key, merged)
      } else {
        next.set(key, incident)
      }
      return { incidents: next }
    }),

  setRunStatus: (status) => set({ runStatus: status }),
  setLlmConfig: (config) => set({ llmConfig: config }),
  setEnvironment: (env) => set({ environment: env }),
  setSseConnected: (connected) => set({ sseConnected: connected }),

  updateRunStats: (patch) =>
    set((state) => ({
      runStats: state.runStats ? { ...state.runStats, ...patch } : { ...defaultStats, ...patch },
    })),

  resetRun: () =>
    set({
      incidents: new Map(),
      runStats: null,
      sseConnected: false,
      runStatus: 'idle',
    }),

  getIncidentsSorted: () => {
    const incidents = Array.from(get().incidents.values())
    return incidents.sort((a, b) => {
      const aOrder = a.severity ? SEVERITY_ORDER[a.severity] ?? 3 : 3
      const bOrder = b.severity ? SEVERITY_ORDER[b.severity] ?? 3 : 3
      return aOrder - bOrder
    })
  },
}))

const defaultStats: RunStats = {
  total: 0,
  resolved: 0,
  needsReview: 0,
  p1Count: 0,
  avgConfidence: 0,
  avgLatencyMs: 0,
  totalTokens: 0,
  totalToolCalls: 0,
  cacheHits: 0,
  spend: 0,
}

// LocalStorage helpers for run history
const HISTORY_KEY = 'reconai_run_history'

export function getRunHistory(): RunHistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]') as RunHistoryEntry[]
  } catch {
    return []
  }
}

export function saveRunToHistory(entry: RunHistoryEntry): void {
  const history = getRunHistory().filter((r) => r.runId !== entry.runId)
  history.unshift(entry)
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 20)))
}

export function updateRunInHistory(runId: string, patch: Partial<RunHistoryEntry>): void {
  const history = getRunHistory().map((r) => (r.runId === runId ? { ...r, ...patch } : r))
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
}

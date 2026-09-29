import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import * as api from './api'
import { useSession } from './session'
import type { BatchJob, BatchRowFlat, DecisionAction, DerivedRow, RowDecisionEntry, RowDetail } from './types'

const IN_FLIGHT: BatchJob['status'][] = ['queued', 'processing']

function firstPhoto(photoRefs: string): string[] {
  return photoRefs
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
}

// The row's status as a person would describe it, from what the backend actually recorded:
// a human decision if there is one, otherwise the batch run's own result. Nothing here infers
// a disposition, grade or identity - the row is shown exactly as the backend wrote it.
function deriveStatus(row: BatchRowFlat, latest: RowDecisionEntry | null): string {
  if (latest) {
    if (latest.action === 'accept' || latest.action === 'override') return 'Finalized'
    if (latest.action === 'retake_request') return 'Awaiting operator'
    if (latest.action === 'review_request') return 'Awaiting review'
  }
  // The backend's flag (batch/auto_approve.py): the engine routed the row with no review and no
  // sign-off required. Not recomputed here, and not the same as a person finalizing it.
  if (row.auto_approved === 'true') return 'Auto-approved'
  if (row.failure_reason || row.observed_state === 'damaged' || row.amazon_condition === 'uncertain') {
    return 'Needs attention'
  }
  return 'Awaiting review'
}

// A wrong item is surfaced as a review flag (§12.2 R03 gives it no disposition): the model's own
// identity verdict on the returned photo is "no", or the returned record's IDs disagree with a sold
// record that exists. A missing sold record is a data gap, not a proven mismatch.
export function isWrongItemFlag(row: BatchRowFlat): boolean {
  const check = row.sold_vs_returned_id_check || ''
  const paperworkMismatch = check.startsWith('NOT MATCHED') && !check.includes('no sold-record')
  return row.photo_identity_match === 'no' || paperworkMismatch
}

function toDerived(job: BatchJob, row: BatchRowFlat, latest: RowDecisionEntry | null): DerivedRow {
  const photos = firstPhoto(row.photo_refs)
  const disposition = latest && latest.new_disposition ? latest.new_disposition : row.operator_disposition
  return {
    ...row,
    operator_disposition: disposition,
    job_id: job.job_id,
    job_status: job.status,
    job_created_at: job.created_at,
    image: photos[0] ?? null,
    reference_image: null,
    photos,
    status: deriveStatus(row, latest),
    wrong_item_flag: isWrongItemFlag(row),
    latest_decision: latest,
  }
}

interface StoreState {
  jobs: BatchJob[]
  rows: DerivedRow[]
  loading: boolean
  error: string | null
}

interface StoreApi extends StoreState {
  activeJobId: string | null
  activeJob: BatchJob | undefined
  inFlightJob: BatchJob | undefined
  justCompletedJob: BatchJob | null
  setActiveJobId: (id: string | null) => void
  dismissCompletedJob: () => void
  refresh: () => Promise<void>
  createJob: (
    fileOrBefore: File,
    returnedOrOpts: File | { confirmSpend: boolean; defaultCategory?: string; maxRequests?: number },
    maybeOpts?: { confirmSpend: boolean; defaultCategory?: string; maxRequests?: number },
  ) => Promise<BatchJob>
  getJob: (jobId: string) => BatchJob | undefined
  findRow: (recordId: string) => DerivedRow | undefined
  getRowDetail: (jobId: string, recordId: string) => Promise<RowDetail>
  getDecisions: (jobId: string, recordId: string, force?: boolean) => Promise<RowDecisionEntry[]>
  recordDecision: (
    jobId: string,
    recordId: string,
    body: { action: DecisionAction; new_disposition?: string | null; reason: string },
  ) => Promise<RowDecisionEntry>
  downloadOutput: (jobId: string) => Promise<void>
  clearCache: () => Promise<void>
}

const StoreContext = createContext<StoreApi | null>(null)

export function BatchStoreProvider({ children }: { children: ReactNode }) {
  const { connected } = useSession()
  const [jobs, setJobs] = useState<BatchJob[]>([])
  const [rowsByJob, setRowsByJob] = useState<Record<string, BatchRowFlat[]>>({})
  const [latestDecisionByRow, setLatestDecisionByRow] = useState<Record<string, RowDecisionEntry | null>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeJobId, setActiveJobIdState] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem('rm_active_job_id')
    } catch {
      return null
    }
  })
  const [justCompletedJob, setJustCompletedJob] = useState<BatchJob | null>(null)

  const detailCache = useRef(new Map<string, RowDetail>())
  const decisionsCache = useRef(new Map<string, RowDecisionEntry[]>())
  const jobsRef = useRef<BatchJob[]>([])
  jobsRef.current = jobs
  const rowsByJobRef = useRef<Record<string, BatchRowFlat[]>>({})
  rowsByJobRef.current = rowsByJob

  const setActiveJobId = useCallback((id: string | null) => {
    setActiveJobIdState(id)
    try {
      if (id) {
        window.localStorage.setItem('rm_active_job_id', id)
      } else {
        window.localStorage.removeItem('rm_active_job_id')
      }
    } catch {
      // storage error
    }
  }, [])

  const dismissCompletedJob = useCallback(() => {
    setJustCompletedJob(null)
  }, [])

  const inFlightJob = jobs.find((j) => IN_FLIGHT.includes(j.status))

  const activeJob = (() => {
    if (activeJobId === 'dismissed') return undefined
    if (activeJobId) {
      const match = jobs.find((j) => j.job_id === activeJobId)
      if (match) return match
    }
    // If there is any in-flight job currently running, default to it
    if (inFlightJob) return inFlightJob
    return undefined
  })()

  const decisionKey = (jobId: string, recordId: string) => `${jobId}:${recordId}`

  const loadRowsForJob = useCallback(async (job: BatchJob) => {
    try {
      const rows = await api.getBatchJobRows(job.job_id)
      setRowsByJob((prev) => ({ ...prev, [job.job_id]: rows }))
      // Fetch each row's latest decision once, up front, so table/dashboard status is
      // accurate without a per-row round trip on every render.
      await Promise.all(
        rows.map(async (row) => {
          try {
            const key = decisionKey(job.job_id, row.record_id)
            if (decisionsCache.current.has(key)) return
            const decisions = await api.getRowDecisions(job.job_id, row.record_id)
            decisionsCache.current.set(key, decisions)
            const latest = decisions.length ? decisions[decisions.length - 1] : null
            setLatestDecisionByRow((prev) => ({ ...prev, [key]: latest }))
          } catch {
            // A row's decision history not loading yet must never block the row from
            // showing up with its real engine output.
          }
        }),
      )
    } catch {
      // Non-fatal if rows not ready yet
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!connected) return
    setLoading(true)
    setError(null)
    try {
      const list = await api.listBatchJobs()
      setJobs(list)
      const relevant = list.filter((j) => j.status === 'done' || (j.status === 'processing' && j.processed > 0))
      await Promise.all(
        relevant
          .filter((j) => !rowsByJobRef.current[j.job_id] || rowsByJobRef.current[j.job_id].length < j.processed)
          .map((j) => loadRowsForJob(j).catch(() => undefined)),
      )
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load batch jobs.')
    } finally {
      setLoading(false)
    }
    // rowsByJob intentionally omitted: re-reading it every call would refetch rows we
    // already have; the filter above reads the latest snapshot via the closure instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, loadRowsForJob])

  useEffect(() => {
    if (connected) void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected])

  // Continuous background polling: fast (1200ms) when any job is in-flight, so that user
  // navigation across pages never interrupts processing or live row updates.
  useEffect(() => {
    if (!connected) return
    let timer: number | undefined
    let cancelled = false

    const poll = async () => {
      const inFlight = jobsRef.current.filter((j) => IN_FLIGHT.includes(j.status))
      if (inFlight.length > 0) {
        for (const job of inFlight) {
          try {
            const updated = await api.getBatchJob(job.job_id)
            const prevJob = jobsRef.current.find((j) => j.job_id === updated.job_id)
            setJobs((prev) => prev.map((j) => (j.job_id === updated.job_id ? updated : j)))

            const currentRows = rowsByJobRef.current[job.job_id] || []
            if (
              updated.status === 'done' ||
              updated.processed > (prevJob?.processed || 0) ||
              (updated.processed > 0 && currentRows.length < updated.processed)
            ) {
              await loadRowsForJob(updated)
            }

            if (updated.status === 'done' && prevJob && prevJob.status !== 'done') {
              setJustCompletedJob(updated)
            }
          } catch {
            // transient poll failure - try again on the next tick
          }
        }
      }

      if (!cancelled) {
        const nextDelay = jobsRef.current.some((j) => IN_FLIGHT.includes(j.status)) ? 1200 : 3500
        timer = window.setTimeout(poll, nextDelay)
      }
    }

    timer = window.setTimeout(poll, 1200)

    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [connected, loadRowsForJob])

  const createJob: StoreApi['createJob'] = useCallback(async (fileOrBefore, returnedOrOpts, maybeOpts) => {
    const job = await api.createBatchJob(fileOrBefore, returnedOrOpts, maybeOpts)
    setActiveJobId(job.job_id)
    setJustCompletedJob(null)
    setJobs((prev) => [job, ...prev])
    return job
  }, [setActiveJobId])

  const getJob = useCallback((jobId: string) => jobsRef.current.find((j) => j.job_id === jobId), [])

  const rawRows: DerivedRow[] = jobs
    .filter((j) => j.status === 'done' || (j.status === 'processing' && (rowsByJob[j.job_id]?.length ?? 0) > 0))
    .flatMap((job) =>
      (rowsByJob[job.job_id] ?? []).map((row) =>
        toDerived(job, row, latestDecisionByRow[decisionKey(job.job_id, row.record_id)] ?? null),
      ),
    )
    .sort((a, b) => b.job_created_at - a.job_created_at)

  // Deduplicate by record_id: newest job's row wins, avoiding duplicate listings across multiple runs
  const seenRecords = new Set<string>()
  const rows: DerivedRow[] = []
  for (const r of rawRows) {
    if (!seenRecords.has(r.record_id)) {
      seenRecords.add(r.record_id)
      rows.push(r)
    }
  }

  const findRow = useCallback((recordId: string) => rows.find((r) => r.record_id === recordId), [rows])

  const getRowDetail: StoreApi['getRowDetail'] = useCallback(async (jobId, recordId) => {
    const key = decisionKey(jobId, recordId)
    const cached = detailCache.current.get(key)
    if (cached) return cached
    const detail = await api.getBatchRowDetail(jobId, recordId)
    detailCache.current.set(key, detail)
    return detail
  }, [])

  const getDecisions: StoreApi['getDecisions'] = useCallback(async (jobId, recordId, force = false) => {
    const key = decisionKey(jobId, recordId)
    if (!force) {
      const cached = decisionsCache.current.get(key)
      if (cached) return cached
    }
    const decisions = await api.getRowDecisions(jobId, recordId)
    decisionsCache.current.set(key, decisions)
    return decisions
  }, [])

  const recordDecision: StoreApi['recordDecision'] = useCallback(async (jobId, recordId, body) => {
    const entry = await api.postRowDecision(jobId, recordId, body)
    const key = decisionKey(jobId, recordId)
    detailCache.current.delete(key) // Invalidate cached detail so updated decision is fetched fresh
    const updated = [...(decisionsCache.current.get(key) ?? []), entry]
    decisionsCache.current.set(key, updated)
    setLatestDecisionByRow((prev) => ({ ...prev, [key]: entry }))
    setRowsByJob((prev) => {
      const jobRows = prev[jobId]
      if (!jobRows) return prev
      return {
        ...prev,
        [jobId]: jobRows.map((r) => {
          if (r.record_id !== recordId) return r
          return {
            ...r,
            operator_disposition: entry.new_disposition || r.operator_disposition,
          }
        }),
      }
    })
    return entry
  }, [])

  const downloadOutput = useCallback((jobId: string) => api.downloadBatchJobOutput(jobId), [])

  const clearCache: StoreApi['clearCache'] = useCallback(async () => {
    try {
      await api.clearBatchCache()
    } catch {
      // ignore network errors if any
    }
    detailCache.current.clear()
    decisionsCache.current.clear()
    setActiveJobId(null)
    setJustCompletedJob(null)
    setRowsByJob({})
    setLatestDecisionByRow({})
    setJobs([])
    try {
      window.sessionStorage.clear()
      const savedKey = window.localStorage.getItem('rm_api_key')
      window.localStorage.clear()
      if (savedKey) window.localStorage.setItem('rm_api_key', savedKey)
    } catch {
      // ignore storage errors
    }
    await refresh()
  }, [refresh, setActiveJobId])

  const value: StoreApi = {
    jobs,
    rows,
    loading,
    error,
    activeJobId,
    activeJob,
    inFlightJob,
    justCompletedJob,
    setActiveJobId,
    dismissCompletedJob,
    refresh,
    createJob,
    getJob,
    findRow,
    getRowDetail,
    getDecisions,
    recordDecision,
    downloadOutput,
    clearCache,
  }

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useBatchStore(): StoreApi {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useBatchStore must be used within BatchStoreProvider')
  return ctx
}

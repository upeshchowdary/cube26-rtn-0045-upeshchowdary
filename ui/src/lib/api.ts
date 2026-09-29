import type {
  BatchJob,
  BatchRowFlat,
  ChainVerificationResponse,
  ControlsResponse,
  DecisionAction,
  EconomicsReportResponse,
  KeyCreated,
  MetricsSummaryResponse,
  RowDecisionEntry,
  RowDetail,
} from './types'

export class ApiError extends Error {
  status: number
  detail?: string
  code?: string
  constructor(status: number, message: string, detail?: string, code?: string) {
    super(message)
    this.status = status
    this.detail = detail
    this.code = code
  }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://127.0.0.1:8000'
const STORAGE_KEY = 'rm_api_key'

let cachedKey: string | null | undefined
let unauthorizedHandler: (() => void) | null = null

export function getApiKey(): string | null {
  if (cachedKey === undefined) {
    try {
      cachedKey = window.localStorage.getItem(STORAGE_KEY)
    } catch {
      cachedKey = null
    }
  }
  return cachedKey
}

export function setApiKey(key: string | null): void {
  cachedKey = key
  try {
    if (key) window.localStorage.setItem(STORAGE_KEY, key)
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // localStorage unavailable (private browsing, blocked site data) - the in-memory
    // cache above still works for the rest of this page load.
  }
}

export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

async function readProblem(res: Response): Promise<{ detail?: string; code?: string }> {
  try {
    const problem = await res.clone().json()
    return { detail: problem.detail || problem.title, code: problem.code }
  } catch {
    try {
      const text = await res.text()
      return { detail: text || undefined }
    } catch {
      return {}
    }
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const key = getApiKey()
  const headers = new Headers(init.headers)
  if (key) headers.set('X-API-Key', key)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  } catch (err) {
    throw new ApiError(0, `Could not reach the backend at ${BASE_URL}. Is it running?`)
  }
  if (res.status === 401) {
    setApiKey(null)
    unauthorizedHandler?.()
    const { detail } = await readProblem(res)
    throw new ApiError(401, detail || 'Not connected to the backend.', detail)
  }
  if (!res.ok) {
    const { detail, code } = await readProblem(res)
    throw new ApiError(res.status, detail || `Request failed (${res.status})`, detail, code)
  }
  if (res.status === 204) return undefined as T
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return (await res.json()) as T
  return (await res.text()) as unknown as T
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

function putJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'PUT', body: JSON.stringify(body) })
}

// ── Auth check ──────────────────────────────────────────────────────────────────────
export function health(): Promise<{ status: string }> {
  return request('/health')
}

// ── Batch jobs (the real "upload a file, backend processes it" pipeline) ───────────
export function createBatchJob(
  fileOrBefore: File,
  returnedOrOpts: File | { confirmSpend: boolean; defaultCategory?: string; maxRequests?: number },
  maybeOpts?: { confirmSpend: boolean; defaultCategory?: string; maxRequests?: number },
): Promise<BatchJob> {
  const form = new FormData()
  let opts: { confirmSpend: boolean; defaultCategory?: string; maxRequests?: number }
  if (returnedOrOpts instanceof File) {
    form.append('before', fileOrBefore)
    form.append('returned', returnedOrOpts)
    opts = maybeOpts || { confirmSpend: false }
  } else {
    // Single unified returns CSV file
    form.append('file', fileOrBefore)
    opts = returnedOrOpts
  }
  form.append('confirm_spend', String(opts.confirmSpend))
  if (opts.defaultCategory) form.append('default_category', opts.defaultCategory)
  if (opts.maxRequests) form.append('max_requests', String(opts.maxRequests))
  return request<BatchJob>('/api/v1/batch/jobs', { method: 'POST', body: form })
}

export function listBatchJobs(): Promise<BatchJob[]> {
  return request('/api/v1/batch/jobs')
}

export function getBatchJob(jobId: string): Promise<BatchJob> {
  return request(`/api/v1/batch/jobs/${encodeURIComponent(jobId)}`)
}

export function getBatchJobRows(jobId: string): Promise<BatchRowFlat[]> {
  return request(`/api/v1/batch/jobs/${encodeURIComponent(jobId)}/rows`)
}

export function getBatchRowDetail(jobId: string, recordId: string): Promise<RowDetail> {
  return request(`/api/v1/batch/jobs/${encodeURIComponent(jobId)}/rows/${encodeURIComponent(recordId)}/detail`)
}

export function postRowDecision(
  jobId: string,
  recordId: string,
  body: { action: DecisionAction; new_disposition?: string | null; reason: string },
): Promise<RowDecisionEntry> {
  return postJson(
    `/api/v1/batch/jobs/${encodeURIComponent(jobId)}/rows/${encodeURIComponent(recordId)}/decision`,
    body,
  )
}

export function getRowDecisions(jobId: string, recordId: string): Promise<RowDecisionEntry[]> {
  return request(
    `/api/v1/batch/jobs/${encodeURIComponent(jobId)}/rows/${encodeURIComponent(recordId)}/decisions`,
  )
}

export function deleteBatchJob(jobId: string): Promise<void> {
  return request(`/api/v1/batch/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
}

export function clearBatchCache(): Promise<{ cleared: number }> {
  return postJson('/api/v1/batch/cache/clear', {})
}

export async function downloadBatchJobOutput(jobId: string): Promise<void> {
  const key = getApiKey()
  const headers: HeadersInit = key ? { 'X-API-Key': key } : {}
  const res = await fetch(`${BASE_URL}/api/v1/batch/jobs/${encodeURIComponent(jobId)}/output.csv`, { headers })
  if (!res.ok) {
    const { detail } = await readProblem(res)
    throw new ApiError(res.status, detail || `Download failed (${res.status})`, detail)
  }
  // Read as text first so we can re-wrap with the correct MIME type.
  // The browser may not honour the server's Content-Type on blob(), causing
  // the OS to treat the file as binary rather than opening it in a spreadsheet.
  const text = await res.text()
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `returns_output_${jobId}.csv`
  document.body.appendChild(a)
  a.click()
  // Small delay before revoking so the browser has time to initiate the download
  setTimeout(() => {
    a.remove()
    URL.revokeObjectURL(url)
  }, 200)
}

// ── Metrics (§18.2/§18.3 - DB-backed; may honestly read "no data" in this demo) ────
export function getMetricsSummary(window = '7d'): Promise<MetricsSummaryResponse> {
  return request(`/api/v1/metrics/summary?window=${encodeURIComponent(window)}`)
}

export function getMetricsEconomics(window = '7d', volume = 1000): Promise<EconomicsReportResponse> {
  return request(`/api/v1/metrics/economics?window=${encodeURIComponent(window)}&volume=${volume}`)
}

// ── System controls (kill switches, §6.7) ───────────────────────────────────────────
export function getSystemControls(): Promise<ControlsResponse> {
  return request('/api/v1/system/controls')
}

export function putSystemControl(body: { control: string; enabled: boolean; reason: string }): Promise<ControlsResponse> {
  return putJson('/api/v1/system/controls', body)
}

// ── API keys (admin) ────────────────────────────────────────────────────────────────
export function createApiKey(body: { name: string; scopes: string[]; expires_at?: string | null }): Promise<KeyCreated> {
  return postJson('/api/v1/keys', body)
}

export function revokeApiKey(keyId: string): Promise<void> {
  return request(`/api/v1/keys/${encodeURIComponent(keyId)}`, { method: 'DELETE' })
}

// ── Evidence / chain verification (DB-backed; real, but only for a real DB unit_id) ─
export function getChainVerification(unitId: string): Promise<ChainVerificationResponse> {
  return request(`/api/v1/units/${encodeURIComponent(unitId)}/chain/verification`)
}

export function getEvidenceRecord(unitId: string): Promise<Record<string, unknown>> {
  return request(`/api/v1/units/${encodeURIComponent(unitId)}/return-evidence`)
}

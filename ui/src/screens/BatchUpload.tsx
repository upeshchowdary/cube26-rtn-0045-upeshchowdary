import { useState, type ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  CheckCircle2,
  CircleAlert,
  Download,
  FileCheck2,
  ShieldCheck,
  Upload,
} from 'lucide-react'
import { ApiError } from '../lib/api'
import { useBatchStore } from '../lib/store'
import type { BatchJob } from '../lib/types'
import { Header, InlineError } from './shared'

const IN_FLIGHT: BatchJob['status'][] = ['queued', 'processing']

function SingleFilePicker({
  file,
  rowCount,
  onPick,
}: {
  file: File | null
  rowCount: number | null
  onPick: (file: File) => void
}) {
  const [dragging, setDragging] = useState(false)

  const handleInput = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = event.target.files?.[0]
    if (picked) onPick(picked)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files?.[0]
    if (dropped && (dropped.name.endsWith('.csv') || dropped.type.includes('csv'))) {
      onPick(dropped)
    }
  }

  return (
    <div className="single-upload-slot">
      <label
        className={`single-upload-area ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        {file ? (
          <>
            <FileCheck2 size={34} style={{ color: '#4ade80' }} />
            <strong style={{ fontSize: '15px' }}>{file.name}</strong>
            <span>
              {(file.size / 1024).toFixed(1)} KB ·{' '}
              {rowCount !== null ? `${rowCount} return rows detected` : 'File ready'} · click or
              drop another file to replace
            </span>
            <div className="single-upload-badges">
              <span
                className="single-upload-badge"
                style={{ color: '#4ade80', borderColor: 'rgba(74, 222, 128, 0.3)' }}
              >
                ✓ Unified before-sale & after-sale dataset
              </span>
              <span className="single-upload-badge">sold_*</span>
              <span className="single-upload-badge">returned_*</span>
              <span className="single-upload-badge">live photo URLs</span>
            </div>
          </>
        ) : (
          <>
            <Upload size={32} style={{ color: '#57e389' }} />
            <strong style={{ fontSize: '15px' }}>
              Choose a unified returns batch CSV file or drag and drop here
            </strong>
            <span>
              Upload one single CSV file containing before-sale (what was ordered) and after-sale
              (what came back) details per return (e.g. <code>returns_input_30.csv</code>).
            </span>
            <div className="single-upload-badges">
              <span className="single-upload-badge">unit_id</span>
              <span className="single-upload-badge">category</span>
              <span className="single-upload-badge">parts_list</span>
              <span className="single-upload-badge">sold_photo_url</span>
              <span className="single-upload-badge">returned_photo_url</span>
            </div>
          </>
        )}
        <input type="file" accept=".csv,text/csv" onChange={handleInput} />
      </label>
    </div>
  )
}

export default function BatchUpload() {
  const navigate = useNavigate()
  const { createJob, downloadOutput, jobs, activeJob, setActiveJobId } = useBatchStore()
  const [file, setFile] = useState<File | null>(null)
  const [rowCount, setRowCount] = useState<number | null>(null)
  const [defaultCategory, setDefaultCategory] = useState('')
  const [maxRequests, setMaxRequests] = useState(15)
  const [confirmSpend, setConfirmSpend] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const onPickFile = (picked: File) => {
    setFile(picked)
    setError('')
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = String(e.target?.result || '')
      const lines = text.split('\n').filter((l) => l.trim().length > 0)
      setRowCount(Math.max(0, lines.length - 1))
    }
    reader.readAsText(picked.slice(0, 80000))
  }

  const submit = async () => {
    if (!file) {
      setError('Please choose a returns batch CSV file to upload.')
      return
    }
    if (!confirmSpend) {
      setError('Confirm the spend checkbox - this run calls the real Gemini API and spends daily quota.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const job = await createJob(file, {
        confirmSpend,
        defaultCategory: defaultCategory || undefined,
        maxRequests,
      })
      setActiveJobId(job.job_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start the batch job.')
    } finally {
      setSubmitting(false)
    }
  }

  const reset = () => {
    setActiveJobId('dismissed')
    setFile(null)
    setRowCount(null)
    setError('')
    setConfirmSpend(false)
  }

  if (activeJob) {
    const inFlight = IN_FLIGHT.includes(activeJob.status)
    const pct =
      activeJob.total_rows > 0
        ? Math.min(
            100,
            Math.round(((activeJob.processed + activeJob.uncertain) / activeJob.total_rows) * 100),
          )
        : 0
    return (
      <>
        <Header
          eyebrow="OPERATIONS / BATCH UPLOAD"
          title="Processing"
          subtitle="The backend is running the real judgment session and disposition engine for each row."
        />
        <section className="panel wizard">
          <div className="upload-progress">
            <div className="wizard-title">
              <span>
                {inFlight ? (
                  <Upload size={18} />
                ) : activeJob.status === 'done' ? (
                  <CheckCircle2 size={18} />
                ) : (
                  <CircleAlert size={18} />
                )}
              </span>
              <div>
                <h2>
                  {inFlight ? 'Processing your upload' : activeJob.status === 'done' ? 'Done' : 'Failed'}
                </h2>
                <p>
                  {activeJob.before_filename} · job {activeJob.job_id.slice(0, 10)}
                </p>
              </div>
            </div>

            <div className="upload-progress-bar">
              <i style={{ width: `${inFlight ? Math.max(pct, 6) : 100}%` }} />
            </div>

            <div className="upload-progress-stats">
              <span>
                Total<b>{activeJob.total_rows}</b>
              </span>
              <span>
                Processed<b>{activeJob.processed}</b>
              </span>
              <span>
                Uncertain / fail-open<b>{activeJob.uncertain}</b>
              </span>
              <span>
                Live model requests<b>{activeJob.live_requests}</b>
              </span>
            </div>

            {activeJob.status === 'failed' && activeJob.error && (
              <InlineError>
                <CircleAlert size={14} /> {activeJob.error}
              </InlineError>
            )}

            {activeJob.notes.length > 0 && (
              <div className="upload-notes">
                {activeJob.notes.map((note, i) => (
                  <span key={i}>{note}</span>
                ))}
              </div>
            )}

            {inFlight && (
              <div className="dialog-actions" style={{ justifyContent: 'space-between', marginTop: 18 }}>
                <button className="button" onClick={() => navigate('/returns')}>
                  View streaming rows in Returns <ArrowRight size={14} />
                </button>
                <button className="button" onClick={reset}>
                  Upload another file
                </button>
              </div>
            )}

            {activeJob.status === 'done' && (
              <div className="dialog-actions">
                <button className="button" onClick={reset}>
                  Upload another file
                </button>
                <button className="button" onClick={() => void downloadOutput(activeJob.job_id)}>
                  <Download size={14} /> Download output CSV
                </button>
                <button className="button primary" onClick={() => navigate('/returns')}>
                  View in Returns <ArrowRight size={14} />
                </button>
              </div>
            )}
          </div>
        </section>
      </>
    )
  }

  return (
    <>
      <Header
        eyebrow="OPERATIONS / INTAKE"
        title="New batch inspection"
        subtitle="Upload a unified returns batch CSV file. The backend processes both before-sale product details and after-sale return photos, running the real judgment session and rules engine to write one output row per return."
      />
      <section className="panel wizard">
        <div className="wizard-content">
          {jobs.length > 0 && jobs[0].status === 'done' && (
            <div className="order-found" style={{ marginBottom: 14 }}>
              <span>
                <b>Recent batch: {jobs[0].before_filename}</b>
                <small>
                  Job {jobs[0].job_id.slice(0, 10)} · {jobs[0].total_rows} returns evaluated ({jobs[0].status})
                </small>
              </span>
              <button
                type="button"
                className="button"
                style={{ marginLeft: 'auto' }}
                onClick={() => setActiveJobId(jobs[0].job_id)}
              >
                Inspect previous results <ArrowRight size={13} />
              </button>
            </div>
          )}
          <div className="form-grid">
            <SingleFilePicker file={file} rowCount={rowCount} onPick={onPickFile} />
            <label className="field">
              <span>Default category · optional (auto-detected per row if blank)</span>
              <input
                value={defaultCategory}
                onChange={(e) => setDefaultCategory(e.target.value)}
                placeholder="electronics, toys_games, home_kitchen..."
              />
            </label>
            <label className="field">
              <span>Max live model requests</span>
              <input
                type="number"
                min={1}
                max={50}
                value={maxRequests}
                onChange={(e) => setMaxRequests(Number(e.target.value) || 1)}
              />
            </label>
          </div>

          <details className="rule-details">
            <summary>
              Unified CSV structure & columns <ArrowRight size={13} />
            </summary>
            <p>
              Unified single-file format (e.g. <code>returns_input_30.csv</code>) contains:
            </p>
            <p>
              <b>Before-sale fields:</b> unit_id, category, parts_list, identity_match, sold_record_id,
              sold_org_id, sold_order_id, sold_sku, sold_asin, sold_time, sold_photo_url.
            </p>
            <p>
              <b>After-sale fields:</b> returned_record_id, returned_org_id, returned_order_id,
              returned_sku, returned_asin, returned_time, returned_photo_url, scenario.
            </p>
          </details>

          <label className="spend-checkbox">
            <input
              type="checkbox"
              checked={confirmSpend}
              onChange={(e) => setConfirmSpend(e.target.checked)}
            />
            <span>
              I understand this run calls the real Gemini API and spends real daily request quota.
              <small>
                Each row costs roughly one model request; failed/uncertain rows fail open and never
                guess a verdict.
              </small>
            </span>
          </label>

          {error && (
            <InlineError>
              <CircleAlert size={14} /> {error}
            </InlineError>
          )}

          <div className="wizard-footer">
            <span>
              {file ? (
                <>
                  <Check size={13} style={{ color: '#4ade80' }} /> {file.name}{' '}
                  {rowCount !== null ? `(${rowCount} items)` : ''}
                </>
              ) : (
                'No returns file selected'
              )}
            </span>
            <div>
              <button className="button" onClick={() => navigate('/returns')}>
                Cancel
              </button>
              <button
                className="button primary"
                disabled={submitting || !file}
                onClick={() => void submit()}
              >
                {submitting ? 'Starting...' : `Process batch${rowCount ? ` (${rowCount} returns)` : ''}`}
              </button>
            </div>
          </div>
        </div>
      </section>
      <p className="form-footnote">
        <ShieldCheck size={14} /> The backend never guesses: a photo it cannot fetch, a category it
        does not recognise, or a model failure fails open to an uncertain row, never a fabricated
        pass.
      </p>
    </>
  )
}

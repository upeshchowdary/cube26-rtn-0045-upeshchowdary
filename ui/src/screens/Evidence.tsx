import { useState } from 'react'
import { CircleAlert, Download, Search, ShieldCheck, X } from 'lucide-react'
import { dispositionLabel } from '../lib/derive'
import { ApiError, getChainVerification } from '../lib/api'
import type { ChainVerificationResponse } from '../lib/types'
import { useBatchStore } from '../lib/store'
import { Header, Note, Pill } from './shared'

export default function Evidence() {
  const [query, setQuery] = useState('')
  const [chosen, setChosen] = useState<string | null>(null)
  const { rows, jobs, downloadOutput } = useBatchStore()
  const shown = rows.filter((r) => `${r.record_id} ${r.ordered_sku} ${r.unit_id}`.toLowerCase().includes(query.toLowerCase()))
  const chosenRow = shown.find((r) => r.record_id === chosen) ?? null

  const [unitLookup, setUnitLookup] = useState('')
  const [lookupResult, setLookupResult] = useState<ChainVerificationResponse | null>(null)
  const [lookupError, setLookupError] = useState('')
  const [lookingUp, setLookingUp] = useState(false)

  const runLookup = async () => {
    if (!unitLookup.trim()) return
    setLookingUp(true)
    setLookupError('')
    setLookupResult(null)
    try {
      setLookupResult(await getChainVerification(unitLookup.trim()))
    } catch (err) {
      setLookupError(err instanceof ApiError ? err.message : 'Lookup failed.')
    } finally {
      setLookingUp(false)
    }
  }

  return (
    <>
      <Header
        eyebrow="RECORDS / AUDIT TRAIL"
        title="Evidence & audit"
        subtitle="Batch-processed rows and their decision history, plus a real hash-chain lookup for any DB-backed unit."
      />
      <div className="integrity">
        <ShieldCheck size={20} />
        <span>
          <b>Batch decision log is hash-chained</b>
          <small>
            Row data and decisions live in the batch job's append-only log, with a deterministic
            prev-hash chain and tamper verification. The database's per-unit hash chain (§13)
            still applies to the live capture pipeline; this is its upload-path equivalent and is
            tamper-evident, not immutable.
          </small>
        </span>
      </div>
      <section className="panel evidence-list">
        <div className="panel-head">
          <div>
            <h2>Processed rows</h2>
            <p>{jobs.filter((j) => j.status === 'done').length} completed upload(s)</p>
          </div>
          <label className="table-search">
            <Search size={15} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search evidence..." />
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>RECORD</th>
                <th>UNIT ID</th>
                <th>DISPOSITION</th>
                <th>DECISION</th>
                <th>CAPTURED</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.record_id} onClick={() => setChosen(chosen === r.record_id ? null : r.record_id)}>
                  <td>
                    <b>{r.record_id}</b>
                    <small>{r.ordered_sku}</small>
                  </td>
                  <td>{r.unit_id}</td>
                  <td>{dispositionLabel(r.operator_disposition)}</td>
                  <td>
                    <span className="verified">
                      <ShieldCheck size={14} />
                      {r.latest_decision ? r.latest_decision.action : 'none yet'}
                    </span>
                  </td>
                  <td>{r.captured_at}</td>
                  <td>
                    <button
                      className="icon-button"
                      onClick={(e) => {
                        e.stopPropagation()
                        void downloadOutput(r.job_id)
                      }}
                      aria-label="Download job output"
                    >
                      <Download size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {chosenRow && (
          <div className="evidence-expanded">
            <button onClick={() => setChosen(null)}>
              <X size={15} />
            </button>
            <b>{chosenRow.record_id} · row detail</b>
            <p>
              Job <code>{chosenRow.job_id}</code> · sold-vs-returned check: {chosenRow.sold_vs_returned_id_check}
            </p>
            <small>
              <ShieldCheck size={13} /> Open the full inspection to see the model's own evidence and citations.
            </small>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Chain verification lookup</h2>
            <p>Real, DB-backed hash-chain check (§13) for any unit id from the live capture pipeline.</p>
          </div>
        </div>
        <div className="return-toolbar">
          <label className="table-search">
            <Search size={15} />
            <input value={unitLookup} onChange={(e) => setUnitLookup(e.target.value)} placeholder="UNIT-..." onKeyDown={(e) => e.key === 'Enter' && void runLookup()} />
          </label>
          <button className="button primary" disabled={lookingUp} onClick={() => void runLookup()}>
            Verify
          </button>
        </div>
        {lookupError && (
          <div className="inline-error">
            <CircleAlert size={14} /> {lookupError}
          </div>
        )}
        {lookupResult && (
          <div className="evidence-expanded">
            <b>
              {lookupResult.unit_id} · <Pill value={lookupResult.valid ? 'Valid' : 'Invalid'} />
            </b>
            <p>
              {lookupResult.events_checked} event(s) · {lookupResult.ledger_entries_checked} ledger entr{lookupResult.ledger_entries_checked === 1 ? 'y' : 'ies'} ·{' '}
              {lookupResult.anchors_checked} anchor(s) checked
            </p>
            <small>{lookupResult.summary}</small>
            {lookupResult.failures.length > 0 && (
              <ul>
                {lookupResult.failures.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
      <Note>Tamper-evident within the database (hash-chained); not immutable.</Note>
    </>
  )
}

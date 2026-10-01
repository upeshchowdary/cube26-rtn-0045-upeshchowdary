import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowDownUp, ArrowUpRight, ChevronLeft, ChevronRight, CircleAlert, Clock3, Download, Package, Plus, Search, SlidersHorizontal } from 'lucide-react'
import { useBatchStore } from '../lib/store'
import { deriveProductReasoning } from '../lib/derive'
import type { DerivedRow } from '../lib/types'
import { Button, Header, Note, Pill } from './shared'

const PAGE_SIZE = 8

function formatTimestamp(val: string | number | undefined): string {
  if (!val) return '—'
  try {
    const d = typeof val === 'number' ? new Date(val > 1e11 ? val : val * 1000) : new Date(val)
    if (isNaN(d.getTime())) return String(val)
    return d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC'
  } catch {
    return String(val)
  }
}

export default function Returns() {
  const navigate = useNavigate()
  const { rows, downloadOutput, jobs } = useBatchStore()
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState('All returns')
  const [page, setPage] = useState(1)
  const [sortKey, setSortKey] = useState<'time' | 'record'>('time')
  const [timeAscending, setTimeAscending] = useState(false)
  const [recordAscending, setRecordAscending] = useState(false)

  const parseTime = (val: string | number | undefined) => {
    if (!val) return 0
    if (typeof val === 'number') return val > 1e11 ? val : val * 1000
    const parsed = Date.parse(val)
    return isNaN(parsed) ? 0 : parsed
  }

  const tabs = [
    'All returns',
    'Awaiting review',
    'Finalized',
    'Auto approved',
    'Auto disapproved',
  ]
  // One rule per tab, from the row's status (store.tsx deriveStatus: a person's accept/override or the
  // backend auto-approve flag finalizes; a retake or review request keeps the row open).
  const tabRule = (name: string, row: DerivedRow): boolean => {
    if (name === 'All returns') return true
    if (name === 'Awaiting review') {
      return ['Awaiting review', 'Awaiting operator', 'Needs attention'].includes(row.status)
    }
    if (name === 'Finalized') return row.status === 'Finalized'
    if (name === 'Auto approved') return row.auto_approved === 'true'
    if (name === 'Auto disapproved') return row.status === 'Auto-disapproved'
    return row.status === name
  }
  const inTab = (row: DerivedRow) => tabRule(tab, row)
  const tabCount = (name: string) => rows.filter((row) => tabRule(name, row)).length
  const filtered = rows
    .filter((r) => `${r.record_id} ${r.order_id} ${r.unit_id} ${r.ordered_sku} ${r.ordered_asin}`.toLowerCase().includes(query.toLowerCase()))
    .filter((r) => inTab(r))
    .sort((a, b) => {
      if (sortKey === 'time') {
        const tA = parseTime(a.captured_at || a.job_created_at)
        const tB = parseTime(b.captured_at || b.job_created_at)
        return timeAscending ? tA - tB : tB - tA
      }
      return recordAscending ? a.record_id.localeCompare(b.record_id) : b.record_id.localeCompare(a.record_id)
    })
  const shown = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const doneJobs = jobs.filter((j) => j.status === 'done')

  return (
    <>
      <Header
        eyebrow="OPERATIONS / RETURNS"
        title="Returns"
        subtitle="Every row here is real output from a batch upload - track it from intake to final disposition."
        actions={
          <>
            {doneJobs.length > 0 && (
              <Button icon={Download} onClick={() => void downloadOutput(doneJobs[0].job_id)}>
                Download latest output
              </Button>
            )}
            <Button primary icon={Plus} onClick={() => navigate('/returns/new')}>
              New batch upload
            </Button>
          </>
        }
      />
      {rows.some(
        (r) =>
          r.failure_reason &&
          (r.failure_reason.includes('quota') ||
            r.failure_reason.includes('max_requests') ||
            r.failure_reason.includes('resource_exhausted') ||
            r.failure_reason.includes('429')),
      ) && (
        <div
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            padding: '12px 16px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <CircleAlert size={18} color="#dc2626" style={{ flexShrink: 0 }} />
          <div style={{ fontSize: '12px' }}>
            <b style={{ color: '#dc2626', display: 'block', marginBottom: '2px' }}>
              Gemini API Quota Notice
            </b>
            <span style={{ color: 'var(--muted)' }}>
              Some items were marked uncertain / fail-open because the Gemini API quota or rate limit was reached during processing.
            </span>
          </div>
        </div>
      )}
      <section className="panel returns-panel">
        <div className="return-toolbar">
          <div className="tabs" style={{ flexWrap: 'wrap', overflow: 'visible' }}>
            {tabs.map((t) => (
              <button
                className={tab === t ? 'tab selected' : 'tab'}
                key={t}
                onClick={() => {
                  setTab(t)
                  setPage(1)
                }}
              >
                {t}
                <small>{tabCount(t)}</small>
              </button>
            ))}
          </div>
          <div className="table-tools">
            <label className="table-search">
              <Search size={15} />
              <input
                placeholder="Search returns..."
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setPage(1)
                }}
              />
            </label>
            <button className="button" onClick={() => setTab(tab === 'Awaiting review' ? 'All returns' : 'Awaiting review')}>
              <SlidersHorizontal size={14} />
              Filters
            </button>
          </div>
        </div>
        <div className="table-scroll">
          <table className="returns-table">
            <thead>
              <tr>
                <th style={{ minWidth: '220px' }}>PRODUCT</th>
                <th style={{ minWidth: '150px' }}>
                  <button onClick={() => { setSortKey('record'); setRecordAscending(!recordAscending); }}>
                    RETURN <ArrowDownUp size={12} />
                  </button>
                </th>
                <th style={{ minWidth: '130px' }}>CATALOG IDENTITY</th>
                <th style={{ minWidth: '110px' }}>PARTS MISSING</th>
                <th style={{ minWidth: '150px' }}>CONDITION</th>
                <th style={{ minWidth: '150px' }}>DISPOSITION</th>
                <th style={{ minWidth: '140px' }}>STATUS</th>
                <th style={{ minWidth: '150px' }}>
                  <button onClick={() => { setSortKey('time'); setTimeAscending(!timeAscending); }}>
                    CAPTURED TIME <ArrowDownUp size={12} />
                  </button>
                </th>
                <th style={{ width: '36px' }} />
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const reasoning = deriveProductReasoning(r)
                return (
                  <tr key={r.record_id} onClick={() => navigate(`/returns/${r.record_id}/inspection`)}>
                    <td>
                      <span className="product-cell">
                        {r.image ? (
                          <img src={r.image} alt="" />
                        ) : r.reference_image ? (
                          <img src={r.reference_image} alt="Catalog Ref" title="Reference photo (No return photo in CSV)" style={{ opacity: 0.8 }} />
                        ) : (
                          <Package size={18} />
                        )}
                        <span>
                          <b>{r.ordered_sku}</b>
                          <small>{r.unit_id}</small>
                        </span>
                      </span>
                    </td>
                    <td>
                      <b>{r.record_id}</b>
                      <small>{r.order_id}</small>
                    </td>
                    <td>
                      <Pill value={r.identity_match} />
                    </td>
                    <td>{r.parts_missing || '—'}</td>
                    <td>
                      <Pill value={reasoning.condition} />
                      <small title={reasoning.conditionReason}>{reasoning.shortConditionReason}</small>
                    </td>
                    <td>
                      {reasoning.disposition === '—' ? '—' : <Pill value={reasoning.disposition} />}
                      {reasoning.disposition !== '—' && (
                        <small title={reasoning.dispositionReason}>{reasoning.shortDispositionReason}</small>
                      )}
                    </td>
                    <td>
                      <Pill value={r.status === 'Needs attention' ? 'Awaiting review' : r.status} />
                      {r.latest_decision && (
                        <small>Operator accepted</small>
                      )}
                    </td>
                    <td>
                      <span className="timestamp-cell">
                        <Clock3 size={11} style={{ opacity: 0.6 }} />
                        {formatTimestamp(r.captured_at || r.job_created_at)}
                      </span>
                    </td>
                    <td>
                      <ArrowUpRight size={15} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {!shown.length && (
          <div className="empty">
            <Search size={22} />
            <b>No returns match</b>
            <span>{rows.length === 0 ? 'Upload a batch file to populate this table.' : 'Try another search or reset the filters.'}</span>
            <Button
              onClick={() => {
                setQuery('')
                setTab('All returns')
              }}
            >
              Reset filters
            </Button>
          </div>
        )}
        <div className="table-footer">
          <span>
            Showing{' '}
            <b>
              {filtered.length ? (page - 1) * PAGE_SIZE + 1 : 0}–{Math.min(page * PAGE_SIZE, filtered.length)}
            </b>{' '}
            of <b>{filtered.length}</b>
          </span>
          <div>
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
              <ChevronLeft size={15} />
            </button>{' '}
            Page <b>{page}</b> of {pages}{' '}
            <button disabled={page >= pages} onClick={() => setPage(page + 1)}>
              <ChevronRight size={15} />
            </button>
          </div>
        </div>
      </section>
      <Note>
        Identity column reflects the catalog record at sale time; open a row to see what the
        model actually observed in the returned photo.
      </Note>
    </>
  )
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowDownUp, ArrowUpRight, ChevronLeft, ChevronRight, Clock3, Download, Package, Plus, Search, SlidersHorizontal } from 'lucide-react'
import { useBatchStore } from '../lib/store'
import { dispositionLabel } from '../lib/derive'
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

  const tabs = ['All returns', 'Awaiting review', 'Needs attention', 'Finalized', 'Auto-disapproved']
  const inTab = (status: string) => {
    if (tab === 'All returns') return true
    if (tab === 'Auto-disapproved') return status === 'Auto-disapproved' || status === 'Rejected'
    return tab === status
  }
  const filtered = rows
    .filter((r) => `${r.record_id} ${r.order_id} ${r.unit_id} ${r.ordered_sku} ${r.ordered_asin}`.toLowerCase().includes(query.toLowerCase()))
    .filter((r) => inTab(r.status))
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
      <section className="panel returns-panel">
        <div className="return-toolbar">
          <div className="tabs">
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
                <small>
                  {t === 'All returns'
                    ? rows.length
                    : t === 'Auto-disapproved'
                    ? rows.filter((r) => r.status === 'Auto-disapproved' || r.status === 'Rejected').length
                    : rows.filter((r) => r.status === t).length}
                </small>
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
            <button className="button" onClick={() => setTab(tab === 'Needs attention' ? 'All returns' : 'Needs attention')}>
              <SlidersHorizontal size={14} />
              Filters
            </button>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>PRODUCT</th>
                <th>
                  <button onClick={() => { setSortKey('record'); setRecordAscending(!recordAscending); }}>
                    RETURN <ArrowDownUp size={12} />
                  </button>
                </th>
                <th>CATALOG IDENTITY</th>
                <th>PARTS MISSING</th>
                <th>CONDITION</th>
                <th>DISPOSITION</th>
                <th>STATUS</th>
                <th>
                  <button onClick={() => { setSortKey('time'); setTimeAscending(!timeAscending); }}>
                    CAPTURED TIME <ArrowDownUp size={12} />
                  </button>
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.record_id} onClick={() => navigate(`/returns/${r.record_id}/inspection`)}>
                  <td>
                    <span className="product-cell">
                      {r.image ? <img src={r.image} alt="" /> : <Package size={18} />}
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
                  <td>{r.amazon_condition}</td>
                  <td>{r.operator_disposition ? <Pill value={dispositionLabel(r.operator_disposition)} /> : '—'}</td>
                  <td>
                    <Pill value={r.status} />
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
              ))}
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

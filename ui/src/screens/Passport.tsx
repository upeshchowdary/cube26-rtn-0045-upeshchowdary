import { useParams, Link } from 'react-router-dom'
import { ArrowUpRight, Check, History, Package, PackageCheck, Upload } from 'lucide-react'
import { useBatchStore } from '../lib/store'
import { formatDateTime } from '../lib/format'
import { Header, Note, Pill } from './shared'

export default function Passport() {
  const { id = '' } = useParams()
  const { rows } = useBatchStore()
  const r = rows.find((x) => x.unit_id === id) || (rows.length > 0 && id === 'UNIT-0001' ? rows[0] : undefined)

  if (!r) {
    return (
      <>
        <Header eyebrow="INTELLIGENCE / UNIT HISTORY" title="Unit digital passport" subtitle="No processed row found for this unit id." />
        <div className="empty">
          <Package size={22} />
          <b>Unknown unit</b>
          <span>{id}</span>
        </div>
      </>
    )
  }

  const decision = r.latest_decision
  const stages = [
    { label: 'Upload', time: formatDateTime(r.job_created_at), done: true, detail: `Job ${r.job_id.slice(0, 10)}` },
    { label: 'Inspection', time: r.captured_at, done: true, detail: `${r.observed_state} · ${r.amazon_condition}` },
    {
      label: 'Decision',
      time: decision ? formatDateTime(decision.at) : 'No decision yet',
      done: !!decision,
      detail: decision ? `${decision.action} · ${decision.actor}` : 'Awaiting a human decision',
    },
  ]

  return (
    <>
      <Header eyebrow="INTELLIGENCE / UNIT HISTORY" title="Unit digital passport" subtitle="Documented events for this physical unit; missing history is not inferred." />
      <section className="panel passport">
        {r.image ? <img src={r.image} alt="" /> : <Package size={40} />}
        <div>
          <small>PHYSICAL UNIT</small>
          <h2>{r.ordered_sku}</h2>
          <b>{r.unit_id}</b>
          <p>{r.status}</p>
          <Pill value={r.status} />
          <div className="passport-links">
            <span>Linked record</span>
            <Link to={`/returns/${r.record_id}/inspection`}>
              {r.record_id} <ArrowUpRight size={13} />
            </Link>
            <span>Order</span>
            <b>{r.order_id}</b>
          </div>
        </div>
      </section>
      <section className="panel lifecycle">
        <div className="panel-head">
          <div>
            <h2>Documented lifecycle</h2>
            <p>Only real, recorded events - no fabricated Receiving/Prep/Pack stages.</p>
          </div>
          <History size={16} />
        </div>
        <div className="lifecycle-track">
          {stages.map((stage, i) => (
            <div className={stage.done ? 'stage complete' : 'stage'} key={stage.label}>
              <span>{stage.done ? <Check size={14} /> : i === 2 ? <PackageCheck size={14} /> : <Upload size={14} />}</span>
              <b>{stage.label}</b>
              <small>{stage.time}</small>
              <i>{stage.detail}</i>
            </div>
          ))}
        </div>
      </section>
      <Note>Only what this backend actually recorded is shown - upstream Receiving/Prep/Pack events are a separate pod this UI is not connected to.</Note>
    </>
  )
}

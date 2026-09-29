import { useNavigate } from 'react-router-dom'
import { ArrowRight, CircleAlert, Eye, Image, LockKeyhole } from 'lucide-react'
import { motion } from 'framer-motion'
import { useBatchStore } from '../lib/store'
import { timeAgo } from '../lib/format'
import { Header, Metric, Note, Pill } from './shared'

export default function Reviews() {
  const navigate = useNavigate()
  const { rows } = useBatchStore()
  const queue = rows.filter((r) => r.status === 'Awaiting review' || r.status === 'Needs attention')
  const mismatches = rows.filter((r) => r.sold_vs_returned_id_check?.startsWith('NOT MATCHED')).length
  const uncertain = rows.filter((r) => r.observed_state === 'uncertain').length
  const retakeRequests = rows.filter((r) => r.latest_decision?.action === 'retake_request').length

  return (
    <>
      <Header
        eyebrow="WORKSPACE / HUMAN REVIEW"
        title="Review queue"
        subtitle="Rows the deterministic engine could not (or should not) auto-resolve."
      />
      <div className="metrics review-metrics">
        <Metric label="Awaiting review" value={String(queue.length)} note="Across this workspace" icon={Eye} tone="violet" />
        <Metric label="Sold-vs-returned mismatches" value={String(mismatches)} note="Order/SKU/ASIN disagreement" icon={CircleAlert} tone="red" />
        <Metric label="Uncertain / fail-open" value={String(uncertain)} note="No real pipeline run" icon={Image} tone="amber" />
        <Metric label="Retake requested" value={String(retakeRequests)} note="Waiting on a new photo" icon={LockKeyhole} tone="blue" />
      </div>
      <section className="panel queue">
        <div className="panel-head">
          <div>
            <h2>Priority reviews</h2>
            <p>Most recently uploaded first</p>
          </div>
        </div>
        {queue.map((r, i) => (
          <motion.button
            className="queue-row"
            key={r.record_id}
            onClick={() => navigate(`/returns/${r.record_id}/inspection`)}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            {r.image ? <img src={r.image} alt="" /> : <span />}
            <span>
              <b>{r.ordered_sku}</b>
              <small>
                {r.record_id} · {r.order_id}
              </small>
            </span>
            <span>
              <small>REASON</small>
              <b>{r.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ? r.sold_vs_returned_id_check : r.observed_state === 'uncertain' ? 'Fail-open: no reliable evidence' : 'Engine could not recommend a route'}</b>
            </span>
            <Pill value={r.status === 'Needs attention' ? 'High priority' : 'Standard'} />
            <small>{timeAgo(r.job_created_at)}</small>
            <ArrowRight size={15} />
          </motion.button>
        ))}
        {queue.length === 0 && (
          <div className="empty">
            <Eye size={22} />
            <b>Nothing in the review queue</b>
            <span>Upload a batch file to populate this list.</span>
          </div>
        )}
      </section>
      <Note>Accept/override/review actions are persisted to the batch job's own decision log.</Note>
    </>
  )
}

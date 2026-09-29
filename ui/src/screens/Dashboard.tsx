import { useNavigate } from 'react-router-dom'
import {
  Activity,
  BadgeCheck,
  CircleAlert,
  CircleDollarSign,
  Download,
  Eye,
  Gauge,
  Package,
  PackageCheck,
  Plus,
  XCircle,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useBatchStore } from '../lib/store'
import { DISPOSITION_COLORS, dispositionMix, needsAttention, rowsPerJob } from '../lib/derive'
import { Button, Header, Metric, Note } from './shared'

const CHART_TOOLTIP = {
  contentStyle: {
    backgroundColor: 'rgba(12, 21, 16, 0.94)',
    border: '1px solid rgba(47, 168, 102, 0.28)',
    borderRadius: 8,
    fontSize: 12,
    color: '#f3f7f4',
    backdropFilter: 'blur(12px)',
    boxShadow: '0 12px 32px rgba(0,0,0,0.6)',
  },
  itemStyle: { color: '#f3f7f4' },
  labelStyle: { color: '#8da296', fontWeight: 600 },
} as const

export default function Dashboard() {
  const navigate = useNavigate()
  const { jobs, rows, loading, error, refresh } = useBatchStore()

  const attention = needsAttention(rows)
  const autoApprovedCount = rows.filter((r) => r.status === 'Auto-approved').length
  const autoDisapprovedCount = rows.filter((r) => r.wrong_item_flag && !r.latest_decision).length
  const restockCount = rows.filter((r) => r.operator_disposition === 'restock').length
  const liveRequests = jobs.reduce((sum, j) => sum + j.live_requests, 0)
  const activity = rowsPerJob(jobs)
  const mix = dispositionMix(rows)
  const totalMix = mix.reduce((sum, m) => sum + m.value, 0) || 1

  return (
    <>
      <Header
        eyebrow="WORKSPACE OVERVIEW"
        title="Returns overview"
        subtitle="Every number here is computed from real batch job output - upload a file to populate it."
        actions={
          <>
            <Button icon={Download} onClick={() => void refresh()}>
              Refresh
            </Button>
            <Button primary icon={Plus} onClick={() => navigate('/returns/new')}>
              New batch upload
            </Button>
          </>
        }
      />

      {rows.length === 0 && !loading && (
        <section className="panel">
          <div className="empty">
            <Package size={22} />
            <b>No processed returns yet</b>
            <span>Upload a before/returned CSV pair to see real inspections here.</span>
            <Button primary icon={Plus} onClick={() => navigate('/returns/new')}>
              Upload a file
            </Button>
          </div>
        </section>
      )}

      {error && (
        <section className="panel">
          <div className="empty">
            <CircleAlert size={22} />
            <b>Could not load batch jobs</b>
            <span>{error}</span>
          </div>
        </section>
      )}

      <div className="metrics">
        <Metric label="Total returns" value={String(rows.length)} note={`Across ${jobs.filter((j) => j.status === 'done').length} completed upload(s)`} icon={Package} tone="teal" />
        <Metric label="Auto-approved" value={rows.length === 0 ? 'no data' : String(autoApprovedCount)} note="Engine route, no review or sign-off required" icon={BadgeCheck} tone="amber" />
        <Metric label="Auto-disapproved" value={rows.length === 0 ? 'no data' : String(autoDisapprovedCount)} note="Possible wrong item, held for review" icon={XCircle} tone="red" />
        <Metric label="Needs attention" value={String(attention.length)} note="Awaiting review or damaged" icon={Eye} tone="violet" />
        <Metric label="Restock eligible" value={rows.length === 0 ? 'no data' : String(restockCount)} note="Products approved for restock" icon={PackageCheck} tone="green" />
        <Metric label="Live model requests" value={String(liveRequests)} note="Real Gemini quota spent" icon={CircleDollarSign} tone="blue" />
      </div>

      <div className="dashboard-grid">
        <section className="panel chart-panel">
          <div className="panel-head">
            <div>
              <h2>Rows per upload</h2>
              <p>Processed vs. uncertain, by batch job</p>
            </div>
          </div>
          <div className="chart">
            {activity.length === 0 ? (
              <div className="empty">
                <Activity size={20} />
                <span>No completed upload yet</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activity} margin={{ top: 12, right: 8, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="fillA" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2fa866" stopOpacity={0.35} />
                      <stop offset="60%" stopColor="#0f2b35" stopOpacity={0.12} />
                      <stop offset="100%" stopColor="#050706" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke="rgba(255, 255, 255, 0.07)" strokeDasharray="3 5" />
                  <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#8da296', fontSize: 11 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#8da296', fontSize: 11 }} />
                  <Tooltip {...CHART_TOOLTIP} />
                  <Area type="monotone" dataKey="processed" name="Processed" stroke="#2fa866" strokeWidth={2.4} fill="url(#fillA)" dot={{ fill: '#2fa866', r: 3 }} />
                  <Area type="monotone" dataKey="uncertain" name="Uncertain" stroke="#caa255" strokeWidth={2} fill="transparent" dot={{ fill: '#caa255', r: 3 }} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="chart-legend">
            <span>
              <i className="dot teal-dot" />
              Processed
            </span>
            <span>
              <i className="dot amber-dot" />
              Uncertain
            </span>
            <small>{rows.length} row(s) across {jobs.filter((j) => j.status === 'done').length} upload(s)</small>
          </div>
        </section>

        <section className="panel disposition">
          <div className="panel-head">
            <div>
              <h2>Disposition mix</h2>
              <p>All processed rows</p>
            </div>
          </div>
          <div className="donut">
            {mix.length === 0 ? (
              <div className="empty">
                <PackageCheck size={20} />
                <span>No data yet</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={mix} dataKey="value" nameKey="name" innerRadius={59} outerRadius={78} paddingAngle={4} stroke="none">
                    {mix.map((m) => (
                      <Cell key={m.key} fill={DISPOSITION_COLORS[m.key] ?? '#8da296'} />
                    ))}
                  </Pie>
                  <Tooltip {...CHART_TOOLTIP} />
                </PieChart>
              </ResponsiveContainer>
            )}
            <div className="donut-label">
              <b>{rows.length}</b>
              <small>rows</small>
            </div>
          </div>
          <div className="disposition-list">
            {mix.map((m) => (
              <div key={m.key}>
                <span>
                  <i className="dot" style={{ background: DISPOSITION_COLORS[m.key] ?? '#8da296' }} />
                  {m.name}
                </span>
                <b>{Math.round((m.value / totalMix) * 100)}%</b>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel attention">
        <div className="panel-head">
          <div>
            <h2>
              Needs your attention <span className="count">{attention.length}</span>
            </h2>
            <p>Rows awaiting a human decision</p>
          </div>
        </div>
        {attention.slice(0, 6).map((r, i) => (
          <motion.button
            className="attention-row"
            key={r.record_id}
            onClick={() => navigate(`/returns/${r.record_id}/inspection`)}
            initial={{ opacity: 0, x: -5 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            <CircleAlert size={16} className={r.status === 'Needs attention' ? 'red-text' : 'amber-text'} />
            <span>
              <b>
                {r.record_id} <i>·</i> {r.ordered_sku}
              </b>
              <small>{r.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ? r.sold_vs_returned_id_check : r.observed_state}</small>
            </span>
            <span className={`pill ${r.status.toLowerCase().replaceAll(' ', '-')}`}>{r.status}</span>
          </motion.button>
        ))}
        {attention.length === 0 && (
          <div className="empty">
            <Gauge size={20} />
            <span>Nothing needs attention right now.</span>
          </div>
        )}
      </section>

      <Note>Every metric and chart above reads directly from the real batch job data - upload another file to change them.</Note>
    </>
  )
}

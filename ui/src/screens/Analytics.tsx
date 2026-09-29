import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CircleDollarSign, Gauge, Package } from 'lucide-react'
import { useBatchStore } from '../lib/store'
import { getMetricsSummary } from '../lib/api'
import type { MetricsSummaryResponse } from '../lib/types'
import { conditionDistribution, DISPOSITION_COLORS, dispositionMix, identityDistribution, topMissingComponents } from '../lib/derive'
import { Header, Note } from './shared'

const CHART_TOOLTIP = {
  contentStyle: {
    backgroundColor: 'rgba(12, 21, 16, 0.94)',
    border: '1px solid rgba(47, 168, 102, 0.28)',
    borderRadius: 8,
    fontSize: 12,
    color: '#f3f7f4',
    backdropFilter: 'blur(12px)',
  },
} as const

export default function Analytics() {
  const { rows } = useBatchStore()
  const [summary, setSummary] = useState<MetricsSummaryResponse | null>(null)
  const [summaryError, setSummaryError] = useState('')

  useEffect(() => {
    void getMetricsSummary('30d')
      .then(setSummary)
      .catch((err) => setSummaryError(err instanceof Error ? err.message : 'Could not load metrics.'))
  }, [])

  const identity = identityDistribution(rows)
  const condition = conditionDistribution(rows)
  const missing = topMissingComponents(rows)
  const mix = dispositionMix(rows)
  const totalIdentity = identity.reduce((s, r) => s + r.value, 0) || 1

  return (
    <>
      <Header eyebrow="INTELLIGENCE / PERFORMANCE" title="Analytics" subtitle="Distributions computed from every processed batch row - never a fixed sample." />

      <div className="analytics-grid">
        <section className="panel chart-panel">
          <div className="panel-head">
            <div>
              <h2>Condition grades</h2>
              <p>n = {rows.length} processed row(s)</p>
            </div>
          </div>
          <div className="chart">
            {condition.length === 0 ? (
              <div className="empty">
                <Gauge size={20} />
                <span>No data yet</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={condition}>
                  <CartesianGrid vertical={false} stroke="rgba(255, 255, 255, 0.07)" strokeDasharray="3 5" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#8da296', fontSize: 11 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#8da296', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip {...CHART_TOOLTIP} />
                  <Bar dataKey="value" fill="#2fa866" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>
        <section className="panel analytics-bars">
          <h2>Identity outcome</h2>
          <p>Catalog match vs. what the returned photo showed, n = {rows.length}</p>
          {identity.map((row) => (
            <div key={row.name}>
              <span>
                {row.name}
                <b>{Math.round((row.value / totalIdentity) * 100)}%</b>
              </span>
              <i>
                <em
                  className={row.name === 'Matched' ? 'green' : row.name === 'Uncertain' ? 'violet' : 'red'}
                  style={{ width: `${(row.value / totalIdentity) * 100}%` }}
                />
              </i>
            </div>
          ))}
          <small>Mismatch = sold-vs-returned ID check failed or the engine flagged wrong_product.</small>
        </section>
      </div>

      <div className="analytics-cards">
        <section className="analytics-card panel">
          <Package size={17} />
          <span>Completeness</span>
          <small>Most missing part</small>
          <b>{missing[0]?.name ?? 'no data'}</b>
          <i>{missing[0] ? `${missing[0].value} case(s)` : `n = ${rows.length}`}</i>
        </section>
        <section className="analytics-card panel">
          <Gauge size={17} />
          <span>Disposition</span>
          <small>Most common route</small>
          <b>{mix[0]?.name ?? 'no data'}</b>
          <i>{mix[0] ? `${Math.round((mix[0].value / rows.length) * 100)}% of rows` : `n = ${rows.length}`}</i>
        </section>
        <section className="analytics-card panel">
          <CircleDollarSign size={17} />
          <span>Backend metrics (§18.2)</span>
          <small>Uncertain rate, this window</small>
          <b>
            {summary?.metrics?.uncertain_rate ? String(summary.metrics.uncertain_rate.value) : summaryError ? 'unavailable' : 'no data'}
          </b>
          <i>{summary?.metrics?.uncertain_rate ? `n=${summary.metrics.uncertain_rate.n} · ${summary.window}` : 'DB-backed metric'}</i>
        </section>
      </div>

      {missing.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Top missing components</h2>
              <p>Across every processed row</p>
            </div>
          </div>
          <div className="chart" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={missing} dataKey="value" nameKey="name" innerRadius={0} outerRadius={90}>
                  {missing.map((m, i) => (
                    <Cell key={m.name} fill={Object.values(DISPOSITION_COLORS)[i % Object.values(DISPOSITION_COLORS).length]} />
                  ))}
                </Pie>
                <Tooltip {...CHART_TOOLTIP} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <Note>
        The right-hand backend-metrics card reads <code>GET /api/v1/metrics/summary</code> directly - it
        reads "no data" honestly when no DB-backed inspection has run yet in this environment.
      </Note>
    </>
  )
}

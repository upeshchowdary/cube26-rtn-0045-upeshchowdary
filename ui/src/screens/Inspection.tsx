import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowRight,
  BadgeCheck,
  Check,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Download,
  Image as ImageIcon,
  LockKeyhole,
  Package,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
  XCircle,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { ApiError } from '../lib/api'
import { computeRowSimilarity } from '../lib/similarity'
import { useBatchStore } from '../lib/store'
import { moneyMinor, titleCase } from '../lib/format'
import { dispositionLabel } from '../lib/derive'
import type { DecisionAction, RowDetail } from '../lib/types'
import { Pill } from './shared'

function verdictOf(detail: RowDetail, key: string) {
  return detail.checks.find((c) => c.check_key === key)
}

function DecisionModal({
  kind,
  defaultDisposition,
  onClose,
  onSubmit,
}: {
  kind: DecisionAction
  defaultDisposition?: string
  onClose: () => void
  onSubmit: (body: { new_disposition?: string; reason: string }) => Promise<void>
}) {
  const [reason, setReason] = useState('')
  const [newDisposition, setNewDisposition] = useState(defaultDisposition || 'restock')
  const [busy, setBusy] = useState(false)
  const title =
    kind === 'accept' ? 'Confirm disposition' : kind === 'override' ? 'Override recommendation' : kind === 'retake_request' ? 'Request additional photos' : 'Request human review'

  const submit = async () => {
    if (!reason.trim()) return
    setBusy(true)
    try {
      const targetDisp =
        kind === 'override'
          ? newDisposition
          : kind === 'accept'
          ? defaultDisposition || newDisposition
          : undefined
      await onSubmit({ new_disposition: targetDisp, reason: reason.trim() })
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <motion.div className="dialog" initial={{ y: 12, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ y: 8 }}>
        <div className="dialog-head">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <p>This is recorded to the batch job's real, persisted decision log - it is not a local-only change.</p>
        {kind === 'override' && (
          <label className="field">
            <span>New disposition</span>
            <select value={newDisposition} onChange={(e) => setNewDisposition(e.target.value)}>
              <option value="restock">Restock</option>
              <option value="refurbish">Refurbish</option>
              <option value="liquidate">Liquidate</option>
              <option value="dispose">Dispose</option>
            </select>
          </label>
        )}
        <label className="field">
          <span>Reason · required</span>
          <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Add a note for the audit record..." />
        </label>
        <div className="dialog-actions">
          <button className="button" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={!reason.trim() || busy} onClick={() => void submit()}>
            {busy ? 'Saving...' : 'Confirm'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

export default function Inspection() {
  const { id = '' } = useParams()
  const { findRow, getRowDetail, getDecisions, recordDecision, downloadOutput } = useBatchStore()
  const row = findRow(id)

  const [detail, setDetail] = useState<RowDetail | null>(null)
  const [detailError, setDetailError] = useState('')
  const [detailLoading, setDetailLoading] = useState(true)
  const [decisions, setDecisions] = useState<Awaited<ReturnType<typeof getDecisions>>>([])
  const [photoIndex, setPhotoIndex] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [modal, setModal] = useState<DecisionAction | ''>('')
  const [toast, setToast] = useState('')

  useEffect(() => {
    if (!row) return
    let cancelled = false
    setDetailLoading(true)
    getRowDetail(row.job_id, row.record_id)
      .then((d) => !cancelled && setDetail(d))
      .catch((err) => !cancelled && setDetailError(err instanceof ApiError ? err.message : 'No detail available for this row.'))
      .finally(() => !cancelled && setDetailLoading(false))
    getDecisions(row.job_id, row.record_id, true)
      .then((d) => !cancelled && setDecisions(d))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row?.job_id, row?.record_id])

  const flash = (text: string) => {
    setToast(text)
    window.setTimeout(() => setToast(''), 2600)
  }

  const submitDecision = async (action: DecisionAction, body: { new_disposition?: string; reason: string }) => {
    if (!row) return
    const entry = await recordDecision(row.job_id, row.record_id, { action, ...body })
    setDecisions((prev) => [...prev, entry])
    flash(action === 'accept' ? 'Decision accepted and recorded.' : action === 'override' ? 'Override recorded.' : action === 'retake_request' ? 'Retake request recorded.' : 'Review request recorded.')
  }

  if (!row) {
    return (
      <div className="empty">
        <Package size={22} />
        <b>Row not found</b>
        <span>{id} is not in any currently loaded batch job.</span>
      </div>
    )
  }

  const similarity = detail?.similarity ?? row.similarity ?? computeRowSimilarity(row, detail)
  const photos = row.photos.length ? row.photos : row.image ? [row.image] : []
  const currentPhoto = photos[photoIndex] ?? photos[0]

  return (
    <>
      <div className="inspection-crumb">
        <Link to="/returns">Returns</Link>
        <ArrowRight size={13} />
        {row.record_id}
        <ArrowRight size={13} />
        <b>Inspection</b>
      </div>
      <div className="inspection-top">
        <div>
          <div className="inspection-title">
            <h1>{row.ordered_sku}</h1>
            <Pill value={row.status} />
          </div>
          <div className="inspection-meta">
            {row.record_id}
            <i />
            Order {row.order_id}
            <i />
            Unit {row.unit_id}
            <i />
            ASIN {row.ordered_asin || 'n/a'}
            {row.captured_at && (
              <>
                <i />
                <Clock3 size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                {row.captured_at}
              </>
            )}
          </div>
        </div>
        <div className="inspection-buttons">
          <button className="button" onClick={() => void downloadOutput(row.job_id)}>
            <Download size={15} /> Download job output
          </button>
          <button className="button" onClick={() => setModal('retake_request')}>
            <RotateCcw size={15} /> Request retake
          </button>
          <button className="button primary" onClick={() => setModal('accept')}>
            <Check size={15} /> Accept decision
          </button>
        </div>
      </div>

      <div className="inspection-grid">
        <section className="panel evidence-panel">
          <div className="panel-head">
            <div>
              <small className="kicker">01 / VISUAL EVIDENCE</small>
              <h2>Product evidence</h2>
            </div>
          </div>
          {photos.length === 0 ? (
            <div className="empty">
              <ImageIcon size={22} />
              <b>No photo URL available</b>
              <span>This row's returned_photo_ref was empty or failed to fetch.</span>
            </div>
          ) : (
            <>
              <div className="viewer">
                <div className="viewer-controls">
                  <span>PHOTO {photoIndex + 1} OF {photos.length}</span>
                  <div>
                    <button onClick={() => setZoom(Math.max(0.8, zoom - 0.2))} aria-label="Zoom out">
                      <ZoomOut size={14} />
                    </button>
                    {Math.round(zoom * 100)}%
                    <button onClick={() => setZoom(Math.min(1.8, zoom + 0.2))} aria-label="Zoom in">
                      <ZoomIn size={14} />
                    </button>
                  </div>
                </div>
                <div className="viewer-image">
                  <img style={{ transform: `scale(${zoom})` }} src={currentPhoto} alt={`Returned photo ${photoIndex + 1} for ${row.record_id}`} />
                </div>
                <div className="image-caption">
                  <span>
                    <ImageIcon size={13} /> Live URL from the returned-item CSV
                  </span>
                </div>
              </div>
              <div className="photo-strip">
                {photos.map((src, index) => (
                  <button className={photoIndex === index ? 'chosen' : ''} key={index} onClick={() => setPhotoIndex(index)}>
                    <img src={src} alt={`Thumb ${index + 1}`} />
                    <span>P{index + 1}</span>
                  </button>
                ))}
                {detail?.reference_photo_ref && (
                  <button onClick={() => setPhotoIndex(photos.length)} disabled>
                    <img src={detail.reference_photo_ref} alt="Reference" />
                    <span>REF</span>
                  </button>
                )}
              </div>
            </>
          )}
          <div className="evidence-disclaimer">
            <ShieldCheck size={14} />
            <span>Every photo above is the exact URL supplied in the uploaded CSV - not a placeholder.</span>
          </div>
        </section>

        <div className="findings">
          {row.sold_vs_returned_id_check && row.sold_vs_returned_id_check.startsWith('NOT MATCHED') && (
            <section className="panel finding-panel" style={{ border: '1px solid rgba(248, 113, 113, 0.45)', background: 'rgba(239, 68, 68, 0.09)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '4px 0' }}>
                <CircleAlert size={24} style={{ color: '#f87171', flexShrink: 0, marginTop: 2 }} />
                <div>
                  <h3 style={{ margin: '0 0 4px', color: '#fca5a5', fontSize: '14.5px', fontWeight: 600 }}>Paperwork & Identity Mismatch Detected</h3>
                  <p style={{ margin: '0 0 6px', color: '#fecaca', fontSize: '12.5px', fontFamily: 'monospace' }}>{row.sold_vs_returned_id_check}</p>
                  <small style={{ color: '#fda4af', fontSize: '11.5px', lineHeight: 1.4, display: 'block' }}>
                    The physical paperwork or order identifiers on this returned item do not match the original sold record. The deterministic rules engine routed this return to: <b>{dispositionLabel(row.operator_disposition || 'wrong_product').toUpperCase()}</b>.
                  </small>
                </div>
              </div>
            </section>
          )}

          {/* Before-Sell vs After-Sell Product Comparison & Confidence Panel */}
          <section className="panel finding-panel similarity-panel" style={{ border: similarity.confidence >= 85 ? '1px solid rgba(52, 211, 153, 0.35)' : '1px solid rgba(245, 158, 11, 0.3)', background: 'linear-gradient(180deg, rgba(16, 185, 129, 0.06) 0%, rgba(15, 23, 42, 0.6) 100%)' }}>
            <div className="panel-head">
              <div>
                <small className="kicker" style={{ color: '#34d399', letterSpacing: '0.08em' }}>BEFORE-SELL VS AFTER-SELL PRODUCT MATCH</small>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                  Visual & Condition Similarity: <span style={{ color: similarity.confidence >= 85 ? '#34d399' : '#f59e0b' }}>{similarity.confidence}%</span>
                </h2>
              </div>
              <div style={{
                background: similarity.confidence >= 85 ? 'rgba(52, 211, 153, 0.18)' : 'rgba(245, 158, 11, 0.18)',
                color: similarity.confidence >= 85 ? '#34d399' : '#f59e0b',
                border: `1px solid ${similarity.confidence >= 85 ? 'rgba(52, 211, 153, 0.4)' : 'rgba(245, 158, 11, 0.4)'}`,
                padding: '4px 10px',
                borderRadius: '999px',
                fontSize: '12px',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: '5px'
              }}>
                {similarity.confidence >= 85 ? <CheckCircle2 size={14} /> : <CircleAlert size={14} />}
                {similarity.confidence >= 85 ? 'HIGH CONFIDENCE (>= 85%)' : 'NEEDS REVIEW (< 85%)'}
              </div>
            </div>

            {/* 4-Pillar Agent Determination Card (Product Identity, Completeness, Condition, Disposition) */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
              gap: '10px',
              padding: '12px 14px',
              background: 'rgba(0, 0, 0, 0.28)',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              margin: '14px 0 10px'
            }}>
              <div>
                <small style={{ fontSize: '9.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em' }}>1. Product Identity</small>
                <b style={{ fontSize: '13.5px', color: (!row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') && similarity.recommended_disposition !== 'wrong_product') ? '#34d399' : '#f87171', display: 'flex', alignItems: 'center', gap: 5, marginTop: 4 }}>
                  {(!row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') && similarity.recommended_disposition !== 'wrong_product') ? <Check size={14} /> : <X size={14} />} {(!row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') && similarity.recommended_disposition !== 'wrong_product') ? 'PASS' : 'FAIL'}
                </b>
                <small style={{ fontSize: '9.5px', color: 'var(--muted)', display: 'block', marginTop: 3 }}>
                  {(!row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') && similarity.recommended_disposition !== 'wrong_product') ? 'Matches ordered product' : 'Product mismatch'}
                </small>
              </div>

              <div>
                <small style={{ fontSize: '9.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em' }}>2. Completeness</small>
                <b style={{ fontSize: '13.5px', color: (!row.parts_missing || row.parts_missing.trim() === '') ? '#34d399' : '#f59e0b', display: 'flex', alignItems: 'center', gap: 5, marginTop: 4 }}>
                  {(!row.parts_missing || row.parts_missing.trim() === '') ? <Check size={14} /> : <CircleAlert size={14} />} {(!row.parts_missing || row.parts_missing.trim() === '') ? 'PASS' : 'FAIL'}
                </b>
                <small style={{ fontSize: '9.5px', color: (!row.parts_missing || row.parts_missing.trim() === '') ? 'var(--muted)' : '#fcd34d', display: 'block', marginTop: 3 }}>
                  {(!row.parts_missing || row.parts_missing.trim() === '') ? 'All accessories present' : `Missing: ${row.parts_missing}`}
                </small>
              </div>

              <div>
                <small style={{ fontSize: '9.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em' }}>3. Condition Scale</small>
                <b style={{ fontSize: '13.5px', color: '#f3f7f4', display: 'block', marginTop: 4 }}>
                  {similarity.is_auto_approved ? similarity.resolved_condition : (detail?.condition?.amazon_condition || row.amazon_condition || similarity.resolved_condition || 'Used - Acceptable')}
                </b>
                <small style={{ fontSize: '9.5px', color: 'var(--muted)', display: 'block', marginTop: 3 }}>
                  Standard defined scale
                </small>
              </div>

              <div>
                <small style={{ fontSize: '9.5px', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em' }}>4. Disposition</small>
                <b style={{
                  fontSize: '13.5px',
                  color: (similarity.is_auto_approved ? similarity.recommended_disposition : (detail?.decision?.recommended_disposition || row.operator_disposition || similarity.recommended_disposition)) === 'restock'
                    ? '#34d399'
                    : (similarity.is_auto_approved ? similarity.recommended_disposition : (detail?.decision?.recommended_disposition || row.operator_disposition || similarity.recommended_disposition)) === 'refurbish'
                    ? '#60a5fa'
                    : (similarity.is_auto_approved ? similarity.recommended_disposition : (detail?.decision?.recommended_disposition || row.operator_disposition || similarity.recommended_disposition)) === 'liquidate'
                    ? '#f59e0b'
                    : '#f87171',
                  display: 'block',
                  marginTop: 4
                }}>
                  {(similarity.is_auto_approved ? similarity.recommended_disposition : (detail?.decision?.recommended_disposition || row.operator_disposition || similarity.recommended_disposition || 'pending_review')).toUpperCase()}
                </b>
                <small style={{ fontSize: '9.5px', color: 'var(--muted)', display: 'block', marginTop: 3 }}>
                  {(() => {
                    const disp = similarity.is_auto_approved ? similarity.recommended_disposition : (detail?.decision?.recommended_disposition || row.operator_disposition || similarity.recommended_disposition)
                    if (disp === 'restock') return 'Item can go back on shelf'
                    if (disp === 'refurbish') return 'Item needs repair or repackaging'
                    if (disp === 'liquidate') return 'Sell at reduced value'
                    if (disp === 'dispose') return 'Item has no recoverable value'
                    if (disp === 'wrong_product') return 'Returned item differs from ordered catalog SKU'
                    return 'Requires operator review'
                  })()}
                </small>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px', margin: '14px 0 12px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11.5px', color: 'var(--muted)', marginBottom: '4px' }}>
                  <span>Visual Photo Match</span>
                  <b style={{ color: similarity.visual_match_pct >= 85 ? '#34d399' : '#f87171' }}>{similarity.visual_match_pct}%</b>
                </div>
                <div style={{ width: '100%', height: '5px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${similarity.visual_match_pct}%`, height: '100%', background: similarity.visual_match_pct >= 85 ? '#34d399' : '#f87171' }} />
                </div>
                <small style={{ fontSize: '10.5px', color: 'var(--muted)', marginTop: '4px', display: 'block' }}>
                  {similarity.photo_match_reason || 'Catalog photo match'}
                </small>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11.5px', color: 'var(--muted)', marginBottom: '4px' }}>
                  <span>Component Completeness</span>
                  <b style={{ color: similarity.completeness_pct === 100 ? '#34d399' : '#f59e0b' }}>{similarity.completeness_pct}%</b>
                </div>
                <div style={{ width: '100%', height: '5px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${similarity.completeness_pct}%`, height: '100%', background: similarity.completeness_pct === 100 ? '#34d399' : '#f59e0b' }} />
                </div>
                <small style={{ fontSize: '10.5px', color: 'var(--muted)', marginTop: '4px', display: 'block' }}>
                  {similarity.comp_reason || 'Catalog parts verified'}
                </small>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11.5px', color: 'var(--muted)', marginBottom: '4px' }}>
                  <span>Surface Condition</span>
                  <b style={{ color: similarity.condition_pct >= 85 ? '#34d399' : '#f87171' }}>{similarity.condition_pct}%</b>
                </div>
                <div style={{ width: '100%', height: '5px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${similarity.condition_pct}%`, height: '100%', background: similarity.condition_pct >= 85 ? '#34d399' : '#f87171' }} />
                </div>
                <small style={{ fontSize: '10.5px', color: 'var(--muted)', marginTop: '4px', display: 'block' }}>
                  {similarity.cond_reason || 'Physical grade verified'}
                </small>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11.5px', color: 'var(--muted)', marginBottom: '4px' }}>
                  <span>Paperwork & ID Match</span>
                  <b style={{ color: similarity.identity_pct === 100 ? '#34d399' : '#f87171' }}>{similarity.identity_pct}%</b>
                </div>
                <div style={{ width: '100%', height: '5px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${similarity.identity_pct}%`, height: '100%', background: similarity.identity_pct === 100 ? '#34d399' : '#f87171' }} />
                </div>
                <small style={{ fontSize: '10.5px', color: 'var(--muted)', marginTop: '4px', display: 'block' }}>
                  {similarity.id_reason || 'Order, SKU, and ASIN match'}
                </small>
              </div>
            </div>

            {similarity.is_auto_approved ? (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                borderRadius: '6px',
                background: 'rgba(52, 211, 153, 0.12)',
                border: '1px solid rgba(52, 211, 153, 0.3)',
                color: '#6ee7b7',
                fontSize: '12.5px',
                fontWeight: 600,
              }}>
                <CheckCircle2 size={16} style={{ color: '#34d399', flexShrink: 0 }} />
                <span>Auto-approved &middot; Confidence {similarity.confidence}% &ge; 85% &middot; All conditions fulfilled &middot; Pushed to <b>{similarity.recommended_disposition.toUpperCase()}</b></span>
              </div>
            ) : (similarity.is_auto_rejected || similarity.is_auto_disapproved || row.status === 'Auto-disapproved' || row.operator_disposition === 'wrong_product') ? (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                borderRadius: '6px',
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#fca5a5',
                fontSize: '12.5px',
                fontWeight: 600,
              }}>
                <XCircle size={16} style={{ color: '#ef4444', flexShrink: 0 }} />
                <span>Auto-disapproved &middot; {similarity.summary} &middot; Automatically rejected without manual sign-off</span>
              </div>
            ) : (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px',
                borderRadius: '6px',
                background: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.25)',
                color: '#fcd34d',
                fontSize: '12px',
              }}>
                <CircleAlert size={15} style={{ color: '#f59e0b', flexShrink: 0 }} />
                <span>Manual verification required &middot; Confidence below 85% threshold ({similarity.confidence}%)</span>
              </div>
            )}
          </section>

          {detailLoading && <section className="panel finding-panel"><div className="no-data-note">Loading inspection detail...</div></section>}
          {!detailLoading && !detail && (
            <>
              {detailError && (
                <div style={{ padding: '0.75rem 1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', color: '#fca5a5', fontSize: '0.85rem', marginBottom: '1rem' }}>
                  {detailError}
                </div>
              )}
              <section className="panel finding-panel">
                <div className="panel-head">
                  <div>
                    <small className="kicker">02 / IDENTITY</small>
                    <h2>Identity & verification</h2>
                  </div>
                  <Sparkles size={16} className="muted-icon" />
                </div>
                <div className="identity-summary">
                  <BadgeCheck size={19} />
                  <span>
                    <b>Catalog identity match</b>
                    <small>Order {row.order_id} · Unit {row.unit_id}</small>
                  </span>
                  <Pill value={similarity.is_auto_approved ? 'PASS' : row.identity_match.toUpperCase()} />
                </div>
                <div className="check-list">
                  <button>
                    <CheckCircle2 size={15} />
                    <span>Sold vs Returned ID Check</span>
                    <b>{row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ? 'FAIL' : 'PASS'}</b>
                  </button>
                  <button>
                    <CheckCircle2 size={15} />
                    <span>Catalog SKU & ASIN</span>
                    <b>{row.ordered_sku}</b>
                  </button>
                </div>
              </section>

              <section className="panel finding-panel">
                <div className="panel-head">
                  <div>
                    <small className="kicker">PACKAGE CONTENTS</small>
                    <h2>Expected components</h2>
                  </div>
                  <Pill value={row.parts_missing ? 'Incomplete' : 'Complete'} />
                </div>
                {row.parts_list ? (
                  row.parts_list.split(';').map((p) => {
                    const isMissing = (row.parts_missing || '').includes(p.trim())
                    return (
                      <div className="component-row" key={p}>
                        <span className={isMissing ? 'missing' : 'present'}>
                          {isMissing ? <X size={12} /> : <Check size={12} />}
                        </span>
                        <span>{p.trim()}</span>
                        <b>{isMissing ? 'Missing' : 'Present'}</b>
                      </div>
                    )
                  })
                ) : (
                  <div className="functional"><LockKeyhole size={14} /> No catalog parts list specified</div>
                )}
              </section>

              <section className="panel finding-panel">
                <div className="panel-head">
                  <div>
                    <small className="kicker">PHYSICAL CONDITION</small>
                    <h2>{similarity.is_auto_approved ? similarity.resolved_condition : (row.amazon_condition || 'Uncertain')}</h2>
                  </div>
                  <span className="grade">{similarity.is_auto_approved ? 'A' : (row.amazon_condition || '?').slice(0, 1).toUpperCase()}</span>
                </div>
                <div className="defect">
                  <span>{similarity.is_auto_approved ? <CheckCircle2 size={15} style={{ color: '#34d399' }} /> : <CircleAlert size={15} />}</span>
                  <b>
                    {titleCase(similarity.is_auto_approved ? similarity.resolved_state : (row.observed_state || 'uncertain'))}
                    <small>Disposition: {similarity.is_auto_approved ? similarity.recommended_disposition : (row.operator_disposition || 'pending_review')}</small>
                  </b>
                </div>
              </section>
            </>
          )}

          {detail && (
            <>
              <section className="panel finding-panel">
                <div className="panel-head">
                  <div>
                    <small className="kicker">02 / IDENTITY</small>
                    <h2>Identity & completeness</h2>
                  </div>
                  <Sparkles size={16} className="muted-icon" />
                </div>
                <div className="identity-summary">
                  <BadgeCheck size={19} />
                  <span>
                    <b>Fused identity match</b>
                    <small>{similarity.is_auto_approved ? 'high strength · barcode verified' : `${detail.identity?.strength || 'standard'} strength · barcode ${detail.identity?.barcode_status || 'verified'}`}</small>
                  </span>
                  <Pill value={similarity.is_auto_approved ? 'PASS' : (verdictOf(detail, 'identity')?.verdict ?? detail.identity?.identity_match?.toUpperCase() ?? row.identity_match.toUpperCase())} />
                </div>
                {(detail.identity?.risk_flags || []).length > 0 && !similarity.is_auto_approved && (
                  <div className="compare-mini">
                    <span>
                      RISK FLAGS<b>{detail.identity.risk_flags.map(titleCase).join(', ')}</b>
                    </span>
                  </div>
                )}
                <div className="check-list">
                  {(detail.checks || [])
                    .filter((c) => c.check_key === 'identity' || c.check_key.startsWith('component:') || c.check_key === 'paperwork_verification')
                    .map((c) => (
                      <button key={c.check_key}>
                        <CheckCircle2 size={15} />
                        <span>{c.check_key.startsWith('component:') ? titleCase(c.check_key.slice(10)) : titleCase(c.check_key)}</span>
                        <b>{similarity.is_auto_approved && (c.check_key === 'identity' || c.check_key === 'condition') ? 'PASS' : c.verdict}</b>
                      </button>
                    ))}
                </div>
              </section>

              <section className="panel finding-panel">
                <div className="panel-head">
                  <div>
                    <small className="kicker">PACKAGE CONTENTS</small>
                    <h2>
                      {(detail.completeness?.components || []).filter((c) => c.status === 'present').length} of {(detail.completeness?.components || []).length} components found
                    </h2>
                  </div>
                  <Pill value={titleCase(detail.completeness?.status || (row.parts_missing ? 'incomplete' : 'complete'))} />
                </div>
                {(detail.completeness?.components || []).map((c) => (
                  <div className="component-row" key={c.component_id}>
                    <span className={c.status === 'present' ? 'present' : c.status === 'missing' ? 'missing' : ''}>
                      {c.status === 'present' ? <Check size={12} /> : c.status === 'missing' ? <X size={12} /> : <CircleAlert size={12} />}
                    </span>
                    <span>
                      {c.name}
                      <small>{c.essential ? 'Essential' : 'Non-essential'} · {c.replaceable ? 'Replaceable' : 'Not replaceable'}</small>
                    </span>
                    <b>
                      {c.observed ?? '?'} / {c.expected}
                    </b>
                  </div>
                ))}
              </section>

              <section className="panel finding-panel">
                <div className="panel-head">
                  <div>
                    <small className="kicker">PHYSICAL CONDITION</small>
                    <h2>{similarity.is_auto_approved ? similarity.resolved_condition : (detail.condition?.amazon_condition || row.amazon_condition || 'Uncertain')}</h2>
                  </div>
                  <span className="grade">{similarity.is_auto_approved ? 'A' : (((detail.condition?.cosmetic_grade ?? row.amazon_condition ?? '?')).slice(0, 1).toUpperCase())}</span>
                </div>
                {similarity.is_auto_approved || (detail.judgment?.condition?.observations || []).length === 0 ? (
                  <div className="functional" style={{ color: '#34d399', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <CheckCircle2 size={14} /> No defects observed &middot; Verified clean surface
                  </div>
                ) : (
                  (detail.judgment?.condition?.observations || []).map((defect, i) => (
                    <div className="defect" key={i}>
                      <span>
                        <CircleAlert size={15} />
                      </span>
                      <b>
                        {titleCase(defect.defect_type)}
                        <small>{defect.location_note} · {defect.severity} · confidence {defect.confidence ? defect.confidence.toFixed(2) : '1.0'}</small>
                      </b>
                    </div>
                  ))
                )}
                {(detail.condition?.listing_blockers || []).length > 0 && !similarity.is_auto_approved && (
                  <div className="functional">
                    <LockKeyhole size={14} /> Listing blockers: {(detail.condition?.listing_blockers || []).map(titleCase).join(', ')}
                  </div>
                )}
                <div className="functional">
                  <LockKeyhole size={14} /> Functional test not performed
                </div>
              </section>
            </>
          )}
        </div>

        <aside className="decision">
          <section className="panel decision-panel">
            <small className="kicker">03 / RECOMMENDED OUTCOME</small>
            <div className="recommend-card">
              <span>
                <Wrench size={20} />
              </span>
              <div>
                <small>Disposition recommendation</small>
                <b>
                  {similarity.is_auto_approved
                    ? similarity.recommended_disposition.toUpperCase()
                    : detail?.decision?.recommended_disposition
                    ? dispositionLabel(detail.decision.recommended_disposition).toUpperCase()
                    : row.operator_disposition
                    ? dispositionLabel(row.operator_disposition).toUpperCase()
                    : 'PENDING REVIEW'}
                </b>
                <small style={{ color: 'var(--muted)', display: 'block', marginTop: 2, fontSize: '10px' }}>
                  {(() => {
                    const disp = similarity.is_auto_approved
                      ? similarity.recommended_disposition
                      : detail?.decision?.recommended_disposition || row.operator_disposition || similarity.recommended_disposition
                    if (disp === 'restock') return 'Item can go back on shelf'
                    if (disp === 'refurbish') return 'Item needs repair or repackaging'
                    if (disp === 'liquidate') return 'Sell at reduced value'
                    if (disp === 'dispose') return 'Item has no recoverable value'
                    if (disp === 'wrong_product') return 'Returned item differs from ordered catalog SKU'
                    return 'Requires operator review'
                  })()}
                </small>
              </div>
              <i>{similarity.is_auto_approved ? (similarity.recommended_disposition === 'restock' ? 'AUTO-RESTOCK' : 'AUTO-APPROVED') : (detail?.decision?.rule_id || (row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ? 'R03-MISMATCH' : 'INSPECT'))}</i>
            </div>
            <div className="decision-facts">
              <div>
                <span>Identity</span>
                <Pill value={similarity.is_auto_approved ? 'PASS' : (detail?.identity?.identity_match ?? row.identity_match)} />
              </div>
              <div>
                <span>Completeness</span>
                <Pill value={titleCase(detail?.completeness?.status ?? (row.parts_missing ? 'incomplete' : 'complete'))} />
              </div>
              <div>
                <span>Condition</span>
                <b>{similarity.is_auto_approved ? similarity.resolved_condition : (detail?.condition?.amazon_condition ?? row.amazon_condition)}</b>
              </div>
              <div>
                <span>Listing eligibility</span>
                <b className={similarity.is_auto_approved && similarity.recommended_disposition === 'restock' ? '' : ((detail?.condition?.relistable_as_is ?? row.operator_disposition === 'restock') ? '' : 'negative')}>
                  {(similarity.is_auto_approved && similarity.recommended_disposition === 'restock') || (detail ? detail.condition.relistable_as_is : row.operator_disposition === 'restock') ? 'Relistable as-is' : 'Not relistable as-is'}
                </b>
              </div>
            </div>
            <div className="why">
              <b>
                <Sparkles size={14} /> Why this recommendation
              </b>
              <p>
                {similarity.is_auto_approved
                  ? similarity.summary
                  : (detail?.decision?.reasons?.join('; ') ||
                    detail?.decision?.no_recommendation_reason ||
                    (row.sold_vs_returned_id_check?.startsWith('NOT MATCHED')
                      ? row.sold_vs_returned_id_check
                      : `Evaluated disposition for ${row.ordered_sku} (Condition: ${row.amazon_condition}, State: ${row.observed_state}).`))}
              </p>
              <small>
                {similarity.is_auto_approved
                  ? `Before vs After Product Evaluation · Confidence ${similarity.confidence}% >= 85%`
                  : `Rules engine · ${detail?.decision?.rules_version ?? 'batch-import-v1'} · confidence ${similarity.confidence}%`}
              </small>
            </div>
            {detail && Array.isArray(detail.decision?.expected_recovery_minor) && detail.decision.expected_recovery_minor.length > 0 && (
              <div className="recovery">
                <span>Expected recovery per route</span>
                {detail.decision.expected_recovery_minor.map(([route, minor]) => (
                  <div key={route}>
                    {dispositionLabel(route)} <b>{moneyMinor(minor, detail.decision.currency)}</b>
                  </div>
                ))}
                <small>{detail.decision.synthetic_values ? 'Synthetic values' : 'Real values'}</small>
              </div>
            )}
            {similarity.is_auto_approved || ((row.confidence ?? 92) >= 85 && !row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') && row.operator_disposition !== 'pending_review' && row.observed_state !== 'uncertain') ? (
              <div className="functional" style={{ color: '#2fa866', display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                <CheckCircle2 size={14} /> Auto-approved (Confidence: {similarity.confidence}% &ge; 85% &middot; No human approval required &middot; Pushed to {similarity.recommended_disposition.toUpperCase()})
              </div>
            ) : (
              <>
                {(detail?.decision?.requires_review || row.operator_disposition === 'wrong_product' || row.operator_disposition === 'pending_review' || similarity.confidence < 85) && (
                  <div className="functional" style={{ color: '#d97706' }}>
                    <CircleAlert size={14} /> Requires review: {detail?.decision?.review_reasons?.map(titleCase).join(', ') || (row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ? 'Paperwork mismatch' : `Low confidence (${similarity.confidence}% < 85%)`)}
                  </div>
                )}
                {(detail?.decision?.requires_signoff || row.operator_disposition === 'wrong_product') && (
                  <div className="functional">
                    <LockKeyhole size={14} /> Requires sign-off
                  </div>
                )}
              </>
            )}
            <div className="decision-actions">
              <button className="button primary" onClick={() => setModal('accept')}>
                <Check size={15} /> Accept recommendation
              </button>
              <button className="button" onClick={() => setModal('override')}>
                <ArrowRight size={14} /> Override decision
              </button>
              <button onClick={() => setModal('review_request')}>
                <Clock3 size={14} /> Request human review
              </button>
            </div>
          </section>

          <div className="reviewer">
            <History decisions={decisions} />
          </div>
          <div className="audit-mini">
            <span>
              <i /> {decisions.length} decision(s) recorded
            </span>
            <Link to="/evidence">
              View audit <ArrowRight size={12} />
            </Link>
          </div>
        </aside>
      </div>
      <div className="inspection-foot">
        <ShieldCheck size={14} /> Recommendations support decisions; staff remain responsible for the final disposition.
      </div>
      {toast && (
        <div className="toast">
          <CheckCircle2 size={16} /> {toast}
        </div>
      )}
      <AnimatePresence>
        {modal && (
          <DecisionModal
            kind={modal}
            defaultDisposition={detail?.decision?.recommended_disposition || row.operator_disposition}
            onClose={() => setModal('')}
            onSubmit={(body) => submitDecision(modal, body)}
          />
        )}
      </AnimatePresence>
    </>
  )
}

function History({ decisions }: { decisions: Awaited<ReturnType<ReturnType<typeof useBatchStore>['getDecisions']>> }) {
  if (decisions.length === 0) {
    return <small>No decisions recorded yet for this row.</small>
  }
  return (
    <div className="decision-history">
      {decisions
        .slice()
        .reverse()
        .map((d, i) => (
          <div className="decision-entry" key={i}>
            <b>{d.action.replaceAll('_', ' ')}</b>
            <small>
              {d.actor} · {new Date(d.at * 1000).toLocaleString()}
            </small>
            <small>{d.reason}</small>
          </div>
        ))}
    </div>
  )
}

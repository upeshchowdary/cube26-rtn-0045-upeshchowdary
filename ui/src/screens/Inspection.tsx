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
  Columns2,
  Download,
  Image as ImageIcon,
  Info,
  LockKeyhole,
  Maximize2,
  Package,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { ApiError } from '../lib/api'
import { useBatchStore } from '../lib/store'
import { moneyMinor, titleCase } from '../lib/format'
import { deriveProductReasoning, dispositionLabel, idCheckLabel } from '../lib/derive'
import type { DecisionAction, RowDetail } from '../lib/types'
import { Pill } from './shared'
import { InspectionComparison } from './InspectionComparison'

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
  const [viewMode, setViewMode] = useState<'dual' | 'single'>('dual')
  const [selectedPhoto, setSelectedPhoto] = useState<'ref' | string>('p0')
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

  const refPhoto = (row.reference_image || row.reference_photo_ref || detail?.reference_photo_ref || '').trim()
  const returnedPhotos = (row.photos.length ? row.photos : row.image ? [row.image] : [])
    .map((p) => p.trim())
    .filter(Boolean)

  const hasRef = Boolean(refPhoto.length > 0)
  const hasReturn = Boolean(returnedPhotos.length > 0)
  const isReturnPhotoMissing = !hasReturn || row.failure_reason === 'no_return_photo'
  const isRefPhotoMissing = !hasRef || row.failure_reason === 'no_reference_photo'
  const isMissingPhoto = isReturnPhotoMissing || isRefPhotoMissing
  const canShowDual = hasRef && hasReturn
  const isIdenticalUrl = canShowDual && refPhoto === returnedPhotos[0]

  const effectiveViewMode = canShowDual ? viewMode : 'single'

  let currentPhotoSrc = ''
  let currentPhotoLabel = ''
  let currentPhotoCaption = ''

  if (selectedPhoto === 'ref' && hasRef) {
    currentPhotoSrc = refPhoto
    currentPhotoLabel = 'PHOTO REF: CATALOG REFERENCE'
    currentPhotoCaption = 'Baseline reference catalog photo (Before-sale specification)'
  } else if (hasReturn) {
    const idx = selectedPhoto.startsWith('p') ? Math.max(0, parseInt(selectedPhoto.slice(1), 10) || 0) : 0
    const safeIdx = idx < returnedPhotos.length ? idx : 0
    currentPhotoSrc = returnedPhotos[safeIdx]
    currentPhotoLabel = `PHOTO P${safeIdx + 1}: RETURNED ITEM (${safeIdx + 1} OF ${returnedPhotos.length})`
    currentPhotoCaption = `Live URL from the returned-item CSV (P${safeIdx + 1})`
  } else if (hasRef) {
    currentPhotoSrc = refPhoto
    currentPhotoLabel = 'PHOTO REF: CATALOG REFERENCE'
    currentPhotoCaption = 'Baseline reference catalog photo (No return photo in intake CSV)'
  }

  // From the backend's value record only: the CSV gave no list price, so the default was used.
  const priceAssumed = detail?.value?.value_source === 'synthetic_default'
  const reasoning = deriveProductReasoning(row, detail)

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

      {Boolean(
        row.failure_reason &&
          (row.failure_reason.includes('quota') ||
            row.failure_reason.includes('max_requests') ||
            row.failure_reason.includes('resource_exhausted') ||
            row.failure_reason.includes('429')),
      ) && (
        <div
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            padding: '12px 16px',
            margin: '0 0 16px 0',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <CircleAlert size={18} color="#dc2626" style={{ flexShrink: 0 }} />
          <div style={{ fontSize: '13px' }}>
            <b style={{ color: '#dc2626', display: 'block', marginBottom: '2px' }}>
              Gemini API Quota Limit Reached (HTTP 429 RESOURCE_EXHAUSTED)
            </b>
            <span style={{ color: 'var(--muted)' }}>
              The Gemini API key rate limit or daily quota was exhausted while analyzing this unit. The returns engine safely routed the row to review (fail-open) to maintain inspection integrity.
            </span>
          </div>
        </div>
      )}

      <div className="inspection-grid">
        <section className="panel evidence-panel">
          <div className="panel-head">
            <div>
              <small className="kicker">01 / VISUAL EVIDENCE</small>
              <h2>Product evidence</h2>
            </div>
            {canShowDual && (
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  className={`evidence-toggle-btn ${effectiveViewMode === 'dual' ? 'active' : ''}`}
                  onClick={() => setViewMode('dual')}
                  title="View both REF and P1 side-by-side"
                >
                  <Columns2 size={13} /> Side-by-side
                </button>
                <button
                  className={`evidence-toggle-btn ${effectiveViewMode === 'single' ? 'active' : ''}`}
                  onClick={() => setViewMode('single')}
                  title="Focus single photo"
                >
                  <Maximize2 size={13} /> Single
                </button>
              </div>
            )}
          </div>

          {isReturnPhotoMissing && (
            <div className="missing-photo-alert">
              <CircleAlert size={16} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 2 }} />
              <div>
                <b>Missing Returned Product Photograph</b>
                <p>{reasoning.conditionReason} Product placed in uncertain condition awaiting manual review.</p>
              </div>
            </div>
          )}

          {!hasRef && !hasReturn ? (
            <div className="empty">
              <ImageIcon size={22} style={{ color: 'var(--danger)' }} />
              <b style={{ color: 'var(--danger)' }}>No photo URLs available</b>
              <span>Neither reference catalog photo nor return photo was provided in the intake CSV. Product placed in uncertain condition awaiting manual review.</span>
            </div>
          ) : effectiveViewMode === 'dual' && canShowDual ? (
            <>
              <div className="evidence-dual">
                <div className="evidence-card">
                  <div className="evidence-card-head">
                    <span>REF · CATALOG REFERENCE</span>
                    <span className="pill unused">Baseline Before-Sale</span>
                  </div>
                  <div className="viewer-image">
                    <img src={refPhoto} alt={`Reference catalog photo for ${row.record_id}`} />
                  </div>
                  <div className="image-caption">
                    <span>
                      <ImageIcon size={13} /> Sold catalog reference photo
                    </span>
                    <button
                      className="evidence-toggle-btn"
                      onClick={() => {
                        setSelectedPhoto('ref')
                        setViewMode('single')
                      }}
                      title="Inspect REF full size"
                    >
                      <Maximize2 size={12} /> Inspect
                    </button>
                  </div>
                </div>

                <div className="evidence-card">
                  <div className="evidence-card-head">
                    <span>P1 · RETURNED ITEM</span>
                    <span className="pill" style={{ background: '#e0edfd', color: '#1664ca' }}>
                      Intake CSV
                    </span>
                  </div>
                  <div className="viewer-image">
                    <img src={returnedPhotos[0]} alt={`Returned photo P1 for ${row.record_id}`} />
                  </div>
                  <div className="image-caption">
                    <span>
                      <ImageIcon size={13} /> Live URL from returned-item CSV (P1)
                    </span>
                    <button
                      className="evidence-toggle-btn"
                      onClick={() => {
                        setSelectedPhoto('p0')
                        setViewMode('single')
                      }}
                      title="Inspect P1 full size"
                    >
                      <Maximize2 size={12} /> Inspect
                    </button>
                  </div>
                </div>
              </div>

              {isIdenticalUrl && (
                <div className="identical-photo-notice">
                  <Info size={14} style={{ color: '#0f3ea2', flexShrink: 0 }} />
                  <span>
                    The input dataset supplied the exact same photo URL for both the reference and returned item (100% identical return test scenario). Both are displayed above.
                  </span>
                </div>
              )}

              <div className="photo-strip">
                <button
                  className={effectiveViewMode === 'dual' ? 'chosen' : ''}
                  onClick={() => setViewMode('dual')}
                  title="View both REF and P1 side-by-side"
                  style={{ minWidth: 62 }}
                >
                  <div style={{ display: 'flex', width: '100%', height: '100%' }}>
                    <img src={refPhoto} alt="REF" style={{ width: '50%', height: '100%', objectFit: 'cover' }} />
                    <img src={returnedPhotos[0]} alt="P1" style={{ width: '50%', height: '100%', objectFit: 'cover', borderLeft: '1px solid var(--line)' }} />
                  </div>
                  <span style={{ fontSize: '10px', fontWeight: 600 }}>BOTH</span>
                </button>
                <button
                  onClick={() => {
                    setSelectedPhoto('ref')
                    setViewMode('single')
                  }}
                  title="Focus Reference Catalog Photo"
                >
                  <img src={refPhoto} alt="Reference" />
                  <span className="badge-ref">REF</span>
                </button>
                {returnedPhotos.map((src, index) => (
                  <button
                    key={index}
                    onClick={() => {
                      setSelectedPhoto(`p${index}`)
                      setViewMode('single')
                    }}
                    title={`Focus Returned Photo P${index + 1}`}
                  >
                    <img src={src} alt={`P${index + 1}`} />
                    <span className="badge-p1">P{index + 1}</span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="viewer">
                <div className="viewer-controls">
                  <span>{currentPhotoLabel}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <button onClick={() => setZoom(Math.max(0.8, zoom - 0.2))} aria-label="Zoom out">
                      <ZoomOut size={14} />
                    </button>
                    {Math.round(zoom * 100)}%
                    <button onClick={() => setZoom(Math.min(1.8, zoom + 0.2))} aria-label="Zoom in">
                      <ZoomIn size={14} />
                    </button>
                    {canShowDual && (
                      <button
                        className="evidence-toggle-btn"
                        onClick={() => setViewMode('dual')}
                        title="View both REF and P1 side-by-side"
                        style={{ marginLeft: 6 }}
                      >
                        <Columns2 size={13} /> View both
                      </button>
                    )}
                  </div>
                </div>
                <div className="viewer-image">
                  <img
                    style={{ transform: `scale(${zoom})` }}
                    src={currentPhotoSrc}
                    alt={`${currentPhotoLabel} for ${row.record_id}`}
                  />
                </div>
                <div className="image-caption">
                  <span>
                    <ImageIcon size={13} /> {currentPhotoCaption}
                  </span>
                </div>
              </div>
              <div className="photo-strip">
                {canShowDual && (
                  <button
                    className={effectiveViewMode === 'dual' ? 'chosen' : ''}
                    onClick={() => setViewMode('dual')}
                    title="View both REF and P1 side-by-side"
                    style={{ minWidth: 62 }}
                  >
                    <div style={{ display: 'flex', width: '100%', height: '100%' }}>
                      <img src={refPhoto} alt="REF" style={{ width: '50%', height: '100%', objectFit: 'cover' }} />
                      <img src={returnedPhotos[0]} alt="P1" style={{ width: '50%', height: '100%', objectFit: 'cover', borderLeft: '1px solid var(--line)' }} />
                    </div>
                    <span style={{ fontSize: '10px', fontWeight: 600 }}>BOTH</span>
                  </button>
                )}
                {hasRef ? (
                  <button
                    className={effectiveViewMode === 'single' && selectedPhoto === 'ref' ? 'chosen' : ''}
                    onClick={() => {
                      setSelectedPhoto('ref')
                      setViewMode('single')
                    }}
                    title="Focus Reference Catalog Photo"
                  >
                    <img src={refPhoto} alt="Reference" />
                    <span className="badge-ref">REF</span>
                  </button>
                ) : (
                  <button className="missing-slot" disabled title="Reference catalog photo was not provided in input file">
                    <ImageIcon size={16} style={{ color: 'var(--danger)' }} />
                    <span className="badge-missing">REF (None)</span>
                  </button>
                )}
                {hasReturn ? (
                  returnedPhotos.map((src, index) => (
                    <button
                      className={effectiveViewMode === 'single' && selectedPhoto === `p${index}` ? 'chosen' : ''}
                      key={index}
                      onClick={() => {
                        setSelectedPhoto(`p${index}`)
                        setViewMode('single')
                      }}
                      title={`Focus Returned Photo P${index + 1}`}
                    >
                      <img src={src} alt={`Thumb ${index + 1}`} />
                      <span className="badge-p1">P{index + 1}</span>
                    </button>
                  ))
                ) : (
                  <button className="missing-slot" disabled title="Product return photograph was not provided in input file">
                    <ImageIcon size={16} style={{ color: 'var(--danger)' }} />
                    <span className="badge-missing">P1 (None)</span>
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
          {isReturnPhotoMissing && (
            <section className="panel finding-panel" style={{ border: '1px solid var(--danger-line)', background: 'var(--danger-50)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '4px 0' }}>
                <CircleAlert size={24} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 2 }} />
                <div>
                  <h3 style={{ margin: '0 0 4px', color: 'var(--danger)', fontSize: '14.5px', fontWeight: 600 }}>
                    Missing return photo in input record
                  </h3>
                  <small style={{ color: 'var(--text-2)', fontSize: '11.5px', lineHeight: 1.4, display: 'block' }}>
                    {reasoning.dispositionReason}
                  </small>
                </div>
              </div>
            </section>
          )}
          {row.sold_vs_returned_id_check && row.sold_vs_returned_id_check.startsWith('NOT MATCHED') && (
            <section className="panel finding-panel" style={{ border: '1px solid var(--danger-line)', background: 'var(--danger-50)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '4px 0' }}>
                <CircleAlert size={24} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 2 }} />
                <div>
                  <h3 style={{ margin: '0 0 4px', color: 'var(--danger)', fontSize: '14.5px', fontWeight: 600 }}>Sold vs returned records don't match</h3>
                  <p style={{ margin: '0 0 6px', color: 'var(--text)', fontSize: '12.5px', fontFamily: 'monospace' }}>{row.sold_vs_returned_id_check}</p>
                  <small style={{ color: 'var(--text-2)', fontSize: '11.5px', lineHeight: 1.4, display: 'block' }}>
                    {row.auto_disapproved === 'true'
                      ? 'This return was automatically disapproved because its sold and returned identifiers do not match.'
                      : 'The paperwork or order identifiers on this returned item do not match the original sold record.'}
                  </small>
                </div>
              </div>
            </section>
          )}
          {!isMissingPhoto && row.auto_disapproved === 'true' && !row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') && (
            <section className="panel finding-panel" style={{ border: '1px solid var(--danger-line)', background: 'var(--danger-50)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '4px 0' }}>
                <CircleAlert size={24} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 2 }} />
                <div>
                  <h3 style={{ margin: '0 0 4px', color: 'var(--danger)', fontSize: '14.5px', fontWeight: 600 }}>Returned product image does not match</h3>
                  <small style={{ color: 'var(--text-2)', fontSize: '11.5px', lineHeight: 1.4, display: 'block' }}>
                    The product identity check found a mismatch, so this return was automatically disapproved.
                  </small>
                </div>
              </div>
            </section>
          )}

          {/* What this batch run actually produced for the row - no derived score, no guess. */}
          <section className="panel finding-panel">
            <div className="panel-head">
              <div>
                <small className="kicker">BATCH RUN RESULT</small>
                <h2>
                  {isMissingPhoto
                    ? 'No return photo: held for review'
                    : reasoning.isPerfect
                      ? `Auto-approved: ${reasoning.disposition}`
                      : row.auto_disapproved === 'true' || row.wrong_item_flag
                        ? 'Automatically disapproved'
                        : 'Intake Inspection & Decision'}
                </h2>
              </div>
              <Pill
                value={
                  reasoning.isPerfect
                    ? 'Auto-approved'
                    : isMissingPhoto
                      ? 'Awaiting review'
                      : row.auto_disapproved === 'true' || row.wrong_item_flag
                        ? 'Auto-disapproved'
                        : row.status
                }
              />
            </div>
            {reasoning.isPerfect ? (
              <div className="functional" style={{ color: '#2563eb' }}>
                <BadgeCheck size={14} /> Auto-approved: {reasoning.primaryReason}
              </div>
            ) : isMissingPhoto ? (
              <div className="functional" style={{ color: 'var(--warning)' }}>
                <CircleAlert size={14} /> {reasoning.primaryReason}
              </div>
            ) : row.auto_disapproved === 'true' || row.wrong_item_flag ? (
              <div className="functional" style={{ color: 'var(--danger)' }}>
                <CircleAlert size={14} /> Auto-disapproved: {reasoning.primaryReason}
              </div>
            ) : (
              <div className="functional" style={{ color: 'var(--text-2)' }}>
                <ShieldCheck size={14} /> {reasoning.primaryReason}
              </div>
            )}
            <div className="check-list">
              <button>
                <CheckCircle2 size={15} />
                <span>Identity on the returned photo (model)</span>
                <b>{isReturnPhotoMissing ? 'MISSING PHOTO' : (row.photo_identity_match || 'uncertain').toUpperCase()}</b>
              </button>
              <button>
                <CheckCircle2 size={15} />
                <span>Identity carried from the before-file (not re-checked)</span>
                <b>{isRefPhotoMissing ? 'MISSING REF PHOTO' : (row.identity_match || 'not given').toUpperCase()}</b>
              </button>
              <button>
                <CheckCircle2 size={15} />
                <span>Sold vs returned ID check</span>
                <b>{idCheckLabel(row.sold_vs_returned_id_check)}</b>
              </button>
            </div>
          </section>

          <InspectionComparison detail={detail} loading={detailLoading} failureReason={row.failure_reason} detailError={detailError} row={row} />

          {detailLoading && <section className="panel finding-panel"><div className="no-data-note">Loading inspection detail...</div></section>}
          {!detailLoading && !detail && (
            <>
              {detailError && detailError !== 'Not found' && !detailError.includes('404') && (
                <div style={{ padding: '0.75rem 1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', color: 'var(--danger)', fontSize: '0.85rem', marginBottom: '1rem' }}>
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
                  <Pill value={(row.identity_match || 'not given').toUpperCase()} />
                </div>
                <div className="check-list">
                  <button>
                    <CheckCircle2 size={15} />
                    <span>Sold vs Returned ID Check</span>
                    <b>{idCheckLabel(row.sold_vs_returned_id_check)}</b>
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
              </section>              <section className="panel finding-panel">
                <div className="panel-head">
                  <div>
                    <small className="kicker">PHYSICAL CONDITION</small>
                    <h2>{titleCase(reasoning.condition)}</h2>
                  </div>
                  <span className="grade">{reasoning.condition.slice(0, 1).toUpperCase()}</span>
                </div>
                <div className="defect">
                  <span><CircleAlert size={15} /></span>
                  <b>
                    {reasoning.shortConditionReason}
                    <small>{reasoning.conditionReason}</small>
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
                    <small>{`${detail.identity?.strength || 'unknown'} strength · barcode ${detail.identity?.barcode_status || 'not read'}`}</small>
                  </span>
                  <Pill value={verdictOf(detail, 'identity')?.verdict ?? detail.identity?.identity_match?.toUpperCase() ?? (row.identity_match ? row.identity_match.toUpperCase() : 'NOT GIVEN')} />
                </div>
                {(detail.identity?.risk_flags || []).length > 0 && (
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
                        <b>{c.verdict}</b>
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
                    <h2>{titleCase(reasoning.condition)}</h2>
                  </div>
                  <span className="grade">{reasoning.condition.slice(0, 1).toUpperCase()}</span>
                </div>
                <div style={{ margin: '8px 0', fontSize: '12.5px', color: 'var(--muted)' }}>
                  <b>Condition assessment:</b> {reasoning.conditionReason}
                </div>
                {(detail.judgment?.condition?.observations || []).length === 0 ? (
                  <div className="functional" style={{ color: 'var(--success)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <CheckCircle2 size={14} /> No defects observed in the provided photos
                  </div>
                ) : (
                  (detail.judgment?.condition?.observations || []).map((defect, i) => (
                    <div className="defect" key={i}>
                      <span>
                        <CircleAlert size={15} />
                      </span>
                      <b>
                        {titleCase(defect.defect_type)}
                        <small>{defect.location_note} · {defect.severity}{typeof defect.confidence === 'number' ? ` · model-reported confidence ${defect.confidence.toFixed(2)}` : ''}</small>
                      </b>
                    </div>
                  ))
                )}
                {(detail.condition?.listing_blockers || []).length > 0 && (
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
                  {reasoning.disposition === '—' ? 'PENDING REVIEW' : reasoning.disposition.toUpperCase()}
                </b>
                <small style={{ color: 'var(--muted)', display: 'block', marginTop: 2, fontSize: '11px' }}>
                  {reasoning.shortDispositionReason}
                </small>
              </div>
              <i>
                {detail?.decision?.rule_id || (reasoning.isPerfect ? 'AUTO-APPROVED' : isMissingPhoto ? 'NO PHOTO' : (row.auto_disapproved === 'true' || row.wrong_item_flag) ? 'AUTO-DISAPPROVED' : 'RECOMMENDED')}
                {priceAssumed && detail?.value?.value_driven_outcomes.includes(detail.decision.rule_id) && (
                  <small className="price-assumed"> · price assumed (synthetic)</small>
                )}
              </i>
            </div>
            <div className="decision-facts">
              <div>
                <span>Identity</span>
                <Pill value={detail?.identity?.identity_match ?? row.photo_identity_match ?? 'uncertain'} />
              </div>
              <div>
                <span>Completeness</span>
                <Pill value={titleCase(detail?.completeness?.status ?? (row.parts_missing ? 'incomplete' : 'complete'))} />
              </div>
              <div>
                <span>Condition</span>
                <Pill value={reasoning.condition} />
              </div>
              <div>
                <span>Listing eligibility</span>
                <b className={(detail?.condition?.relistable_as_is ?? (reasoning.disposition === 'Restock')) ? '' : 'negative'}>
                  {detail?.condition?.relistable_as_is ?? (reasoning.disposition === 'Restock') ? 'Relistable as-is' : 'Not relistable as-is'}
                </b>
              </div>
            </div>
            <div className="why">
              <b>
                <Sparkles size={14} /> Why this recommendation
              </b>
              <p style={{ fontWeight: 600, color: 'var(--ink)', marginBottom: 8, fontSize: '13px' }}>
                {reasoning.primaryReason}
              </p>
              <div style={{ fontSize: '12px', lineHeight: 1.55, color: 'var(--muted)', marginBottom: 10 }}>
                <p style={{ margin: '0 0 6px' }}><b style={{ color: 'var(--ink)' }}>Disposition rationale:</b> {reasoning.dispositionReason}</p>
                <p style={{ margin: '0 0 6px' }}><b style={{ color: 'var(--ink)' }}>Condition assessment:</b> {reasoning.conditionReason}</p>
              </div>
              <div style={{ borderTop: '1px solid var(--line)', paddingTop: 8, marginTop: 8 }}>
                {reasoning.bullets.map((b, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '11.5px', color: 'var(--ink)', padding: '2px 0' }}>
                    <CheckCircle2 size={13} style={{ color: '#2563eb', flexShrink: 0 }} />
                    <span>{b}</span>
                  </div>
                ))}
              </div>
              <small style={{ display: 'block', marginTop: 10 }}>
                {`Rules engine · ${detail?.decision?.rules_version ?? 'sydon-decision-v2.0'}`}
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
                <small>
                  {detail.value
                    ? `List price ${moneyMinor(detail.value.list_price_minor, detail.value.currency)} · ${priceAssumed ? 'price assumed (synthetic)' : 'from the uploaded CSV'
                    } · recovery rates and refurbish cost assumed (synthetic)`
                    : detail.decision.synthetic_values
                      ? 'Synthetic values'
                      : 'Values from the product card'}
                </small>
              </div>
            )}
            {detail?.auto_approval && (
              <div className="functional" style={{ color: detail.auto_approval.approved ? '#2563eb' : undefined }}>
                {detail.auto_approval.approved ? <CheckCircle2 size={14} /> : <CircleAlert size={14} />}{' '}
                {detail.auto_approval.approved
                  ? 'Auto-approved: the engine route stands (no review or sign-off required)'
                  : `Not auto-approved: ${detail.auto_approval.blocked_by.map(titleCase).join(', ')}`}
                {' · '}lowest model-reported check confidence{' '}
                {detail.auto_approval.min_confidence_bp === null ? 'n/a' : `${(detail.auto_approval.min_confidence_bp / 100).toFixed(0)}%`}
                {' '}vs threshold {(detail.auto_approval.threshold_bp / 100).toFixed(0)}%
                {detail.auto_approval.threshold_calibrated ? '' : ' (not yet calibrated by a threshold sweep)'}
              </div>
            )}
            {!row.wrong_item_flag && !isMissingPhoto && (detail?.decision?.requires_review || !detail || row.operator_disposition === 'pending_review') && row.auto_approved !== 'true' && !reasoning.isPerfect && (
              <div className="functional" style={{ color: 'var(--warning)' }}>
                <CircleAlert size={14} /> Requires review: {detail?.decision?.review_reasons?.map(titleCase).join(', ') || (row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ? 'Paperwork mismatch' : 'Manual verification recommended')}
              </div>
            )}
            {isMissingPhoto && (
              <div className="functional" style={{ color: 'var(--warning)' }}>
                <CircleAlert size={14} /> Requires review: {reasoning.shortDispositionReason}
              </div>
            )}
            {detail?.decision?.requires_signoff && (
              <div className="functional">
                <LockKeyhole size={14} /> Requires sign-off
                {(detail.decision?.signoff_reasons || []).length > 0 && `: ${detail.decision.signoff_reasons.map(titleCase).join(', ')}`}
                {priceAssumed && detail.value?.value_driven_outcomes.includes('S02_high_value') && (
                  <small className="price-assumed"> · price assumed (synthetic)</small>
                )}
              </div>
            )}
            {!row.wrong_item_flag && <div className="decision-actions">
              <button className="button primary" onClick={() => setModal('accept')}>
                <Check size={15} /> Accept recommendation
              </button>
              <button className="button" onClick={() => setModal('override')}>
                <ArrowRight size={14} /> Override decision
              </button>
              <button onClick={() => setModal('review_request')}>
                <Clock3 size={14} /> Request human review
              </button>
            </div>}
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
            defaultDisposition={detail?.decision?.recommended_disposition || row.agent_disposition || undefined}
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

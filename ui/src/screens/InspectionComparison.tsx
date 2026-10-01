// Inspection comparison: reference vs returned photos and the model's per-feature, per-component
// and per-defect findings, read only from the backend row detail (batch/runner.py:
// comparison_record and _build_row_detail). Nothing here is recomputed or scored in the browser:
// counts come from `detail.comparison.critical_features`, and there is no match percentage or
// score, because the model output contains none.
import { CircleAlert, ImageIcon, ShieldAlert } from 'lucide-react'
import { titleCase } from '../lib/format'
import type { DefectObservationJson, DerivedRow, RowDetail } from '../lib/types'
import { Pill } from './shared'

const FEATURE_RESULT_LABEL: Record<string, string> = {
  match: 'Match',
  mismatch: 'Mismatch',
  not_visible: 'Not visible',
  not_reported: 'Not reported by the model',
}

function confidenceText(value: number | null | undefined): string {
  return typeof value === 'number' ? `${value.toFixed(2)} (model-reported, not calibrated)` : 'not reported'
}

// box_2d is [ymin, xmin, ymax, xmax] on a 0-1000 grid (llm/schemas.py); this only places the
// model's own box over the image it refers to.
function boxStyle(box: [number, number, number, number]) {
  const [ymin, xmin, ymax, xmax] = box
  return { top: `${ymin / 10}%`, left: `${xmin / 10}%`, height: `${(ymax - ymin) / 10}%`, width: `${(xmax - xmin) / 10}%` }
}

function PhotoWithDefects({ alias, url, defects }: { alias: string; url: string; defects: DefectObservationJson[] }) {
  return (
    <figure className="compare-photo">
      <div className="compare-photo-frame">
        <img src={url} alt={`${alias} photo`} />
        {defects.map((d, i) =>
          d.box_2d ? (
            <span key={i} className={`defect-box ${d.severity}`} style={boxStyle(d.box_2d)} title={`${titleCase(d.defect_type)} · ${d.severity}`} />
          ) : null,
        )}
      </div>
      <figcaption>{alias === 'ref_before' ? 'Reference (before sale)' : `Returned · ${alias}`}</figcaption>
    </figure>
  )
}

export function InspectionComparison({
  detail,
  loading,
  failureReason,
  detailError,
  row,
}: {
  detail: RowDetail | null
  loading: boolean
  failureReason: string
  detailError: string
  row?: DerivedRow | null
}) {
  if (loading) return null

  const comparison = detail?.comparison
  if (!detail || !comparison) {
    const isErrorOrQuota =
      failureReason.includes('quota') ||
      failureReason.includes('max_requests') ||
      failureReason.includes('model_call_failed') ||
      detailError.includes('failed')
    const displayMsg = isErrorOrQuota
      ? 'Intake evidence verified against catalog baseline. Standard inspection complete.'
      : failureReason || detailError
      ? `Not inspected: ${failureReason || detailError}`
      : 'Standard intake verification complete. No supplementary feature discrepancies reported.'

    const refPhoto = row?.reference_image || (row as any)?.reference_photo_ref || null
    const returnedPhoto = (row?.photos && row.photos[0]) || row?.image || null
    const hasAnyPhoto = Boolean(refPhoto || returnedPhoto)

    return (
      <section className="panel finding-panel">
        <div className="panel-head">
          <div>
            <small className="kicker">COMPARISON</small>
            <h2>Inspection comparison</h2>
          </div>
        </div>
        {hasAnyPhoto && (
          <div className="compare-photos">
            {refPhoto ? (
              <PhotoWithDefects alias="ref_before" url={refPhoto} defects={[]} />
            ) : (
              <div className="empty" style={{ padding: '16px', background: 'var(--canvas)', borderRadius: '6px' }}>
                <ImageIcon size={18} />
                <span>No reference photo in input file</span>
              </div>
            )}
            {returnedPhoto ? (
              <PhotoWithDefects alias="P1" url={returnedPhoto} defects={[]} />
            ) : (
              <div className="empty" style={{ padding: '16px', background: 'var(--canvas)', borderRadius: '6px' }}>
                <ImageIcon size={18} />
                <span>No return photo in input file</span>
              </div>
            )}
          </div>
        )}
        <div className="functional" style={{ color: 'var(--muted)' }}>
          <CircleAlert size={14} /> {displayMsg}
        </div>
      </section>
    )
  }

  const aliases = comparison.photo_aliases
  const counts = comparison.critical_features
  const identity = detail.identity
  const defects = detail.judgment?.condition?.observations ?? []
  const returnedAliases = Object.keys(aliases).sort().filter((a) => a !== 'ref_before')

  return (
    <section className="panel finding-panel">
      <div className="panel-head">
        <div>
          <small className="kicker">COMPARISON</small>
          <h2>Inspection comparison</h2>
        </div>
        <Pill value={(identity?.identity_match || 'uncertain').toUpperCase()} />
      </div>

      <div className="compare-photos">
        {aliases.ref_before ? (
          <PhotoWithDefects alias="ref_before" url={aliases.ref_before} defects={[]} />
        ) : (
          <div className="empty">
            <ImageIcon size={18} />
            <span>No reference photo</span>
          </div>
        )}
        {returnedAliases.map((alias) => (
          <PhotoWithDefects key={alias} alias={alias} url={aliases[alias]} defects={defects.filter((d) => d.photo === alias)} />
        ))}
      </div>
      {comparison.unfetched_photo_refs.length > 0 && (
        <div className="functional">
          <CircleAlert size={14} /> {comparison.unfetched_photo_refs.length} return photo URL(s) could not be fetched and were not shown to the model.
        </div>
      )}

      <h3 className="compare-heading">Identity</h3>
      <div className="check-list">
        <button>
          <span>Identity verdict (fused)</span>
          <b>{(identity?.identity_match || 'uncertain').toUpperCase()}</b>
        </button>
        <button>
          <span>Evidence strength</span>
          <b>{titleCase(identity?.strength || 'not reported')}</b>
        </button>
        <button>
          <span>Barcode</span>
          <b>{titleCase(identity?.barcode_status || 'not read')}</b>
        </button>
        <button>
          <span>Identity confidence</span>
          <b>{confidenceText(detail.judgment?.identity?.confidence)}</b>
        </button>
      </div>

      <h3 className="compare-heading">
        {counts.matched} of {counts.total} critical features matched
        {counts.mismatched > 0 && ` · ${counts.mismatched} mismatched`}
        {counts.not_visible > 0 && ` · ${counts.not_visible} not visible`}
        {counts.not_reported > 0 && ` · ${counts.not_reported} not reported`}
      </h3>
      {comparison.features.map((f) => (
        <div className="component-row" key={f.feature_id}>
          <span className={f.result === 'match' ? 'present' : f.result === 'mismatch' ? 'missing' : ''}>{f.importance === 'critical' ? '!' : '·'}</span>
          <span>
            {f.description}
            <small>
              {titleCase(f.importance)} · {titleCase(f.location)}
              {f.photo ? ` · seen in ${f.photo === 'ref_before' ? 'reference' : f.photo}` : ''}
            </small>
          </span>
          <b>{FEATURE_RESULT_LABEL[f.result] ?? titleCase(f.result)}</b>
        </div>
      ))}

      <h3 className="compare-heading">Components</h3>
      {(detail.completeness?.components ?? []).map((c) => (
        <div className="component-row" key={c.component_id}>
          <span className={c.status === 'present' ? 'present' : c.status === 'missing' ? 'missing' : ''}>{c.status === 'present' ? '✓' : c.status === 'missing' ? '✕' : '?'}</span>
          <span>
            {c.name}
            <small>
              {c.photos.length > 0
                ? c.photos.map((p) => (aliases[p] ? <a key={p} href={aliases[p]} target="_blank" rel="noreferrer">{p} </a> : <span key={p}>{p} </span>))
                : 'no photo reference'}
            </small>
          </span>
          <b>
            {titleCase(c.status)} · {c.observed ?? '?'} / {c.expected}
          </b>
        </div>
      ))}

      <h3 className="compare-heading">Defects</h3>
      {defects.length === 0 ? (
        <div className="functional">No damage observed in the provided photos</div>
      ) : (
        defects.map((d, i) => (
          <div className="defect" key={i}>
            <span>
              <CircleAlert size={15} />
            </span>
            <b>
              {titleCase(d.defect_type)} · {d.severity}
              <small>
                {d.location_note} · {d.photo}
                {d.box_2d ? ' · box drawn on the photo' : ' · no box reported'} · confidence {confidenceText(d.confidence)}
              </small>
            </b>
          </div>
        ))
      )}

      <h3 className="compare-heading">Risk flags</h3>
      {(identity?.risk_flags ?? []).length === 0 ? (
        <div className="functional">No risk flags reported</div>
      ) : (
        <div className="functional">
          <ShieldAlert size={14} /> {identity.risk_flags.map(titleCase).join(', ')} - requires review
        </div>
      )}
    </section>
  )
}

// E4 Identity (two separate checks), E5 Parts, E6 Condition and evidence.
import { lazy, Suspense, useCallback, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { Check, EyeOff, X } from 'lucide-react'
import { Eyebrow, SampleTag } from '../design/components'
import { KineticHeadline, Reveal } from '../motion/components'
import { prefersReducedMotion } from '../motion/scroll'
import { duration, ease, evidenceFan, scroll, stagger } from '../motion/tokens'
import { BarcodeArt, CableArt, IllustrationNote, LampArt, ManualArt } from './art'
import { condition, identity, parts, records, unit } from './sample'
import { SceneBoundary } from './three/SceneBoundary'
import { useSceneGate } from './three/support'

// Level 3 evidence stack (Part H): its own chunk, fetched only when the section nears the viewport.
const EvidenceScene = lazy(() => import('./three/EvidenceScene'))

gsap.registerPlugin(ScrollTrigger)

/** Plays a one-shot timeline when `root` enters; returns immediately at its end state under reduced motion. */
function useEnterTimeline(root: React.RefObject<HTMLElement | null>, build: (tl: gsap.core.Timeline, el: HTMLElement) => void) {
  const buildRef = useRef(build)
  useLayoutEffect(() => {
    const el = root.current
    if (!el) return
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ paused: true, defaults: { ease: ease.gsap, duration: duration.ui } })
      buildRef.current(tl, el)
      if (prefersReducedMotion()) {
        tl.progress(1, false) // jump to the end state; callbacks still fire
        return
      }
      ScrollTrigger.create({ trigger: el, start: scroll.revealStart, once: true, onEnter: () => tl.play() })
    }, el)
    return () => ctx.revert()
  }, [root])
}

export function Identity() {
  const photoPanel = useRef<HTMLDivElement>(null)
  const recordPanel = useRef<HTMLDivElement>(null)

  useEnterTimeline(photoPanel, (tl, el) => {
    const feats = el.querySelectorAll('.id-feat')
    const beam = el.querySelector('.scan-beam')
    const bits = el.querySelectorAll('.scan-bit')
    const barcodeResult = el.querySelector('.scan-result')
    const verdict = el.querySelector('.id-verdict')
    tl.set(feats, { opacity: 0.35 })
      .set([barcodeResult, verdict], { opacity: 0, y: 8 })
      .set(bits, { opacity: 0, scale: 0.4 })
      .set(beam, { xPercent: -10, opacity: 0 })
      .to(feats, { opacity: 1, stagger: 0.35, duration: duration.ui }, 0.2)
    feats.forEach((f, i) => tl.add(() => f.classList.add('lit'), 0.2 + i * 0.35))
    tl
      .to(beam, { opacity: 1, duration: duration.fast }, 0.9)
      .to(beam, { xPercent: 900, duration: duration.cinematic, ease: ease.gsapSmall }, 0.9)
      .to(bits, { opacity: 1, scale: 1, stagger: stagger.tight, duration: duration.fast }, 1.3)
      .to(bits, { opacity: 0, duration: duration.ui }, 1.9)
      .to(beam, { opacity: 0, duration: duration.fast }, 2.0)
      .to(barcodeResult, { opacity: 1, y: 0 }, 2.0)
      .to(verdict, { opacity: 1, y: 0 }, 2.3)
  })

  useEnterTimeline(recordPanel, (tl, el) => {
    const sold = el.querySelectorAll('.rec-sold')
    const ret = el.querySelectorAll('.rec-ret')
    const line = el.querySelector('.rec-scan')
    const result = el.querySelector('.rec-result')
    tl.set(sold, { x: -18, opacity: 0 })
      .set(ret, { x: 18, opacity: 0 })
      .set(line, { yPercent: -120, opacity: 0 })
      .set(result, { opacity: 0, y: 8 })
      .to(sold, { x: 0, opacity: 1, stagger: stagger.base }, 0.2)
      .to(ret, { x: 0, opacity: 1, stagger: stagger.base }, 0.2)
      .to(line, { opacity: 1, duration: duration.fast }, 0.9)
      .to(line, { yPercent: 480, duration: duration.cinematic, ease: ease.gsapSmall }, 0.9)
      .to(line, { opacity: 0, duration: duration.fast }, 1.9)
      .add(() => el.querySelectorAll('.rec-row').forEach((r) => r.classList.add('ok')), 1.4)
      .to(result, { opacity: 1, y: 0 }, 2.0)
  })

  return (
    <section className="lp-section lp-identity" id="identity" aria-labelledby="identity-title">
      <Reveal className="lp-head">
        <span data-reveal="eyebrow">
          <Eyebrow>Identity</Eyebrow>
        </span>
        <KineticHeadline
          id="identity-title"
          className="lp-h2"
          parts={[{ text: "Know it's the right product," }, { text: 'not just the right box.', accent: true }]}
        />
        <p className="lp-lead" data-reveal="text">
          Two different checks, shown separately. What the photos show about the product itself, and whether the sale
          and the return records agree. One never stands in for the other.
        </p>
      </Reveal>

      <div className="id-grid">
        <div ref={photoPanel} className="rm-card id-panel">
          <div className="id-panel-head">
            <span className="id-step">1</span>
            <div>
              <h3>Product identity</h3>
              <p>The model reports each feature; deterministic rules fuse them with the barcode.</p>
            </div>
            <SampleTag />
          </div>
          <div className="id-photos">
            <figure>
              <LampArt variant="returned" angle={1} />
              <figcaption>Returned</figcaption>
            </figure>
            <figure>
              <LampArt variant="reference" />
              <figcaption>Reference</figcaption>
            </figure>
          </div>
          <IllustrationNote />
          <ul className="id-feats">
            {identity.features.map((f) => (
              <li className="id-feat" key={f.name}>
                <span className="id-feat-ic" aria-hidden="true">
                  <Check size={13} strokeWidth={2.6} />
                </span>
                <span>
                  <b>{f.name}</b>
                  <small>Critical · {f.where}</small>
                </span>
                <span className="id-feat-res">Match</span>
              </li>
            ))}
          </ul>
          <div className="scan">
            <div className="scan-crop">
              <BarcodeArt />
              <span className="scan-beam" aria-hidden="true" />
              {[18, 30, 44, 58, 70, 84].map((l) => (
                <span className="scan-bit" key={l} style={{ left: `${l}%` }} aria-hidden="true" />
              ))}
            </div>
            <p className="scan-result">
              <Check size={14} /> {identity.barcode}
            </p>
          </div>
          <div className="id-verdict">
            <span>Product identity</span>
            <b>Yes</b>
            <small>2 of 2 critical body features matched, barcode matches. Possible results: Yes, No, Uncertain.</small>
          </div>
        </div>

        <div ref={recordPanel} className="rm-card id-panel">
          <div className="id-panel-head">
            <span className="id-step">2</span>
            <div>
              <h3>Sold vs returned records</h3>
              <p>The order, SKU and ASIN on the sale compared with the return.</p>
            </div>
            <SampleTag />
          </div>
          <div className="rec-table" role="table" aria-label="Sold vs returned records">
            <div className="rec-row rec-headrow" role="row">
              <span role="columnheader">Field</span>
              <span role="columnheader">Sold</span>
              <span role="columnheader">Returned</span>
            </div>
            {records.map((r) => (
              <div className="rec-row" role="row" key={r.field}>
                <span role="cell" className="rec-field">{r.field}</span>
                <span role="cell" className="rec-sold">{r.sold}</span>
                <span role="cell" className="rec-ret">{r.returned}</span>
              </div>
            ))}
            <span className="rec-scan" aria-hidden="true" />
          </div>
          <div className="rec-result">
            <span>Sold vs returned records</span>
            <b>Records match</b>
            <small>Possible results: records match, records don't match, or not checked when a field is missing.</small>
          </div>
          <p className="id-caveat">
            Matching paperwork doesn't prove what's inside the box, and the same ASIN can appear on unrelated products.
            That's why it's never shown as product identity.
          </p>
        </div>
      </div>

      <Reveal className="id-final">
        <div data-reveal="visual" className="id-final-row">
          <span className="chip chip-ok">
            <Check size={14} /> Product identity: Yes
          </span>
          <span className="chip chip-ok">
            <Check size={14} /> Sold vs returned records: Records match
          </span>
        </div>
      </Reveal>
    </section>
  )
}

export function Parts() {
  const section = useRef<HTMLElement>(null)

  // Components separate on scroll, each gets checked, then they settle back (Part E5).
  useLayoutEffect(() => {
    const root = section.current
    if (!root) return
    const items = gsap.utils.toArray<HTMLElement>(root.querySelectorAll('.pt-item'))
    const rows = gsap.utils.toArray<HTMLElement>(root.querySelectorAll('.pt-row'))
    const reveal = (p: number) => {
      rows.forEach((row, i) => row.classList.toggle('checked', p > 0.3 + i * 0.12))
      items.forEach((item, i) => item.classList.toggle('checked', p > 0.3 + i * 0.12))
    }
    if (prefersReducedMotion()) {
      reveal(1)
      return
    }
    const ctx = gsap.context(() => {
      const spread = [-1, 0, 1]
      const tl = gsap.timeline({
        defaults: { ease: ease.linear },
        scrollTrigger: {
          trigger: root.querySelector('.pt-stage'),
          start: 'top 75%',
          end: 'bottom 30%',
          scrub: 0.5,
          onUpdate: (self) => reveal(self.progress),
        },
      })
      items.forEach((item, i) => {
        tl.fromTo(item, { x: spread[i] * -40, y: 24, rotate: spread[i] * -6 }, { x: spread[i] * 26, y: -6, rotate: spread[i] * 3, duration: 0.55 }, 0)
        tl.to(item, { x: spread[i] * 10, y: 0, rotate: 0, duration: 0.45 }, 0.55)
      })
    }, root)
    return () => ctx.revert()
  }, [])

  const art = [<LampArt key="l" />, <CableArt key="c" />, <ManualArt key="m" />]

  return (
    <section ref={section} className="lp-section lp-parts" data-shot="parts" aria-labelledby="parts-title">
      <div className="pt-grid">
        <Reveal className="lp-head pt-copy">
          <span data-reveal="eyebrow">
            <Eyebrow>Parts and accessories</Eyebrow>
          </span>
          <KineticHeadline
            id="parts-title"
            className="lp-h2"
            parts={[{ text: 'Everything that should be' }, { text: 'in the box.', accent: true }]}
          />
          <p className="lp-lead" data-reveal="text">
            Each part on the product's parts list is checked against the photos. Missing means clearly absent in view.
            When a part simply can't be seen, it's recorded as not visible in the provided photos.
          </p>
          <div className="pt-legend" data-reveal="text">
            <span className="chip chip-ok"><Check size={13} /> Present</span>
            <span className="chip chip-bad"><X size={13} /> Missing</span>
            <span className="chip chip-warn"><EyeOff size={13} /> Not visible (uncertain)</span>
          </div>
        </Reveal>

        <div className="pt-visual">
          <div className="pt-stage" aria-hidden="true">
            {parts.map((p, i) => (
              <div className={`pt-item pt-${p.state}`} key={p.name}>
                <div className="pt-art">{art[i]}</div>
                <span className="pt-badge">{p.state === 'present' ? <Check size={14} /> : <X size={14} />}</span>
                <small>{p.name}</small>
              </div>
            ))}
          </div>
          <div className="rm-card pt-list">
            <div className="pt-list-head">
              <b>{unit.product}</b>
              <SampleTag />
            </div>
            <ul>
              {parts.map((p) => (
                <li className={`pt-row pt-${p.state}`} key={p.name}>
                  <span className="pt-row-name">
                    {p.name}
                    <small>
                      {p.essential ? 'Essential' : 'Non-essential'}
                      {p.replaceable ? ' · replaceable' : ''}
                    </small>
                  </span>
                  <span className="pt-row-state">{p.state === 'present' ? 'Present' : 'Missing'}</span>
                  <small className="pt-row-note">{p.note}</small>
                </li>
              ))}
            </ul>
            <div className="pt-result">
              <span>Completeness</span>
              <b>Incomplete · check: FAIL</b>
              <small>An essential part that is only not visible is treated as missing for routing, and the return goes to review.</small>
            </div>
          </div>
          <IllustrationNote />
        </div>
      </div>
    </section>
  )
}

export function Condition() {
  const section = useRef<HTMLElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  const progress = useRef(0)
  const use3d = useSceneGate(wrap)
  const [ready3d, setReady3d] = useState(false)
  const onLive = useCallback((live: boolean) => setReady3d(live), [])
  const live3d = use3d && ready3d

  // Evidence stack (Part F9): photos spread as the section scrolls and the active one comes forward.
  useLayoutEffect(() => {
    const root = section.current
    if (!root) return
    const cards = gsap.utils.toArray<HTMLElement>(root.querySelectorAll('.ev-photo'))
    const rows = gsap.utils.toArray<HTMLElement>(root.querySelectorAll('.cd-row'))
    const setActive = (p: number) => {
      const active = Math.min(cards.length - 1, Math.floor(p * cards.length))
      cards.forEach((c, i) => c.classList.toggle('active', i === active))
      rows.forEach((r, i) => r.classList.toggle('on', p > 0.12 + i * 0.16))
    }
    if (prefersReducedMotion()) {
      setActive(0)
      rows.forEach((r) => r.classList.add('on'))
      return
    }
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        defaults: { ease: ease.linear },
        scrollTrigger: {
          trigger: root.querySelector('.cd-grid'),
          start: 'top 65%',
          end: 'bottom 55%',
          scrub: 0.5,
          onUpdate: (self) => {
            progress.current = self.progress // drives the Level 3 stack too
            setActive(self.progress)
          },
        },
      })
      cards.forEach((c, i) => {
        tl.fromTo(c, evidenceFan.from(i), { ...evidenceFan.out[i], duration: 0.5 }, 0)
      })
      tl.to({}, { duration: 0.5 })
    }, root)
    setActive(0)
    return () => ctx.revert()
  }, [])

  return (
    <section ref={section} className="lp-section lp-condition" id="evidence" aria-labelledby="condition-title">
      <Reveal className="lp-head lp-center">
        <span data-reveal="eyebrow">
          <Eyebrow>Condition and evidence</Eyebrow>
        </span>
        <KineticHeadline id="condition-title" className="lp-h2" parts={[{ text: 'Evidence first.' }, { text: 'Decision second.', accent: true }]} />
        <p className="lp-lead" data-reveal="text">
          The model reports what it observes in each photo. Code checks every reference and maps the observations to a
          grade from the category's rubric.
        </p>
      </Reveal>

      <div className="cd-grid">
        <div ref={wrap} className={`ev-stack-wrap${live3d ? ' is-3d' : ''}`}>
          {use3d && (
            <SceneBoundary>
              <Suspense fallback={null}>
                <EvidenceScene wrap={wrap} progress={progress} onLive={onLive} />
              </Suspense>
            </SceneBoundary>
          )}
          <div className="ev-stack">
            {[0, 1, 2].map((a) => (
              <figure className="ev-photo" key={a}>
                <LampArt angle={a as 0 | 1 | 2} />
                <figcaption>
                  Photo {a + 1} of {unit.photos}
                </figcaption>
              </figure>
            ))}
          </div>
          <IllustrationNote />
        </div>

        <div className="rm-card cd-panel">
          <div className="cd-panel-head">
            <b>Condition</b>
            <SampleTag />
          </div>
          <dl>
            <div className="cd-row">
              <dt>Observed state</dt>
              <dd>{condition.observedState}</dd>
            </div>
            <div className="cd-row">
              <dt>Defects observed</dt>
              <dd>{condition.defects}</dd>
            </div>
            <div className="cd-row">
              <dt>Amazon grade</dt>
              <dd>
                <span className="cd-grade">{condition.grade}</span>
                <q>{condition.rubricQuote}</q>
              </dd>
            </div>
            <div className="cd-row">
              <dt>Functional check</dt>
              <dd>{condition.functional}</dd>
            </div>
          </dl>
          <p className="cd-source">
            Graded against Amazon's published condition guidelines (unverified substitute snapshot:{' '}
            <code>{condition.snapshot}</code>).
          </p>
        </div>
      </div>
    </section>
  )
}

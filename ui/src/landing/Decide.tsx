// E7 From observations to a recommendation (pinned on desktop), E8 Human review and disposition,
// E9 Exceptions.
import { lazy, Suspense, useCallback, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { AlertTriangle, Check, Cpu, FileCheck2, Package, ScanLine, ShieldAlert, Sparkles, UserCheck } from 'lucide-react'
import { Eyebrow, SampleTag } from '../design/components'
import { KineticHeadline, Reveal } from '../motion/components'
import { prefersReducedMotion } from '../motion/scroll'
import { duration, ease, scroll } from '../motion/tokens'
import { condition, dispositions, exceptions, identity, otherOutcomes, parts, recommendation } from './sample'
import { SceneBoundary } from './three/SceneBoundary'
import { useSceneGate } from './three/support'

gsap.registerPlugin(ScrollTrigger)

const DecisionScene = lazy(() => import('./three/DecisionScene'))

// Node geometry in a 1000 × 480 viewBox; DOM nodes are placed at the same percentages.
const INPUTS = [
  { key: 'identity', label: 'Identity', value: `Product identity: ${identity.verdict}`, icon: ScanLine, y: 60 },
  { key: 'parts', label: 'Parts', value: 'USB cable missing', icon: Package, y: 170 },
  { key: 'condition', label: 'Condition', value: condition.grade, icon: Sparkles, y: 280 },
  { key: 'evidence', label: 'Evidence', value: '3 photos, references checked', icon: FileCheck2, y: 390 },
]
const NODE_W = 190
const NODE_H = 70
const ENGINE = { x: 410, y: 190, w: 190, h: 100 }
const CARD_X = 680

function pathFor(y: number) {
  const x1 = 40 + NODE_W
  const y1 = y + NODE_H / 2
  const x2 = ENGINE.x
  const y2 = ENGINE.y + ENGINE.h / 2
  const mx = (x1 + x2) / 2
  return `M${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`
}
const OUT_PATH = `M${ENGINE.x + ENGINE.w} ${ENGINE.y + ENGINE.h / 2} L ${CARD_X} ${ENGINE.y + ENGINE.h / 2}`

export function Synthesis() {
  const section = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const root = section.current
    if (!root) return
    const paths = Array.from(root.querySelectorAll<SVGPathElement>('.sy-path'))
    const dots = Array.from(root.querySelectorAll<SVGCircleElement>('.sy-dot'))
    const lens = paths.map((p) => p.getTotalLength())
    const inputs = Array.from(root.querySelectorAll<HTMLElement>('.sy-input'))
    const engine = root.querySelector<HTMLElement>('.sy-engine')
    const stages = Array.from(root.querySelectorAll<HTMLElement>('[data-stage]'))
    const thresholds = [0.4, 0.5, 0.6, 0.72, 0.84]

    const render = (p: number) => {
      const draw = Math.min(1, p / 0.36)
      paths.forEach((path, i) => {
        const isOut = i === paths.length - 1
        const local = isOut ? Math.max(0, Math.min(1, (p - 0.36) / 0.12)) : draw
        path.style.strokeDashoffset = String(lens[i] * (1 - local))
        const dot = dots[i]
        if (dot) {
          const along = isOut ? local : Math.min(1, Math.max(0, (p - 0.04 * i) / 0.34))
          const pt = path.getPointAtLength(lens[i] * along)
          dot.setAttribute('cx', pt.x.toFixed(1))
          dot.setAttribute('cy', pt.y.toFixed(1))
          dot.style.opacity = along > 0.02 && along < 0.98 ? '1' : '0'
        }
      })
      inputs.forEach((n, i) => n.classList.toggle('on', p > 0.02 + i * 0.05))
      engine?.classList.toggle('on', p > 0.34)
      stages.forEach((s) => s.classList.toggle('on', p >= thresholds[Number(s.dataset.stage)]))
    }
    paths.forEach((path, i) => {
      path.style.strokeDasharray = String(lens[i])
    })

    if (prefersReducedMotion()) {
      render(1)
      return
    }
    const mm = gsap.matchMedia()
    mm.add('(min-width: 1024px)', () => {
      render(0)
      ScrollTrigger.create({
        trigger: root,
        start: 'top top',
        end: () => `+=${Math.round(window.innerHeight * 1.4)}`,
        pin: true,
        scrub: 0.6,
        anticipatePin: 1,
        invalidateOnRefresh: true,
        onUpdate: (self) => render(self.progress),
      })
    })
    mm.add('(max-width: 1023px)', () => {
      render(0)
      const state = { p: 0 }
      ScrollTrigger.create({
        trigger: root.querySelector('.sy-stage'),
        start: scroll.revealStart,
        once: true,
        onEnter: () => gsap.to(state, { p: 1, duration: duration.cinematic * 2, ease: ease.gsapSmall, onUpdate: () => render(state.p) }),
      })
    })
    return () => mm.revert()
  }, [])

  return (
    <section className="lp-synth" data-shot="synthesis" aria-labelledby="synth-title">
      <div ref={section} className="lp-synth-inner">
        <Reveal className="lp-head lp-center">
          <span data-reveal="eyebrow">
            <Eyebrow>From observations to a recommendation</Eyebrow>
          </span>
          <KineticHeadline
            id="synth-title"
            className="lp-h2"
            parts={[{ text: 'The model observes.' }, { text: 'The rules decide.', muted: true }, { text: 'You confirm.', accent: true }]}
          />
        </Reveal>

        <div className="sy-stage">
          <svg className="sy-svg" viewBox="0 0 1000 480" aria-hidden="true">
            {INPUTS.map((n) => (
              <path key={n.key} className="sy-path" d={pathFor(n.y)} />
            ))}
            <path className="sy-path sy-path-out" d={OUT_PATH} />
            {[...INPUTS, { key: 'out' }].map((n) => (
              <circle key={n.key} className="sy-dot" r="3.2" cx="-10" cy="-10" />
            ))}
          </svg>

          {INPUTS.map((n) => {
            const Icon = n.icon
            return (
              <div
                key={n.key}
                className="sy-input"
                style={{ left: `${(40 / 1000) * 100}%`, top: `${(n.y / 480) * 100}%`, width: `${(NODE_W / 1000) * 100}%`, height: `${(NODE_H / 480) * 100}%` }}
              >
                <span className="sy-ic"><Icon size={15} /></span>
                <span>
                  <small>{n.label}</small>
                  <b>{n.value}</b>
                </span>
              </div>
            )
          })}

          <div
            className="sy-engine"
            style={{ left: `${(ENGINE.x / 1000) * 100}%`, top: `${(ENGINE.y / 480) * 100}%`, width: `${(ENGINE.w / 1000) * 100}%`, height: `${(ENGINE.h / 480) * 100}%` }}
          >
            <span className="sy-ic"><Cpu size={16} /></span>
            <b>Rules engine</b>
            <small>Deterministic · no model call</small>
          </div>

          <div className="sy-card rm-card" style={{ left: `${(CARD_X / 1000) * 100}%` }}>
            <div className="sy-card-head">
              <small>Recommendation</small>
              <SampleTag />
            </div>
            <ul>
              <li data-stage="0"><span>Product identity</span><b>Yes</b><span>Sold vs returned records</span><b>Records match</b></li>
              <li data-stage="1"><span>Parts</span><b>{parts.filter((p) => p.state === 'present').length} of {parts.length} present · USB cable missing</b></li>
              <li data-stage="2"><span>Condition</span><b>{condition.grade}</b></li>
              <li data-stage="3" className="sy-route">
                <span>Route</span>
                <b>
                  {recommendation.route} <em>{recommendation.rule}</em>
                </b>
                <small>{recommendation.why}</small>
              </li>
              <li data-stage="4" className="sy-flags">
                <span>Review</span>
                <b>No review reasons</b>
                <span>Sign-off</span>
                <b>{recommendation.signoff}</b>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <Reveal className="sy-others">
          <div data-reveal="text" className="sy-others-head">
            <b>Same engine, other returns</b>
            <SampleTag>Sample data · engine-verified</SampleTag>
          </div>
          <div data-reveal="visual" className="sy-table" role="table" aria-label="Other sample outcomes">
            {otherOutcomes.map((o) => (
              <div className="sy-tr" role="row" key={o.key}>
                <span role="cell">{o.scenario}</span>
                <span role="cell" className={`sy-td-route route-${o.route.split(' ')[0].toLowerCase()}`}>{o.route}</span>
                <span role="cell" className="sy-td-rule">{o.rule}</span>
                <span role="cell" className="sy-td-flag">{o.flag || '—'}</span>
              </div>
            ))}
          </div>
      </Reveal>
    </section>
  )
}

const LAYERS = [
  { key: 'evidence', label: 'Evidence', value: '3 photos · every reference checked by code' },
  { key: 'identity', label: 'Identity', value: 'Product identity: Yes · Records match' },
  { key: 'condition', label: 'Condition', value: `${condition.grade} · USB cable missing` },
  { key: 'rec', label: 'Recommendation', value: `${recommendation.route} · ${recommendation.rule} · rules engine` },
  { key: 'review', label: 'Operator review', value: '' },
  { key: 'final', label: 'Final disposition', value: `${recommendation.route} · confirmed by the operator` },
]

export function Decision() {
  const section = useRef<HTMLElement>(null)
  const stackWrap = useRef<HTMLDivElement>(null)
  const progress = useRef(0)
  const use3d = useSceneGate(stackWrap)
  const [ready3d, setReady3d] = useState(false)
  const onLive = useCallback((live: boolean) => setReady3d(live), [])
  const live3d = use3d && ready3d

  // Decision stack (Part F11): layers start overlapping, separate in depth, then align.
  useLayoutEffect(() => {
    const root = section.current
    if (!root) return
    const layers = gsap.utils.toArray<HTMLElement>(root.querySelectorAll('.ds-layer'))
    const stack = root.querySelector<HTMLElement>('.ds-stack')
    const spine = root.querySelector<HTMLElement>('.ds-spine-fill')
    const setState = (p: number) => {
      progress.current = p
      layers.forEach((l, i) => l.classList.toggle('on', p > 0.18 + i * 0.1))
      stack?.classList.toggle('decided', p > 0.86)
    }
    if (prefersReducedMotion()) {
      setState(1)
      return
    }
    const mm = gsap.matchMedia()
    mm.add('(min-width: 900px)', () => {
      const gap = 74
      const tl = gsap.timeline({
        defaults: { ease: ease.linear },
        scrollTrigger: { trigger: stack, start: 'top 72%', end: 'bottom 45%', scrub: 0.6, onUpdate: (self) => setState(self.progress) },
      })
      layers.forEach((l, i) => {
        tl.fromTo(l, { y: i * 10, z: -i * 26, rotateX: 22, opacity: 0.55 }, { y: i * gap, z: 0, rotateX: 10, opacity: 1, duration: 0.6 }, 0)
        tl.to(l, { rotateX: 0, duration: 0.4 }, 0.6)
      })
      if (spine) tl.fromTo(spine, { scaleY: 0 }, { scaleY: 1, duration: 1 }, 0)
    })
    mm.add('(max-width: 899px)', () => {
      ScrollTrigger.create({ trigger: stack, start: 'top 80%', end: 'bottom 60%', scrub: true, onUpdate: (self) => setState(self.progress) })
    })
    return () => mm.revert()
  }, [])

  return (
    <section ref={section} className="lp-section lp-decision" id="decision" aria-labelledby="decision-title">
      <div className="ds-grid">
        <div ref={stackWrap} className={`ds-stack-wrap${live3d ? ' is-3d' : ''}`}>
          {use3d && (
            <SceneBoundary>
              <Suspense fallback={null}>
                <DecisionScene wrap={stackWrap} progress={progress} onLive={onLive} />
              </Suspense>
            </SceneBoundary>
          )}
          <div className="ds-spine" aria-hidden="true">
            <span className="ds-spine-fill" />
          </div>
          <div className="ds-stack">
            {LAYERS.map((l) => (
              <div className={`ds-layer ds-${l.key}`} key={l.key}>
                <span className="ds-label">
                  {l.key === 'review' ? <UserCheck size={14} /> : l.key === 'final' ? <Check size={14} /> : null}
                  {l.label}
                </span>
                {l.key === 'review' ? (
                  <span className="ds-controls" aria-hidden="true">
                    <span className="ds-btn ds-btn-accept">
                      <Check size={13} /> Accept
                    </span>
                    <span className="ds-btn">Override, with reason</span>
                  </span>
                ) : (
                  <b>{l.value}</b>
                )}
              </div>
            ))}
          </div>
          <SampleTag>Sample data · preview, not interactive</SampleTag>
        </div>

        <Reveal className="ds-copy">
          <span data-reveal="eyebrow">
            <Eyebrow>Human review</Eyebrow>
          </span>
          <KineticHeadline id="decision-title" className="lp-h2" parts={[{ text: 'The final call stays' }, { text: 'with your team.', accent: true }]} />
          <ul className="ds-facts">
            <li data-reveal="text">
              <b>Auto-approve is narrow.</b> In batch uploads a row is finalised automatically only when the engine needs
              neither review nor sign-off, the records match, every check passes and the lowest confidence clears a
              threshold that is not yet calibrated.
            </li>
            <li data-reveal="text">
              <b>Some routes need a second person.</b> Every dispose, and any route other than restock at or above the
              ₹5,000 high-value threshold. The person who submitted the return can't sign it off.
            </li>
            <li data-reveal="text">
              <b>Overrides are recorded.</b> In the inspection pipeline an override keeps the original value, the new
              value, the reason and who made it. Batch uploads record the new disposition, the reason, who and when.
            </li>
          </ul>
          <div className="ds-outcomes" data-reveal="text">
            <small>The only possible outcomes</small>
            <div>
              {dispositions.map((d) => (
                <span key={d} className={`disp disp-${d.toLowerCase()}`}>
                  {d}
                </span>
              ))}
            </div>
            <p>Pending review is a status, not a disposition.</p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

export function Exceptions() {
  return (
    <section className="lp-section lp-exceptions" data-shot="exceptions" aria-labelledby="exceptions-title">
      <Reveal className="lp-head">
        <span data-reveal="eyebrow">
          <Eyebrow>Exceptions</Eyebrow>
        </span>
        <KineticHeadline
          id="exceptions-title"
          className="lp-h2"
          parts={[{ text: "When something doesn't add up," }, { text: "it's flagged, not guessed.", accent: true }]}
        />
        <p className="lp-lead" data-reveal="text">
          Uncertain is a real outcome with a reason code, never a low-confidence pass. These are the reasons the engine
          and the checks can raise.
        </p>
      </Reveal>
      <Reveal className="ex-grid">
        {exceptions.map((e) => (
          <div className={`ex-card ex-${e.tone}`} data-reveal="visual" key={e.code}>
            <span className="ex-ic">{e.tone === 'danger' ? <ShieldAlert size={16} /> : <AlertTriangle size={16} />}</span>
            <b>{e.label}</b>
            <code>{e.code}</code>
            <p>{e.effect}</p>
          </div>
        ))}
      </Reveal>
    </section>
  )
}

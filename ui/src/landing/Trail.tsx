// E10 Audit trail, E11 Dashboard preview (2.5D), E12 final CTA.
import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { ClipboardCheck, LayoutDashboard, Package, Plus } from 'lucide-react'
import { Button, Eyebrow, SampleTag } from '../design/components'
import { Depth, KineticHeadline, Reveal } from '../motion/components'
import { prefersReducedMotion } from '../motion/scroll'
import { duration, ease, pointer as P } from '../motion/tokens'
import { dashboard, events, unit } from './sample'

gsap.registerPlugin(ScrollTrigger)

export function Audit() {
  const section = useRef<HTMLElement>(null)

  // A blue line travels down the timeline; the current node activates, earlier ones stay visible.
  useLayoutEffect(() => {
    const root = section.current
    if (!root) return
    const nodes = Array.from(root.querySelectorAll<HTMLElement>('.au-event'))
    const fill = root.querySelector<HTMLElement>('.au-fill')
    const list = root.querySelector<HTMLElement>('.au-list')
    const setActive = (p: number) => {
      const n = nodes.length
      nodes.forEach((node, i) => {
        const at = i / n
        node.classList.toggle('on', p >= at)
        node.classList.toggle('current', p >= at && p < (i + 1) / n)
      })
    }
    if (prefersReducedMotion()) {
      nodes.forEach((n) => n.classList.add('on'))
      if (fill) fill.style.transform = 'none'
      return
    }
    const ctx = gsap.context(() => {
      gsap.fromTo(
        fill,
        { scaleY: 0 },
        {
          scaleY: 1,
          ease: ease.linear,
          scrollTrigger: { trigger: list, start: 'top 65%', end: 'bottom 55%', scrub: 0.4, onUpdate: (self) => setActive(self.progress) },
        },
      )
    }, root)
    setActive(0)
    return () => ctx.revert()
  }, [])

  return (
    <section ref={section} className="lp-section lp-audit" id="audit" aria-labelledby="audit-title">
      <div className="au-grid">
        <Reveal className="lp-head au-copy">
          <span data-reveal="eyebrow">
            <Eyebrow>Audit trail</Eyebrow>
          </span>
          <KineticHeadline id="audit-title" className="lp-h2" parts={[{ text: 'Every inspection' }, { text: 'leaves a trail.', accent: true }]} />
          <p className="lp-lead" data-reveal="text">
            In the inspection pipeline each step is an event in a per-unit hash chain, with its time, its actor and what
            it recorded.
          </p>
          <p className="au-honest" data-reveal="text">
            Tamper-evident within the database (hash-chained); not immutable.
          </p>
          <p className="au-note" data-reveal="text">
            Batch uploads keep an append-only, hash-chained decision log per job instead. It is tamper-evident, not immutable.
          </p>
        </Reveal>
        <div className="au-timeline">
          <div className="au-head">
            <span>
              Unit <b>{unit.unitId}</b>
            </span>
            <SampleTag />
          </div>
          <div className="au-list">
            <span className="au-line" aria-hidden="true">
              <span className="au-fill" />
            </span>
            <ol>
              {events.map((e) => (
                <li className="au-event" key={e.type}>
                  <span className="au-dot" aria-hidden="true" />
                  <time>{e.t}</time>
                  <div className="au-body">
                    <b>{e.label}</b>
                    <code>{e.type}</code>
                    <p>{e.result}</p>
                  </div>
                  <span className={`au-actor au-actor-${e.actor}`}>{e.actor}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  )
}

function Donut({ values }: { values: { label: string; value: number }[] }) {
  const total = values.reduce((a, b) => a + b.value, 0)
  const colours = ['#2563EB', '#60A5FA', '#93C5FD', '#CBD5E1', '#F59E0B']
  const r = 36
  const c = 2 * Math.PI * r
  const lens = values.map((v) => (v.value / total) * c)
  const offsets = lens.map((_, i) => lens.slice(0, i).reduce((a, b) => a + b, 0))
  return (
    <svg viewBox="0 0 100 100" className="dp-donut" aria-hidden="true">
      <circle cx="50" cy="50" r={r} fill="none" stroke="#F1F5F9" strokeWidth="12" />
      {values.map((v, i) => (
          <circle
            key={v.label}
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke={colours[i]}
            strokeWidth="12"
            strokeDasharray={`${lens[i] - 1.2} ${c - lens[i] + 1.2}`}
            strokeDashoffset={-offsets[i]}
            transform="rotate(-90 50 50)"
          />
      ))}
    </svg>
  )
}

export function DashboardPreview() {
  const section = useRef<HTMLElement>(null)
  const frame = useRef<HTMLDivElement>(null)

  // Enters with scale 0.94→1, opacity, y 60→0 and a slight rotateX settling to ~3° (Part F12).
  useLayoutEffect(() => {
    const el = frame.current
    if (!el) return
    const ctx = gsap.context(() => {
      if (prefersReducedMotion()) {
        gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: duration.ui, scrollTrigger: { trigger: el, start: 'top 85%', once: true } })
        return
      }
      gsap.fromTo(
        el,
        { opacity: 0, y: 60, scale: 0.94, rotateX: 14 },
        { opacity: 1, y: 0, scale: 1, rotateX: 3, duration: duration.cinematic, ease: ease.gsap, scrollTrigger: { trigger: el, start: 'top 85%', once: true } },
      )
    })
    return () => ctx.revert()
  }, [])

  const max = Math.max(...dashboard.perUpload)
  const nav = [
    { icon: LayoutDashboard, label: 'Overview', active: true },
    { icon: Package, label: 'Returns' },
    { icon: Plus, label: 'New inspection' },
    { icon: ClipboardCheck, label: 'Review queue' },
  ]

  return (
    <section ref={section} className="lp-section lp-dash" data-shot="dashboard" aria-labelledby="dash-title">
      <Reveal className="lp-head lp-center">
        <span data-reveal="eyebrow">
          <Eyebrow>The workspace</Eyebrow>
        </span>
        <KineticHeadline id="dash-title" className="lp-h2" parts={[{ text: 'Turn returned units into' }, { text: 'clear outcomes.', accent: true }]} />
        <p className="lp-lead" data-reveal="text">
          Upload a batch, watch each row's status, and work the review queue. The dashboard counts what the rows say, and
          nothing else.
        </p>
      </Reveal>

      <div className="dp-stage">
        <div ref={frame} className="dp-frame-wrap">
          <Depth depth={0} tilt={P.tiltDeg} float={false} className="dp-tilt">
            <div className="dp-frame" aria-hidden="true">
              <aside className="dp-side">
                <span className="dp-brand">
                  <i /> sydon
                </span>
                {nav.map((n) => {
                  const Icon = n.icon
                  return (
                    <span className={`dp-nav ${n.active ? 'active' : ''}`} key={n.label}>
                      <Icon size={13} /> {n.label}
                    </span>
                  )
                })}
              </aside>
              <div className="dp-main">
                <div className="dp-top">
                  <b>Returns overview</b>
                  <span className="dp-search">Search returns, orders, units…</span>
                </div>
                <div className="dp-tiles">
                  {dashboard.tiles.map((t) => (
                    <div className="dp-tile" key={t.label}>
                      <small>{t.label}</small>
                      <b>{t.value}</b>
                    </div>
                  ))}
                </div>
                <div className="dp-panels">
                  <div className="dp-panel">
                    <small>Rows per upload</small>
                    <div className="dp-bars">
                      {dashboard.perUpload.map((v, i) => (
                        <span key={i} style={{ height: `${(v / max) * 100}%` }} />
                      ))}
                    </div>
                  </div>
                  <div className="dp-panel dp-mix">
                    <small>Disposition mix</small>
                    <div className="dp-mix-body">
                      <Donut values={dashboard.mix} />
                      <ul>
                        {dashboard.mix.map((m) => (
                          <li key={m.label}>
                            <i className={`dp-key dp-key-${m.label.split(' ')[0].toLowerCase()}`} /> {m.label}
                            <b>{m.value}</b>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Depth>
          <Depth depth={P.heroMid} seed={0.31} className="dp-float dp-float-a">
            <div className="dp-float-card">
              <small>Needs attention</small>
              <b>17</b>
              <span>Rows awaiting review or needing attention</span>
            </div>
          </Depth>
          <Depth depth={P.heroFront} seed={0.74} className="dp-float dp-float-b">
            <div className="dp-float-card">
              <small>Auto-approved</small>
              <b>41</b>
              <span>Threshold not yet calibrated</span>
            </div>
          </Depth>
        </div>
        <div className="dp-caption">
          <SampleTag />
          <span>Preview of the dashboard's real tiles and charts. Every value shown is sample data.</span>
        </div>
      </div>
    </section>
  )
}

export function FinalCta() {
  return (
    <section className="lp-section lp-cta" data-shot="cta" aria-labelledby="cta-title">
      <div className="cta-card">
        <div className="cta-glow" aria-hidden="true" />
        <KineticHeadline
          id="cta-title"
          className="cta-title"
          parts={[{ text: 'Returns are decisions.' }, { text: 'Make each one clear.', accent: true }]}
        />
        <Reveal className="cta-actions">
          <p data-reveal="text">Open the workspace, upload a batch, and review what the evidence says.</p>
          <div data-reveal="text" className="cta-buttons">
            <Button to="/dashboard" size="lg" arrow>
              Open sydon
            </Button>
            <Button to="/returns/new" size="lg" variant="secondary">
              Start a batch inspection
            </Button>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

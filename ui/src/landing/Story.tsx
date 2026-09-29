// E2 The problem, and E3 The Return Journey (pinned on desktop, vertical on mobile).
import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import { Eyebrow } from '../design/components'
import { KineticHeadline, Reveal } from '../motion/components'
import { prefersReducedMotion } from '../motion/scroll'
import { ease } from '../motion/tokens'

const problemLines = [
  'A returned unit has to be identified.',
  'Its order has to be matched.',
  'Its parts have to be accounted for.',
  'Its condition has to be graded.',
  'The evidence has to be kept.',
  'Then someone decides what happens next.',
]

export function Problem() {
  return (
    <section className="lp-section lp-problem" data-shot="problem" aria-labelledby="problem-title">
      <Reveal className="lp-problem-grid">
        <div className="lp-problem-head">
          <span data-reveal="eyebrow">
            <Eyebrow>The problem</Eyebrow>
          </span>
          <KineticHeadline
            id="problem-title"
            className="lp-h2"
            parts={[{ text: "Returns aren't just refunds." }, { text: "They're decisions.", accent: true }]}
          />
        </div>
        <div className="lp-problem-list">
          <ol>
            {problemLines.map((line, i) => (
              <li key={line} data-reveal="text">
                <span className="lp-problem-num">{String(i + 1).padStart(2, '0')}</span>
                {line}
              </li>
            ))}
          </ol>
          <p className="lp-problem-close" data-reveal="text">
            Today that varies by operator and shift, and the reasoning often isn't recorded.
          </p>
        </div>
      </Reveal>
    </section>
  )
}

const journeySteps = [
  { name: 'Return received', text: 'Photos and the return row are stored before any model call.' },
  { name: 'Product identity', text: 'Distinguishing features on the product body, plus any decoded barcode.' },
  { name: 'Parts', text: 'Every part on the parts list: present, missing, or not visible.' },
  { name: 'Condition', text: 'Observed state and defects, graded against the category rubric.' },
  { name: 'Evidence', text: 'Every observation points to a photo, and code checks every reference.' },
  { name: 'Recommendation', text: 'The rules engine computes a route and names the rule it used.' },
  { name: 'Human review', text: 'An operator confirms or overrides. Some routes need a second person.' },
  { name: 'Disposition', text: 'Restock, refurbish, liquidate or dispose.' },
  { name: 'Audit trail', text: 'Each step is recorded as an event.' },
]

export function Journey() {
  const section = useRef<HTMLElement>(null)
  const track = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const root = section.current
    if (!root) return
    const nodes = Array.from(root.querySelectorAll<HTMLElement>('.jr-step'))
    const fill = root.querySelector<HTMLElement>('.jr-fill')
    const setActive = (p: number) => {
      // step i activates once the line reaches it; "Return received" is always on
      const n = nodes.length
      nodes.forEach((node, i) => {
        const at = i / (n - 1)
        node.classList.toggle('on', i === 0 || p >= at - 0.001)
        node.classList.toggle('current', p >= at - 0.001 && (i === n - 1 || p < (i + 1) / (n - 1)))
      })
    }
    if (prefersReducedMotion()) {
      setActive(1)
      if (fill) fill.style.transform = 'none'
      return
    }
    const mm = gsap.matchMedia()
    mm.add('(min-width: 1024px)', () => {
      gsap.set(fill, { scaleX: 0, scaleY: 1 })
      gsap.to(fill, {
        scaleX: 1,
        ease: ease.linear,
        scrollTrigger: {
          trigger: root,
          start: 'top top',
          end: () => `+=${Math.round(window.innerHeight * 1.6)}`,
          pin: true,
          scrub: 0.6,
          anticipatePin: 1,
          invalidateOnRefresh: true,
          onUpdate: (self) => setActive(self.progress),
        },
      })
    })
    mm.add('(max-width: 1023px)', () => {
      gsap.set(fill, { scaleY: 0, scaleX: 1 })
      gsap.to(fill, {
        scaleY: 1,
        ease: ease.linear,
        scrollTrigger: {
          trigger: track.current,
          start: 'top 70%',
          end: 'bottom 60%',
          scrub: 0.4,
          onUpdate: (self) => setActive(self.progress),
        },
      })
    })
    setActive(0)
    return () => mm.revert()
  }, [])

  return (
    <section ref={section} className="lp-journey" id="journey" aria-labelledby="journey-title">
      <div className="lp-journey-inner">
        <Reveal className="lp-head lp-center">
          <span data-reveal="eyebrow">
            <Eyebrow>The return journey</Eyebrow>
          </span>
          <KineticHeadline
            id="journey-title"
            className="lp-h2"
            parts={[{ text: 'Know what came back.' }, { text: 'Know what belongs.', muted: true }, { text: 'Know what happens next.', accent: true }]}
          />
        </Reveal>
        <div ref={track} className="jr-track">
          <div className="jr-line" aria-hidden="true">
            <span className="jr-fill" />
          </div>
          <ol className="jr-steps">
            {journeySteps.map((s, i) => (
              <li className="jr-step" key={s.name}>
                <span className="jr-dot" aria-hidden="true">
                  <span>{i + 1}</span>
                </span>
                <b>{s.name}</b>
                <p>{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}

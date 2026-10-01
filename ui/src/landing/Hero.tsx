// E1 Hero: kinetic headline over the particle field, and a layered 2.5D composition of real
// Return Manager card types built from the sample unit (labelled Sample data). On capable desktops
// the same cards are swapped for a Level 3 scene (three/HeroScene), loaded as its own chunk; the
// DOM cards stay in place underneath (still read by screen readers) and remain the fallback.
import { lazy, Suspense, useCallback, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { Check, Camera, CircleDot, ScanLine, X } from 'lucide-react'
import { Button, Eyebrow, SampleTag } from '../design/components'
import { Depth, KineticHeadline, Reveal } from '../motion/components'
import { ParticleField } from '../motion/ParticleField'
import { prefersReducedMotion } from '../motion/scroll'
import { ease, heroScroll, pointer as P } from '../motion/tokens'
import { LampArt } from './art'
import { SceneBoundary } from './three/SceneBoundary'
import { useSceneGate } from './three/support'
import { condition, identity, parts, recommendation, unit } from './sample'

const HeroScene = lazy(() => import('./three/HeroScene'))

export function Hero() {
  const stage = useRef<HTMLDivElement>(null)
  const rig = useRef<HTMLDivElement>(null)
  const progress = useRef(0)
  const use3d = useSceneGate(stage)
  const [ready3d, setReady3d] = useState(false)
  const onLive = useCallback((live: boolean) => setReady3d(live), [])
  const live3d = use3d && ready3d // Level 2 returns the moment the scene is dropped

  // Scroll-linked hand-off (Part F7): the visual moves up, scales, tilts and recedes as the page scrolls.
  useLayoutEffect(() => {
    if (!stage.current || !rig.current || prefersReducedMotion()) return
    const ctx = gsap.context(() => {
      gsap.to(rig.current, {
        y: heroScroll.y,
        scale: heroScroll.scale,
        rotateX: heroScroll.rotateX,
        opacity: heroScroll.opacity,
        ease: ease.linear,
        scrollTrigger: {
          trigger: stage.current,
          start: 'top 60%',
          end: 'bottom top',
          scrub: true,
          onUpdate: (self) => (progress.current = self.progress), // drives the Level 3 hand-off too
        },
      })
    })
    return () => ctx.revert()
  }, [])

  const present = parts.filter((p) => p.state === 'present').length

  return (
    <section className="lp-hero" id="top" aria-labelledby="hero-title">
      <ParticleField className="lp-hero-particles" />
      <div className="lp-hero-glow" aria-hidden="true" />
      <Reveal className="lp-hero-copy" immediate>
        <span data-reveal="eyebrow">
          <Eyebrow>The return inspection workflow</Eyebrow>
        </span>
        <KineticHeadline
          as="h1"
          id="hero-title"
          className="lp-hero-title"
          immediate
          delay={0.1}
          parts={[{ text: 'Turn every return into a' }, { text: 'clear decision.', accent: true }]}
        />
        <p className="lp-hero-sub" data-reveal="text">
          sydon checks a returned item's identity, parts and condition from photos, records the evidence, and
          computes one of four dispositions for your team to confirm.
        </p>
        <div className="lp-hero-ctas" data-reveal="text">
          <Button to="/dashboard" size="lg" arrow>
            Open sydon
          </Button>
          <Button href="#journey" variant="secondary" size="lg">
            See how it works
          </Button>
        </div>
      </Reveal>

      <Reveal className="hero-stage" immediate>
        <div ref={stage} className={`hero-stage-inner${live3d ? ' is-3d' : ''}`} data-reveal="visual">
          {use3d && (
            <SceneBoundary>
              <Suspense fallback={null}>
                <HeroScene rig={rig} progress={progress} onLive={onLive} />
              </Suspense>
            </SceneBoundary>
          )}
          <div ref={rig} className="hero-rig">
            {/* back layer: evidence */}
            <Depth depth={P.heroBack} seed={0.21} className="hc hc-evidence">
              <div className="hc-card">
                <div className="hc-head">
                  <Camera size={14} /> Evidence <span className="hc-count">{unit.photos} photos</span>
                </div>
                <div className="hc-thumbs">
                  {[0, 1, 2].map((a) => (
                    <LampArt key={a} angle={a as 0 | 1 | 2} className="hc-thumb" />
                  ))}
                </div>
                <p className="hc-foot">Illustrations, not product photos</p>
              </div>
            </Depth>

            {/* middle layer: the return record and its checks */}
            <Depth depth={P.heroMid} seed={0.57} className="hc hc-record">
              <div className="hc-card hc-card-main">
                <div className="hc-record-top">
                  <div>
                    <small>Return</small>
                    <b>{unit.returnId}</b>
                  </div>
                  <SampleTag />
                </div>
                <dl className="hc-ids">
                  <div><dt>Unit</dt><dd>{unit.unitId}</dd></div>
                  <div><dt>Order</dt><dd>{unit.orderId}</dd></div>
                  <div><dt>SKU</dt><dd>{unit.sku}</dd></div>
                  <div><dt>ASIN</dt><dd>{unit.asin}</dd></div>
                </dl>
                <div className="hc-checks">
                  <div className="hc-check ok">
                    <span className="hc-ic"><ScanLine size={14} /></span>
                    <span>
                      <small>Product identity (photo)</small>
                      <b>{identity.verdict} · 2 of 2 critical features matched</b>
                    </span>
                  </div>
                  <div className="hc-check ok">
                    <span className="hc-ic"><Check size={14} /></span>
                    <span>
                      <small>Sold vs returned records</small>
                      <b>Records match</b>
                    </span>
                  </div>
                  <div className="hc-check warn">
                    <span className="hc-ic"><X size={14} /></span>
                    <span>
                      <small>Parts</small>
                      <b>
                        {present} of {parts.length} present · USB cable missing
                      </b>
                    </span>
                  </div>
                  <div className="hc-check ok">
                    <span className="hc-ic"><CircleDot size={14} /></span>
                    <span>
                      <small>Condition</small>
                      <b>
                        {condition.grade} · {condition.observedState}
                      </b>
                    </span>
                  </div>
                </div>
              </div>
            </Depth>

            {/* front layer: the engine's recommendation */}
            <Depth depth={P.heroFront} seed={0.83} className="hc hc-disposition">
              <div className="hc-card hc-card-front">
                <small>Recommended disposition</small>
                <div className="hc-route">
                  <b>{recommendation.route}</b>
                  <span className="hc-rule">{recommendation.rule}</span>
                </div>
                <p>Computed by the rules engine · awaiting operator</p>
              </div>
            </Depth>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

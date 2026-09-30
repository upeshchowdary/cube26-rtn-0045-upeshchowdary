// The Return Manager landing page. Lazy-loaded from App.tsx so the workspace never loads it.
// Story: problem → system → workflow → product → evidence → decision → trail → FAQ → CTA.
import { useEffect, useLayoutEffect } from 'react'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { BackToTop, Eyebrow, Faq, SiteFooter, SiteHeader } from '../design/components'
import { KineticHeadline, Reveal } from '../motion/components'
import { usePointer, useScrollProgress } from '../motion/hooks'
import { acquireLenis, releaseLenis } from '../motion/lenis'
import { anchors, appLinks, faq, footerLinks } from './content'
import { Condition, Identity, Parts } from './Checks'
import { Decision, Exceptions, Synthesis } from './Decide'
import { Hero } from './Hero'
import { Journey, Problem } from './Story'
import { Audit, DashboardPreview, FinalCta } from './Trail'
import './landing.css'

export default function Landing() {
  useLayoutEffect(() => {
    acquireLenis()
    return () => releaseLenis()
  }, [])
  usePointer()

  // Header progress line: page scroll 0→1 written straight to the element's transform.
  useScrollProgress(null, (p) => {
    const bar = document.querySelector<HTMLElement>('[data-scroll-progress]')
    if (bar) bar.style.transform = `scaleX(${p.toFixed(4)})`
  }, { allowReduced: true })

  // Fonts change line heights; refresh trigger positions once they have loaded.
  useEffect(() => {
    let cancelled = false
    document.fonts?.ready.then(() => !cancelled && ScrollTrigger.refresh())
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="rm-site">
      <a className="lp-skip" href="#main">
        Skip to content
      </a>
      <SiteHeader anchors={anchors} appLinks={appLinks} />
      <main id="main">
        <Hero />
        <Problem />
        <Journey />
        <Identity />
        <Parts />
        <Condition />
        <Synthesis />
        <Decision />
        <Exceptions />
        <Audit />
        <DashboardPreview />

        <section className="lp-section lp-faq" id="faq" aria-labelledby="faq-title">
          <Reveal className="lp-head lp-center">
            <span data-reveal="eyebrow">
              <Eyebrow>Common questions</Eyebrow>
            </span>
            <KineticHeadline id="faq-title" className="lp-h2" parts={[{ text: 'What teams ask' }, { text: 'first.', accent: true }]} />
          </Reveal>
          <Reveal className="lp-faq-wrap">
            <div data-reveal="visual">
              <Faq items={faq} />
            </div>
          </Reveal>
        </section>

        <FinalCta />
      </main>
      <SiteFooter
        links={footerLinks}
        statement={
          <KineticHeadline
            as="p"
            parts={[{ text: 'Every return.' }, { text: 'Every inspection.', muted: true }, { text: 'One clear decision.', accent: true }]}
          />
        }
      />
      <BackToTop />
    </div>
  )
}

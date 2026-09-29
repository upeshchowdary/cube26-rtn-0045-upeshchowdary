// The Return Manager landing page. Lazy-loaded from App.tsx so the workspace never loads it.
import { useEffect } from 'react'
import { BackToTop, Button, Eyebrow, Faq, SiteFooter, SiteHeader } from '../design/components'
import { acquireLenis, releaseLenis } from '../motion/lenis'
import { anchors, appLinks, faq, footerLinks } from './content'
import './landing.css'

export default function Landing() {
  useEffect(() => {
    acquireLenis()
    return () => releaseLenis()
  }, [])

  return (
    <div className="rm-site">
      <SiteHeader anchors={anchors} appLinks={appLinks} />
      <main id="main">
        <section className="lp-hero" id="top">
          <div className="lp-hero-copy">
            <Eyebrow>The return inspection workflow</Eyebrow>
            <h1 className="lp-hero-title">
              Turn every return into a <span className="lp-accent">clear decision.</span>
            </h1>
            <p className="lp-hero-sub">
              Return Manager checks a returned item's identity, parts and condition from photos, records the evidence,
              and computes one of four dispositions for your team to confirm.
            </p>
            <div className="lp-hero-ctas">
              <Button to="/dashboard" size="lg" arrow>
                Open Return Manager
              </Button>
              <Button href="#journey" variant="secondary" size="lg">
                See how it works
              </Button>
            </div>
          </div>
        </section>

        <section className="lp-section lp-faq" id="faq" aria-labelledby="faq-title">
          <div className="lp-head lp-center">
            <Eyebrow>Common questions</Eyebrow>
            <h2 id="faq-title" className="lp-h2">
              What teams ask <span className="lp-accent">first.</span>
            </h2>
          </div>
          <div className="lp-faq-wrap">
            <Faq items={faq} />
          </div>
        </section>
      </main>
      <SiteFooter
        links={footerLinks}
        statement={
          <>
            Every return. <span className="muted">Every inspection.</span> <span className="accent">One clear decision.</span>
          </>
        }
      />
      <BackToTop />
    </div>
  )
}

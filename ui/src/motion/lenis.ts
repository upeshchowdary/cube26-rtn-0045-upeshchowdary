// Exactly one Lenis instance for the whole app, driven by the GSAP ticker (Part F1).
// Pages acquire it on mount and release it on unmount; the last release tears everything down,
// so route changes never leave a second smooth-scroll loop or a stale ticker callback behind.
// Only the landing page imports this module (it carries GSAP + Lenis).
import Lenis from 'lenis'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { prefersReducedMotion, setScroller } from './scroll'
import { scroll } from './tokens'

gsap.registerPlugin(ScrollTrigger)

let lenis: Lenis | null = null
let holders = 0
let tick: ((time: number) => void) | null = null

/** Returns the shared instance, or null under reduced motion (native scrolling, no inertia). */
export function acquireLenis(): Lenis | null {
  holders += 1
  if (prefersReducedMotion()) return null
  if (!lenis) {
    const instance = new Lenis({
      duration: scroll.lenisDuration,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      wheelMultiplier: scroll.wheelMultiplier,
      touchMultiplier: scroll.touchMultiplier,
      autoRaf: false,
    })
    instance.on('scroll', ScrollTrigger.update)
    tick = (time: number) => instance.raf(time * 1000)
    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)
    setScroller({ scrollTo: (target, opts) => instance.scrollTo(target, opts) })
    lenis = instance
  }
  return lenis
}

export function releaseLenis(): void {
  holders = Math.max(0, holders - 1)
  if (holders > 0 || !lenis) return
  if (tick) gsap.ticker.remove(tick)
  lenis.off('scroll', ScrollTrigger.update)
  lenis.destroy()
  setScroller(null)
  lenis = null
  tick = null
}

export function getLenis(): Lenis | null {
  return lenis
}

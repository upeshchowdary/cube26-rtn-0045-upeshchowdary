// Dependency-free scroll helpers. Components shared with the app import these, not lenis.ts, so
// the workspace screens never pull GSAP or Lenis into their bundle. lenis.ts registers itself
// here while the landing page holds it.
import { duration } from './tokens'

type Scroller = { scrollTo: (target: string | number | HTMLElement, opts: { offset: number; duration: number }) => void }

let scroller: Scroller | null = null

export function setScroller(next: Scroller | null): void {
  scroller = next
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Smooth scroll through Lenis when it is active; otherwise native (instant under reduced motion). */
export function scrollToTarget(target: string | number | HTMLElement, offset = 0): void {
  if (scroller) {
    scroller.scrollTo(target, { offset, duration: duration.cinematic })
    return
  }
  const behavior: ScrollBehavior = prefersReducedMotion() ? 'auto' : 'smooth'
  if (typeof target === 'number') {
    window.scrollTo({ top: target, behavior })
    return
  }
  const el = typeof target === 'string' ? document.querySelector<HTMLElement>(target) : target
  if (!el) return
  window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY + offset, behavior })
}

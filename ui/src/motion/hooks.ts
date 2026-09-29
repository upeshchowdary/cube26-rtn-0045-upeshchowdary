// Reusable motion hooks (Part F1); the components that use them are in components.tsx. Every ScrollTrigger / tween lives in a
// gsap.context that is reverted on unmount, so route changes leave no triggers or listeners.
import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { startPointer, stopPointer } from './pointer'
import { prefersReducedMotion } from './scroll'
import { distance, duration, ease, scroll, stagger } from './tokens'

gsap.registerPlugin(ScrollTrigger)

export const useIsoLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect

/**
 * Section reveal (Part F4): children marked data-reveal="eyebrow|heading|text|visual" enter in that
 * order, once, as the section scrolls in. Under reduced motion it is a plain opacity fade.
 */
export function useReveal<T extends HTMLElement>(ref: RefObject<T | null>, opts: { start?: string; immediate?: boolean } = {}) {
  useIsoLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    const ctx = gsap.context(() => {
      const q = (kind: string) => gsap.utils.toArray<HTMLElement>(root.querySelectorAll(`[data-reveal="${kind}"]`))
      const all = gsap.utils.toArray<HTMLElement>(root.querySelectorAll('[data-reveal]'))
      if (!all.length) return
      const reduced = prefersReducedMotion()
      const tl = gsap.timeline({
        paused: true,
        defaults: { ease: ease.gsap, duration: duration.reveal },
      })
      if (reduced) {
        tl.fromTo(all, { opacity: 0 }, { opacity: 1, duration: duration.ui, stagger: stagger.tight })
      } else {
        const eyebrow = q('eyebrow')
        const heading = q('heading')
        const text = q('text')
        const visual = q('visual')
        if (eyebrow.length) tl.fromTo(eyebrow, { opacity: 0, y: distance.eyebrowY }, { opacity: 1, y: 0, stagger: stagger.base }, 0)
        if (heading.length) tl.fromTo(heading, { opacity: 0, y: distance.headingY }, { opacity: 1, y: 0, stagger: stagger.base }, 0.08)
        if (text.length) tl.fromTo(text, { opacity: 0, y: distance.paragraphY }, { opacity: 1, y: 0, stagger: stagger.base }, 0.18)
        if (visual.length)
          tl.fromTo(
            visual,
            { opacity: 0, y: distance.visualY, scale: distance.visualScaleFrom, filter: `blur(${distance.visualBlurFrom}px)` },
            { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)', stagger: stagger.loose, clearProps: 'filter' },
            0.26,
          )
      }
      if (opts.immediate) {
        tl.play()
      } else {
        ScrollTrigger.create({ trigger: root, start: opts.start ?? scroll.revealStart, once: true, onEnter: () => tl.play() })
      }
    }, root)
    return () => ctx.revert()
  }, [])
}

/** Parallax (Part F7): moves the element by `strength` × scroll distance while its section is in view. */
export function useParallax<T extends HTMLElement>(ref: RefObject<T | null>, strength: number) {
  useIsoLayoutEffect(() => {
    const el = ref.current
    if (!el || prefersReducedMotion()) return
    const ctx = gsap.context(() => {
      gsap.fromTo(
        el,
        { y: () => window.innerHeight * strength },
        {
          y: () => -window.innerHeight * strength,
          ease: ease.linear,
          scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true, invalidateOnRefresh: true },
        },
      )
    })
    return () => ctx.revert()
  }, [strength])
}

/**
 * Scroll progress 0→1 across a trigger (or the whole document when trigger is null), delivered to a
 * callback that writes to the DOM directly. Scrubbed sequences are disabled under reduced motion.
 */
export function useScrollProgress(
  trigger: RefObject<HTMLElement | null> | null,
  onProgress: (p: number) => void,
  opts: { start?: string; end?: string; allowReduced?: boolean } = {},
) {
  const cb = useRef(onProgress)
  useIsoLayoutEffect(() => {
    cb.current = onProgress
  })
  useIsoLayoutEffect(() => {
    if (prefersReducedMotion() && !opts.allowReduced) {
      cb.current(1)
      return
    }
    const st = ScrollTrigger.create({
      trigger: trigger ? trigger.current : document.documentElement,
      start: opts.start ?? 'top top',
      end: opts.end ?? 'bottom bottom',
      onUpdate: (self) => cb.current(self.progress),
      onRefresh: (self) => cb.current(self.progress),
    })
    return () => st.kill()
  }, [])
}

/** Starts the shared pointer loop for as long as the calling component is mounted. */
export function usePointer() {
  useEffect(() => {
    startPointer()
    return () => stopPointer()
  }, [])
}


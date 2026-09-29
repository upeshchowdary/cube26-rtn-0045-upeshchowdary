// Reusable motion components (Part F1): Reveal, KineticHeadline, Depth.
import { Fragment, useEffect, useRef, type ElementType, type ReactNode } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useIsoLayoutEffect, useReveal } from './hooks'
import { registerLayer } from './pointer'
import { prefersReducedMotion } from './scroll'
import { duration, ease, scroll, stagger } from './tokens'

gsap.registerPlugin(ScrollTrigger)

export function Reveal({
  as: Tag = 'div',
  children,
  className,
  id,
  immediate,
  ...rest
}: { as?: ElementType; children: ReactNode; className?: string; id?: string; immediate?: boolean } & Record<string, unknown>) {
  const ref = useRef<HTMLElement>(null)
  useReveal(ref, { immediate })
  return (
    <Tag ref={ref} className={className} id={id} {...rest}>
      {children}
    </Tag>
  )
}

export type HeadlinePart = { text: string; accent?: boolean; muted?: boolean; br?: boolean }

/**
 * Kinetic typography (Part F5): word-by-word clip + translateY + opacity. Only for the hero,
 * major section headlines and the final CTA. The full sentence stays in the DOM for screen readers.
 */
export function KineticHeadline({
  parts,
  as: Tag = 'h2',
  className,
  id,
  immediate = false,
  delay = 0,
}: {
  parts: HeadlinePart[]
  as?: ElementType
  className?: string
  id?: string
  immediate?: boolean
  delay?: number
}) {
  const ref = useRef<HTMLElement>(null)
  useIsoLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    const ctx = gsap.context(() => {
      const words = gsap.utils.toArray<HTMLElement>(root.querySelectorAll('.kw-i'))
      const reduced = prefersReducedMotion()
      const from = reduced ? { opacity: 0 } : { yPercent: 105, opacity: 0 }
      const to = reduced
        ? { opacity: 1, duration: duration.ui, stagger: stagger.tight }
        : { yPercent: 0, opacity: 1, duration: duration.reveal, ease: ease.gsap, stagger: stagger.base }
      gsap.set(words, from)
      const play = () => gsap.to(words, { ...to, delay })
      if (immediate) play()
      else ScrollTrigger.create({ trigger: root, start: scroll.revealStart, once: true, onEnter: play })
    }, root)
    return () => ctx.revert()
  }, [])

  const label = parts.map((p) => p.text).join(' ')
  let key = 0
  return (
    <Tag ref={ref} className={`kinetic ${className ?? ''}`} id={id} aria-label={label}>
      {parts.map((part) => {
        const words = part.text.split(' ').filter(Boolean)
        return [
          ...words.map((w) => (
            <Fragment key={key++}>
              <span className="kw" aria-hidden="true">
                <span className={`kw-i ${part.accent ? 'lp-accent' : ''} ${part.muted ? 'kw-muted' : ''}`}>{w}</span>
              </span>{' '}
            </Fragment>
          )),
          part.br ? <br key={key++} /> : null,
        ]
      })}
    </Tag>
  )
}

/** A 2.5D layer (Part F3 Level 2): moves with the pointer at its own depth and floats on its own phase. */
export function Depth({
  children,
  depth,
  tilt = 0,
  float = true,
  seed,
  className,
  style,
}: {
  children: ReactNode
  depth: number
  tilt?: number
  float?: boolean
  seed?: number
  className?: string
  style?: React.CSSProperties
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    return registerLayer(ref.current, { depth, tilt, float, seed })
  }, [depth, tilt, float, seed])
  return (
    <div ref={ref} className={`depth ${className ?? ''}`} style={style}>
      {children}
    </div>
  )
}

// The one place for every animation value (Part F2). Components never hard-code a duration,
// easing, distance, stagger or strength; they read it from here. CSS mirrors the few it needs
// in src/design/tokens.css (--ease, --t-fast, --t-hover, --t-ui).

export const ease = {
  /** Standard ease-out for UI and reveals. */
  css: 'cubic-bezier(0.22, 1, 0.36, 1)',
  gsap: 'power3.out',
  /** Small elements (chips, icons). */
  gsapSmall: 'power2.out',
  /** Floating layers. */
  float: 'sine.inOut',
  /** Continuous particles and backgrounds only. */
  linear: 'none',
} as const

/** Seconds (GSAP convention). */
export const duration = {
  fast: 0.18,
  hover: 0.24,
  ui: 0.38,
  page: 0.55,
  reveal: 0.85,
  cinematic: 1.2,
  driftMin: 5,
  driftMax: 20,
} as const

export const stagger = {
  tight: 0.05,
  base: 0.08,
  loose: 0.12,
} as const

/** Pixel distances. */
export const distance = {
  eyebrowY: 20,
  headingY: 35,
  paragraphY: 24,
  visualY: 40,
  visualScaleFrom: 0.97,
  visualBlurFrom: 8,
  cardLift: 3,
  arrowNudge: 3,
  wordY: 0.9, // em, for kinetic headline words
} as const

/** Parallax as a fraction of scroll delta (Part F7). */
export const parallax = {
  background: 0.1,
  decorative: 0.2,
  product: 0.05,
} as const

export const pointer = {
  /** Interpolation factor per frame: current += (target - current) * damping. */
  damping: 0.08,
  /** Hero layers, px of travel at pointer = ±1 (Part F13: 3–8px). */
  heroBack: 3,
  heroMid: 5,
  heroFront: 8,
  /** Max tilt in degrees for the dashboard preview (Part F12: ≤ 2–3°). */
  tiltDeg: 2.5,
} as const

export const float = {
  /** px of vertical travel (Part F13: 2–8px). */
  yMin: 2,
  yMax: 6,
  /** degrees of rotation (0.1–0.5°). */
  rotMin: 0.1,
  rotMax: 0.4,
  /** seconds per half-cycle (4–8s full cycle). */
  periodMin: 2.2,
  periodMax: 4,
} as const

export const particles = {
  densityDesktop: 0.00009, // particles per CSS px² of canvas
  densityMobile: 0.00004,
  maxCount: 150,
  sizeMin: 1,
  sizeMax: 2.4,
  speed: 0.06, // px per frame at 60 fps
  repelRadius: 110,
  repelStrength: 10, // max px pushed away from the pointer
  returnDamping: 0.05,
  velocityBoost: 0.015, // extra drift per px/frame of scroll velocity
  velocityMax: 1.6,
  /** Keep the headline area clear: particles are weighted to the edges. */
  centreClear: 0.34,
} as const

export const scroll = {
  /** Lenis (one instance, driven by the GSAP ticker). */
  lenisDuration: 1.05,
  wheelMultiplier: 0.95,
  touchMultiplier: 1.4,
  /** Reveal trigger: when the element's top reaches this viewport position. */
  revealStart: 'top 82%',
} as const

export const heroScroll = {
  /** As scrolling begins the hero visual moves up, scales slightly and tilts (Part F7). */
  y: -80,
  scale: 0.94,
  rotateX: 6,
  opacity: 0.55,
} as const

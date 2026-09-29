// One global, normalised (−1…1) pointer with damping, and one ticker that moves every 2.5D layer
// (Part F13). Layers register an element + depth; nothing calls React setState per frame.
import gsap from 'gsap'
import { prefersReducedMotion } from './scroll'
import { float, pointer as P } from './tokens'

export type PointerState = { x: number; y: number; tx: number; ty: number; active: boolean }

export const pointerState: PointerState = { x: 0, y: 0, tx: 0, ty: 0, active: false }

type Layer = {
  el: HTMLElement
  depth: number // px of travel at pointer = ±1
  tilt: number // degrees of rotateX/Y at pointer = ±1
  floatY: number
  floatRot: number
  period: number
  phase: number
  visible: boolean
}

const layers = new Set<Layer>()
let holders = 0
let tick: (() => void) | null = null
let onMove: ((e: PointerEvent) => void) | null = null
let onLeave: (() => void) | null = null

function isFinePointer(): boolean {
  return window.matchMedia('(hover: hover) and (pointer: fine)').matches
}

export function startPointer(): void {
  holders += 1
  if (tick) return
  const fine = isFinePointer()
  const reduced = prefersReducedMotion()
  if (fine && !reduced) {
    onMove = (e: PointerEvent) => {
      pointerState.tx = (e.clientX / window.innerWidth) * 2 - 1
      pointerState.ty = (e.clientY / window.innerHeight) * 2 - 1
      pointerState.active = true
    }
    onLeave = () => {
      pointerState.tx = 0
      pointerState.ty = 0
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('pointerleave', onLeave)
  }
  const t0 = performance.now()
  tick = () => {
    pointerState.x += (pointerState.tx - pointerState.x) * P.damping
    pointerState.y += (pointerState.ty - pointerState.y) * P.damping
    if (reduced) return
    const t = (performance.now() - t0) / 1000
    layers.forEach((l) => {
      if (!l.visible) return // off-screen layers cost nothing
      const f = Math.sin((t / l.period) * Math.PI + l.phase)
      const x = pointerState.x * l.depth
      const y = pointerState.y * l.depth + f * l.floatY
      const rx = -pointerState.y * l.tilt
      const ry = pointerState.x * l.tilt
      l.el.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0) rotateX(${rx.toFixed(3)}deg) rotateY(${ry.toFixed(3)}deg) rotateZ(${(f * l.floatRot).toFixed(3)}deg)`
    })
  }
  gsap.ticker.add(tick)
}

export function stopPointer(): void {
  holders = Math.max(0, holders - 1)
  if (holders > 0 || !tick) return
  gsap.ticker.remove(tick)
  if (onMove) window.removeEventListener('pointermove', onMove)
  if (onLeave) document.removeEventListener('pointerleave', onLeave)
  tick = null
  onMove = null
  onLeave = null
  layers.clear()
  pointerState.x = pointerState.y = pointerState.tx = pointerState.ty = 0
}

/** Registers a 2.5D layer; returns its unregister function. Each layer floats on its own phase. */
export function registerLayer(
  el: HTMLElement,
  opts: { depth?: number; tilt?: number; float?: boolean; seed?: number } = {},
): () => void {
  const seed = opts.seed ?? Math.random()
  const layer: Layer = {
    el,
    depth: opts.depth ?? P.heroMid,
    tilt: opts.tilt ?? 0,
    floatY: opts.float === false ? 0 : float.yMin + (float.yMax - float.yMin) * seed,
    floatRot: opts.float === false ? 0 : float.rotMin + (float.rotMax - float.rotMin) * ((seed * 7.3) % 1),
    period: float.periodMin + (float.periodMax - float.periodMin) * ((seed * 3.7) % 1),
    phase: seed * Math.PI * 2,
    visible: true,
  }
  layers.add(layer)
  const io = new IntersectionObserver(([entry]) => {
    layer.visible = entry.isIntersecting
  })
  io.observe(el)
  return () => {
    io.disconnect()
    layers.delete(layer)
    el.style.transform = ''
  }
}

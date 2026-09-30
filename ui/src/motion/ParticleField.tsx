// Hero particle field (Part F6). Canvas, one GSAP-ticker callback, paused off-screen and when the
// tab is hidden. Sparse, tiny, low-opacity, weighted to the edges so the headline stays clear.
import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { getLenis } from './lenis'
import { prefersReducedMotion } from './scroll'
import { particles as T } from './tokens'

type Dot = {
  x: number
  y: number
  vx: number
  vy: number
  ox: number // pointer push offset
  oy: number
  r: number
  a: number // base alpha
  tw: number // twinkle phase
  tws: number // twinkle speed
  c: string
}

const COLOURS = ['37,99,235', '59,130,246', '34,211,238', '100,116,139', '148,163,184']
const WEIGHTS = [0.3, 0.26, 0.16, 0.16, 0.12]

function pickColour(r: number): string {
  let acc = 0
  for (let i = 0; i < COLOURS.length; i++) {
    acc += WEIGHTS[i]
    if (r <= acc) return COLOURS[i]
  }
  return COLOURS[0]
}

export function ParticleField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const reduced = prefersReducedMotion()
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches
    let w = 0
    let h = 0
    let dpr = 1
    let dots: Dot[] = []
    let visible = true
    let running = false
    const mouse = { x: -9999, y: -9999, on: false }

    // Weighted to the edges: reject points inside a central ellipse most of the time.
    const place = (): [number, number] => {
      for (let i = 0; i < 12; i++) {
        const x = Math.random() * w
        const y = Math.random() * h
        const nx = (x - w / 2) / (w / 2)
        const ny = (y - h * 0.45) / (h / 2)
        const d = nx * nx + ny * ny
        if (d > T.centreClear || Math.random() < 0.08) return [x, y]
      }
      return [Math.random() * w, Math.random() * h]
    }

    const build = () => {
      const rect = canvas.getBoundingClientRect()
      w = Math.max(1, rect.width)
      h = Math.max(1, rect.height)
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const density = w < 700 ? T.densityMobile : T.densityDesktop
      const n = Math.min(T.maxCount, Math.round(w * h * density))
      dots = Array.from({ length: n }, () => {
        const [x, y] = place()
        const angle = Math.random() * Math.PI * 2
        const speed = T.speed * (0.4 + Math.random() * 0.8)
        return {
          x,
          y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          ox: 0,
          oy: 0,
          r: T.sizeMin + Math.random() * (T.sizeMax - T.sizeMin),
          a: 0.18 + Math.random() * 0.42,
          tw: Math.random() * Math.PI * 2,
          tws: 0.004 + Math.random() * 0.01,
          c: pickColour(Math.random()),
        }
      }).sort((p, q) => (p.c < q.c ? -1 : p.c > q.c ? 1 : 0))
    }

    const draw = (step: boolean) => {
      ctx.clearRect(0, 0, w, h)
      const lenis = getLenis()
      const vel = lenis ? Math.min(T.velocityMax, Math.abs(lenis.velocity) * T.velocityBoost) : 0
      for (const d of dots) {
        if (step) {
          d.x += d.vx * (1 + vel)
          d.y += d.vy * (1 + vel)
          if (d.x < -4) d.x = w + 4
          else if (d.x > w + 4) d.x = -4
          if (d.y < -4) d.y = h + 4
          else if (d.y > h + 4) d.y = -4
          d.tw += d.tws
          // pointer: push a few px away, then ease back (damped)
          let tx = 0
          let ty = 0
          if (mouse.on) {
            const dx = d.x - mouse.x
            const dy = d.y - mouse.y
            const dist = Math.hypot(dx, dy)
            if (dist < T.repelRadius && dist > 0.01) {
              const f = (1 - dist / T.repelRadius) * T.repelStrength
              tx = (dx / dist) * f
              ty = (dy / dist) * f
            }
          }
          d.ox += (tx - d.ox) * T.returnDamping * 2
          d.oy += (ty - d.oy) * T.returnDamping * 2
        }
      }
      // Batched by colour (dots are pre-sorted): one fillStyle per group, alpha via globalAlpha.
      let colour = ''
      for (const d of dots) {
        if (d.c !== colour) {
          colour = d.c
          ctx.fillStyle = `rgb(${colour})`
        }
        ctx.globalAlpha = d.a * (0.72 + 0.28 * Math.sin(d.tw))
        ctx.fillRect(d.x + d.ox - d.r / 2, d.y + d.oy - d.r / 2, d.r, d.r)
      }
      ctx.globalAlpha = 1
    }

    const tick = () => draw(true)
    const start = () => {
      if (running || reduced || !visible || document.hidden) return
      running = true
      gsap.ticker.add(tick)
    }
    const stop = () => {
      if (!running) return
      running = false
      gsap.ticker.remove(tick)
    }

    build()
    draw(false)

    const ro = new ResizeObserver(() => {
      build()
      draw(false)
    })
    ro.observe(canvas)
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      if (visible) start()
      else stop()
    })
    io.observe(canvas)
    const onVis = () => (document.hidden ? stop() : start())
    document.addEventListener('visibilitychange', onVis)

    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      mouse.x = e.clientX - rect.left
      mouse.y = e.clientY - rect.top
      mouse.on = true
    }
    const onLeave = () => {
      mouse.on = false
    }
    if (fine && !reduced) {
      window.addEventListener('pointermove', onMove, { passive: true })
      document.addEventListener('pointerleave', onLeave)
    }
    start()

    return () => {
      stop()
      ro.disconnect()
      io.disconnect()
      document.removeEventListener('visibilitychange', onVis)
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerleave', onLeave)
    }
  }, [])

  return <canvas ref={ref} className={`particle-field ${className ?? ''}`} aria-hidden="true" />
}

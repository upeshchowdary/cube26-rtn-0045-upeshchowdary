// Level 3 gate and loader (Part H). Nothing here imports three.js: each scene is its own chunk,
// fetched with a dynamic import only when its section nears the viewport, and only when the
// device should run it. Everywhere else, and while a chunk is loading, the Level 2 version shows.
import { useEffect, useState, type RefObject } from 'react'
import { prefersReducedMotion } from '../../motion/scroll'

/** The desktop composition the 3D scenes reproduce exists only at this width and above. */
export const DESKTOP_3D = '(min-width: 1100px)'

let webgl: boolean | null = null

/** WebGL2 on a hardware renderer. Software renderers (SwiftShader, llvmpipe) count as unavailable. */
function hasHardwareWebGL(): boolean {
  if (webgl !== null) return webgl
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl2')
    if (!gl) return (webgl = false)
    const info = gl.getExtension('WEBGL_debug_renderer_info')
    const renderer = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : ''
    webgl = !/swiftshader|llvmpipe|software|basic render/i.test(renderer)
    gl.getExtension('WEBGL_lose_context')?.loseContext()
  } catch {
    webgl = false
  }
  return webgl
}

type NavigatorHints = Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } }

function isLowPower(): boolean {
  const nav = navigator as NavigatorHints
  if (nav.connection?.saveData) return true
  if (typeof nav.deviceMemory === 'number' && nav.deviceMemory < 4) return true
  return typeof nav.hardwareConcurrency === 'number' && nav.hardwareConcurrency < 4
}

/**
 * `?3d=off` always shows Level 2 (for side-by-side comparison); `?3d=on` skips the low-power and
 * software-renderer checks (for testing), but never reduced motion, width or missing WebGL.
 */
function override(): 'on' | 'off' | null {
  const v = new URLSearchParams(window.location.search).get('3d')
  return v === 'on' || v === 'off' ? v : null
}

export function canRender3D(): boolean {
  if (typeof window === 'undefined') return false
  const o = override()
  if (o === 'off') return false
  if (prefersReducedMotion()) return false
  if (!window.matchMedia(DESKTOP_3D).matches) return false
  if (o === 'on') return !!document.createElement('canvas').getContext('webgl2')
  return !isLowPower() && hasHardwareWebGL()
}

/**
 * True once `target` is within `margin` of the viewport (and the main thread is idle) on a device
 * that passes `canRender3D()`; the caller then renders its React.lazy scene. Turns false again
 * (back to Level 2) if the viewport narrows below the desktop width or reduced motion is switched on.
 */
export function useSceneGate(target: RefObject<HTMLElement | null>, margin = '600px 0px'): boolean {
  const [allowed, setAllowed] = useState(false)
  const [near, setNear] = useState(false)

  useEffect(() => {
    const wide = window.matchMedia(DESKTOP_3D)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setAllowed(canRender3D())
    update()
    wide.addEventListener('change', update)
    reduced.addEventListener('change', update)
    return () => {
      wide.removeEventListener('change', update)
      reduced.removeEventListener('change', update)
    }
  }, [])

  useEffect(() => {
    const el = target.current
    if (!allowed || !el || near) return
    let idle = 0
    const hasIdle = typeof window.requestIdleCallback === 'function'
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return
        io.disconnect()
        // Start the fetch when the main thread is free, so it never competes with first paint.
        const start = () => setNear(true)
        idle = hasIdle ? window.requestIdleCallback(start, { timeout: 1200 }) : window.setTimeout(start, 200)
      },
      { rootMargin: margin },
    )
    io.observe(el)
    return () => {
      io.disconnect()
      if (hasIdle) window.cancelIdleCallback(idle)
      else window.clearTimeout(idle)
    }
  }, [allowed, target, margin, near])

  return allowed && near
}

/** Pauses a scene when it leaves the viewport or the tab is hidden. */
export function useOnScreen(target: RefObject<HTMLElement | null>, margin = '120px 0px'): boolean {
  const [on, setOn] = useState(false)
  useEffect(() => {
    const el = target.current
    if (!el) return
    let inView = false
    const update = () => setOn(inView && document.visibilityState === 'visible')
    const io = new IntersectionObserver(
      (entries) => {
        inView = entries.some((e) => e.isIntersecting)
        update()
      },
      { rootMargin: margin },
    )
    io.observe(el)
    document.addEventListener('visibilitychange', update)
    return () => {
      io.disconnect()
      document.removeEventListener('visibilitychange', update)
    }
  }, [target, margin])
  return on
}

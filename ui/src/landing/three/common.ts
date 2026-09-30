// Shared by every Level 3 scene (Part H): texture loading with disposal, layout measurement, and the
// projection that lets a plane sit exactly where its Level 2 DOM element does. Only scene chunks
// import this file, so three.js never reaches the landing bundle.
import { useEffect, useRef, useState, type RefObject } from 'react'
import { useThree } from '@react-three/fiber'
import { ImageBitmapLoader, LinearMipmapLinearFilter, Mesh, MeshBasicMaterial, PlaneGeometry, Scene, SRGBColorSpace, Texture } from 'three'
import { three as T } from '../../motion/tokens'

/** Material settings every textured UI plane uses: unlit, colours exact, drawn in renderOrder. */
export const PLANE_MATERIAL = { transparent: true, depthWrite: false, depthTest: false, toneMapped: false } as const

export type SceneProps = {
  /** true once the first complete 3D frame is on screen; false when the scene unmounts. */
  onLive: (live: boolean) => void
}

/**
 * Loads the textures, uploads them (one per frame) before the first visible frame, and disposes
 * them on unmount.
 * Images are decoded off the main thread (createImageBitmap, via ImageBitmapLoader): uploading an
 * <img> makes the browser decode it synchronously inside texImage2D, which was a 117 ms task.
 * ImageBitmaps ignore `flipY` at upload, so the flip happens at decode instead.
 */
export function useTextures(urls: readonly string[]): Texture[] | null {
  const gl = useThree((s) => s.gl)
  const camera = useThree((s) => s.camera)
  const [textures, setTextures] = useState<Texture[] | null>(null)
  const key = urls.join('|')
  useEffect(() => {
    let alive = true
    const loader = new ImageBitmapLoader().setOptions({ imageOrientation: 'flipY', premultiplyAlpha: 'none' })
    const loaded: Texture[] = []
    const aniso = Math.min(8, gl.capabilities.getMaxAnisotropy())
    let raf = 0
    let proxy: Mesh<PlaneGeometry, MeshBasicMaterial> | null = null
    Promise.all(
      key.split('|').map((url) =>
        loader.loadAsync(url).then((bitmap: ImageBitmap) => {
          const t = new Texture(bitmap)
          t.flipY = false
          t.colorSpace = SRGBColorSpace
          t.minFilter = LinearMipmapLinearFilter
          t.anisotropy = aniso
          t.needsUpdate = true
          t.addEventListener('dispose', () => bitmap.close())
          loaded.push(t)
          return t
        }),
      ),
    )
      .then((ts) => {
        // Upload one texture per frame: all at once put every upload (and mip build) in the first
        // rendered frame, a 62 ms frame for the evidence stack's six.
        let i = 0
        const next = () => {
          if (!alive) return
          if (i < ts.length) {
            gl.initTexture(ts[i++])
            raf = requestAnimationFrame(next)
          } else {
            // Then compile the planes' shader without blocking (KHR_parallel_shader_compile), on a
            // proxy with the same material settings, so the same cached program. Compiling on
            // first draw instead made three.js wait for the driver: a 126 ms frame. The proxy
            // keeps the program referenced until unmount.
            proxy = new Mesh(new PlaneGeometry(), new MeshBasicMaterial({ map: ts[0], ...PLANE_MATERIAL }))
            const scene = new Scene().add(proxy)
            gl.compileAsync(scene, camera)
              .then(() => alive && setTextures(ts))
              .catch(() => undefined)
          }
        }
        raf = requestAnimationFrame(next)
      })
      .catch(() => undefined) // Level 2 stays visible
    return () => {
      alive = false
      cancelAnimationFrame(raf)
      loaded.forEach((t) => t.dispose())
      if (proxy) {
        proxy.geometry.dispose()
        proxy.material.dispose()
      }
    }
  }, [gl, camera, key])
  return textures
}

/**
 * Captures exist at 2x and 1.5x. The canvas renders at min(devicePixelRatio, 2), so up to 1.5 the
 * 1.5x set already covers every drawn pixel, with 56% of the pixels to decode, upload and mip.
 */
export function textureSet<T>(hi: T, lo: T): T {
  return Math.min(window.devicePixelRatio || 1, T.dprMax) > 1.5 ? hi : lo
}

/** Camera distance at which 1 world unit = `T.pxPerUnit` CSS px on the z = 0 plane. */
export function fitDistance(heightPx: number): number {
  return heightPx / T.pxPerUnit / 2 / Math.tan(((T.fov / 2) * Math.PI) / 180)
}

/** Canvas CSS px → world units on the plane at depth z, so it projects to the same screen spot. */
export function toWorld(px: number, py: number, z: number, W: number, H: number, D: number) {
  const k = (D - z) / D
  return { x: ((px - W / 2) / T.pxPerUnit) * k, y: (-(py - H / 2) / T.pxPerUnit) * k, k }
}

/**
 * Re-measures the Level 2 layout whenever `root` changes size (the observer also fires once on
 * observe). `measure` must read untransformed layout (offsetLeft/offsetTop), not client rects.
 */
export function useLayout<T>(root: RefObject<HTMLElement | null>, measure: (el: HTMLElement) => T): T | null {
  const [value, setValue] = useState<T | null>(null)
  const fn = useRef(measure)
  useEffect(() => {
    fn.current = measure
  })
  useEffect(() => {
    const el = root.current
    if (!el) return
    const ro = new ResizeObserver(() => setValue(fn.current(el)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [root])
  return value
}

/** Offset of `el` inside `root`, summed through offsetParents (ignores CSS transforms). */
export function offsetIn(el: HTMLElement, root: HTMLElement): { left: number; top: number } {
  let left = 0
  let top = 0
  let cur: HTMLElement | null = el
  while (cur && cur !== root) {
    left += cur.offsetLeft
    top += cur.offsetTop
    cur = cur.offsetParent as HTMLElement | null
  }
  return { left, top }
}

/** Calls onLive(true) once, on the first frame rendered with everything in place. */
export function useLiveSignal(onLive: (live: boolean) => void) {
  const done = useRef(false)
  return () => {
    if (done.current) return
    done.current = true
    requestAnimationFrame(() => onLive(true)) // after this frame is on screen
  }
}

export const damp = (current: number, target: number, factor: number) => current + (target - current) * factor

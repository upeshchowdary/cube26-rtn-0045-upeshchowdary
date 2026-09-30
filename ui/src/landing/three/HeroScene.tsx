// E1 hero, Level 3 (Part H): the three Level 2 cards as textured planes in a real perspective
// scene, with slight Z separation, damped pointer influence on the camera and the cards, a slow
// float that starts almost still, and the same scroll hand-off as Level 2 (up, smaller, tilted,
// fading). Lazy chunk: three.js and R3F load only here.
//
// Textures are captures of the Level 2 cards themselves (each card alone, with its CSS shadow, on a
// transparent background, at 2x), so the 3D planes carry exactly the sample data and labels the
// DOM shows. Regenerate them whenever the hero cards change. Planes are unlit (MeshBasicMaterial,
// no tone mapping) so the UI colours match the design tokens exactly; no post-processing.
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { LinearMipmapLinearFilter, SRGBColorSpace, TextureLoader, type Group, type Mesh, type MeshBasicMaterial, type Texture } from 'three'
import { pointerState } from '../../motion/pointer'
import { heroScroll, three as T } from '../../motion/tokens'
import { useOnScreen } from './support'
import evidenceUrl from './textures/hero-evidence.webp'
import recordUrl from './textures/hero-record.webp'
import decisionUrl from './textures/hero-decision.webp'

/** Transparent margin baked around each capture (CSS px), holding the card's shadow. */
const PAD = 72
/** How far the canvas extends past the rig on every side (CSS px), so shadows and motion never clip. */
export const HERO_MARGIN = 140

const CARDS = [
  { selector: '.hc-evidence', url: evidenceUrl, seed: 0.21, period: 3.4 },
  { selector: '.hc-record', url: recordUrl, seed: 0.57, period: 4.1 },
  { selector: '.hc-disposition', url: decisionUrl, seed: 0.83, period: 3.7 },
] as const

type Box = { cx: number; cy: number; w: number; h: number }

export type HeroSceneProps = {
  rig: RefObject<HTMLDivElement | null>
  /** 0 at rest → 1 when the hero has scrolled away (same trigger as the Level 2 hand-off). */
  progress: RefObject<number>
  /** true once the first complete 3D frame is on screen; false when the scene unmounts. */
  onLive: (live: boolean) => void
}

function useTextures(): Texture[] | null {
  const gl = useThree((s) => s.gl)
  const [textures, setTextures] = useState<Texture[] | null>(null)
  useEffect(() => {
    let alive = true
    const loader = new TextureLoader()
    const loaded: Texture[] = []
    const aniso = Math.min(8, gl.capabilities.getMaxAnisotropy())
    Promise.all(
      CARDS.map((c) =>
        loader.loadAsync(c.url).then((t) => {
          t.colorSpace = SRGBColorSpace
          t.minFilter = LinearMipmapLinearFilter
          t.anisotropy = aniso
          loaded.push(t)
          return t
        }),
      ),
    )
      .then((ts) => {
        if (!alive) return
        ts.forEach((t) => gl.initTexture(t)) // upload now, so the first visible frame is complete
        setTextures(ts)
      })
      .catch(() => undefined) // Level 2 stays visible
    return () => {
      alive = false
      loaded.forEach((t) => t.dispose())
    }
  }, [gl])
  return textures
}

/** Card boxes in canvas CSS px, measured from the (untransformed) Level 2 layout. */
function measure(rig: HTMLDivElement): Box[] {
  return CARDS.map((c) => {
    const layer = rig.querySelector<HTMLElement>(c.selector)
    const card = layer?.querySelector<HTMLElement>('.hc-card')
    if (!layer || !card) return { cx: 0, cy: 0, w: 0, h: 0 }
    const w = card.offsetWidth
    const h = card.offsetHeight
    return {
      cx: HERO_MARGIN + layer.offsetLeft + card.offsetLeft + w / 2,
      cy: HERO_MARGIN + layer.offsetTop + card.offsetTop + h / 2,
      w,
      h,
    }
  })
}

function Cards({ rig, progress, onLive }: HeroSceneProps) {
  const textures = useTextures()
  const size = useThree((s) => s.size)
  const camera = useThree((s) => s.camera)
  const pivot = useRef<Group>(null)
  const meshes = useRef<(Mesh | null)[]>([])
  const [boxes, setBoxes] = useState<Box[] | null>(null)
  const t0 = useRef(0)
  const ready = useRef(false)

  // Measure the Level 2 layout now and whenever the rig changes size (the observer fires on observe).
  useEffect(() => {
    const el = rig.current
    if (!el) return
    const ro = new ResizeObserver(() => setBoxes(measure(el)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [rig])

  const W = size.width
  const H = size.height
  const D = H / T.pxPerUnit / 2 / Math.tan(((T.fov / 2) * Math.PI) / 180)
  // The rig's transform-origin (50% 20%) is the pivot for the scroll tilt, as in Level 2.
  const rigH = H - HERO_MARGIN * 2
  const pivotY = -(HERO_MARGIN + rigH * 0.2 - H / 2) / T.pxPerUnit

  const layout = useMemo(
    () =>
      boxes?.map((b, i) => {
        // Scale each plane by its depth so that, at rest, it projects to exactly its DOM size.
        const k = (D - T.layerZ[i]) / D
        return {
          x: ((b.cx - W / 2) / T.pxPerUnit) * k,
          y: (-(b.cy - H / 2) / T.pxPerUnit) * k - pivotY,
          z: T.layerZ[i],
          w: ((b.w + PAD * 2) / T.pxPerUnit) * k,
          h: ((b.h + PAD * 2) / T.pxPerUnit) * k,
        }
      }) ?? null,
    [boxes, W, H, D, pivotY],
  )

  useFrame((state) => {
    if (!layout || !textures || !pivot.current) return
    const now = state.clock.elapsedTime
    if (!t0.current) t0.current = now || 0.0001
    const t = now - t0.current
    const ramp = Math.min(1, t / T.settle)
    const settle = ramp * ramp * (3 - 2 * ramp) // starts almost still
    const px = pointerState.x
    const py = pointerState.y

    // Camera: slight orbit against the pointer, so nearer cards travel further with it (as in Level 2).
    const ry = -px * T.cameraRot
    const rx = py * T.cameraRot
    camera.position.set(D * Math.sin(ry) * Math.cos(rx), D * Math.sin(rx), D * Math.cos(ry) * Math.cos(rx))
    camera.lookAt(0, 0, 0)

    // Scroll hand-off: up, slightly smaller, tilted back and fading (heroScroll tokens).
    const p = Math.min(1, Math.max(0, progress.current ?? 0))
    const g = pivot.current
    g.position.set(0, pivotY + (-heroScroll.y / T.pxPerUnit) * p, 0)
    g.rotation.x = -((heroScroll.rotateX * Math.PI) / 180) * p
    g.scale.setScalar(1 + (heroScroll.scale - 1) * p)
    const opacity = 1 + (heroScroll.opacity - 1) * p

    layout.forEach((l, i) => {
      const m = meshes.current[i]
      if (!m) return
      const c = CARDS[i]
      const f = Math.sin((t / c.period) * Math.PI + c.seed * Math.PI * 2) * settle
      m.position.set(l.x, l.y + (f * T.floatY[i]) / T.pxPerUnit, l.z)
      m.rotation.set(py * T.cardRot[i], px * T.cardRot[i], f * T.floatRoll)
      ;(m.material as MeshBasicMaterial).opacity = opacity
    })

    if (!ready.current) {
      ready.current = true
      requestAnimationFrame(() => onLive(true)) // after this frame is on screen
    }
  })

  if (!layout || !textures) return null
  return (
    <group ref={pivot}>
      {layout.map((l, i) => (
        <mesh
          key={CARDS[i].selector}
          ref={(m) => {
            meshes.current[i] = m
          }}
          position={[l.x, l.y, l.z]}
          renderOrder={i}
        >
          <planeGeometry args={[l.w, l.h]} />
          <meshBasicMaterial map={textures[i]} transparent depthWrite={false} depthTest={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  )
}

export default function HeroScene(props: HeroSceneProps) {
  const host = useRef<HTMLDivElement>(null)
  const onScreen = useOnScreen(host)
  const { onLive } = props
  useEffect(() => () => onLive(false), [onLive])
  return (
    <div ref={host} className="hero-3d" aria-hidden="true">
      <Canvas
        frameloop={onScreen ? 'always' : 'never'}
        dpr={[1, T.dprMax]}
        flat
        gl={{ antialias: false, alpha: true, powerPreference: 'default' }}
        camera={{ fov: T.fov, near: 0.1, far: 100, position: [0, 0, 10] }}
      >
        <Cards {...props} />
      </Canvas>
    </div>
  )
}

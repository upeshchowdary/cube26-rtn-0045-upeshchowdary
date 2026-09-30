// E1 hero, Level 3 (Part H): the three Level 2 cards as textured planes in a real perspective
// scene, with slight Z separation, damped pointer influence on the camera and the cards, a slow
// float that starts almost still, and the same scroll hand-off as Level 2 (up, smaller, tilted,
// fading). Lazy chunk: three.js and R3F load only here.
//
// Textures are captures of the Level 2 cards themselves (each card alone, with its CSS shadow, on a
// transparent background, at 2x and 1.5x; see `textureSet`), so the 3D planes carry exactly the
// sample data and labels the DOM shows. Regenerate them whenever the hero cards change. Planes are
// unlit (MeshBasicMaterial, no tone mapping) so the UI colours match the design tokens exactly; no
// post-processing.
import { useMemo, useRef, type RefObject } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import type { Group, Mesh, MeshBasicMaterial } from 'three'
import { pointerState } from '../../motion/pointer'
import { heroScroll, three as T } from '../../motion/tokens'
import { fitDistance, toWorld, useLayout, useLiveSignal, useTextures, PLANE_MATERIAL, textureSet, type SceneProps } from './common'
import { SceneCanvas } from './SceneCanvas'
import evidenceUrl from './textures/hero-evidence.webp'
import recordUrl from './textures/hero-record.webp'
import decisionUrl from './textures/hero-decision.webp'
import evidenceLo from './textures/hero-evidence-1.5x.webp'
import recordLo from './textures/hero-record-1.5x.webp'
import decisionLo from './textures/hero-decision-1.5x.webp'

/** Transparent margin baked around each capture (CSS px), holding the card's shadow. */
const PAD = 72
/** How far the canvas extends past the rig on every side (CSS px); matches `.hero-3d` in landing.css. */
const MARGIN = 140

const CARDS = [
  { selector: '.hc-evidence', seed: 0.21, period: 3.4 },
  { selector: '.hc-record', seed: 0.57, period: 4.1 },
  { selector: '.hc-disposition', seed: 0.83, period: 3.7 },
] as const
const URLS = textureSet([evidenceUrl, recordUrl, decisionUrl], [evidenceLo, recordLo, decisionLo])

type Box = { cx: number; cy: number; w: number; h: number }

export type HeroSceneProps = SceneProps & {
  rig: RefObject<HTMLDivElement | null>
  /** 0 at rest → 1 when the hero has scrolled away (same trigger as the Level 2 hand-off). */
  progress: RefObject<number>
}

/** Card boxes in canvas CSS px, measured from the (untransformed) Level 2 layout. */
function measure(rig: HTMLElement): Box[] {
  return CARDS.map((c) => {
    const layer = rig.querySelector<HTMLElement>(c.selector)
    const card = layer?.querySelector<HTMLElement>('.hc-card')
    if (!layer || !card) return { cx: 0, cy: 0, w: 0, h: 0 }
    const w = card.offsetWidth
    const h = card.offsetHeight
    return { cx: MARGIN + layer.offsetLeft + card.offsetLeft + w / 2, cy: MARGIN + layer.offsetTop + card.offsetTop + h / 2, w, h }
  })
}

function Cards({ rig, progress, onLive }: HeroSceneProps) {
  const textures = useTextures(URLS)
  const boxes = useLayout(rig, measure)
  const size = useThree((s) => s.size)
  const camera = useThree((s) => s.camera)
  const pivot = useRef<Group>(null)
  const meshes = useRef<(Mesh | null)[]>([])
  const t0 = useRef(0)
  const live = useLiveSignal(onLive)

  const W = size.width
  const H = size.height
  const D = fitDistance(H)
  // The rig's transform-origin (50% 20%) is the pivot for the scroll tilt, as in Level 2.
  const pivotY = -(MARGIN + (H - MARGIN * 2) * 0.2 - H / 2) / T.pxPerUnit

  const layout = useMemo(
    () =>
      boxes?.map((b, i) => {
        // Scaled by depth so that, at rest, each plane projects to exactly its DOM size.
        const p = toWorld(b.cx, b.cy, T.layerZ[i], W, H, D)
        return { x: p.x, y: p.y - pivotY, z: T.layerZ[i], w: ((b.w + PAD * 2) / T.pxPerUnit) * p.k, h: ((b.h + PAD * 2) / T.pxPerUnit) * p.k }
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
    live()
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
          <meshBasicMaterial map={textures[i]} {...PLANE_MATERIAL} />
        </mesh>
      ))}
    </group>
  )
}

export default function HeroScene(props: HeroSceneProps) {
  return (
    <SceneCanvas className="hero-3d" onLive={props.onLive}>
      <Cards {...props} />
    </SceneCanvas>
  )
}

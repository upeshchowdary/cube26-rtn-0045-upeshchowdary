// E6 evidence stack, Level 3 (Part H, candidate 2): the three photo cards as planes that fan out
// in real perspective as the section scrolls (the Level 2 fan, from `evidenceFan`), each side card
// turning slightly toward the centre, and the active photo coming forward past the front of the fan
// while its highlight cross-fades in. Pointer influence is a slight camera orbit. Lazy chunk.
//
// Textures are captures of the Level 2 photo cards, idle and active (blue border and shadow), so the
// planes show exactly the DOM content: the illustrations and "Photo n of 3" captions.
import { useRef, type RefObject } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import type { Mesh, MeshBasicMaterial } from 'three'
import { pointerState } from '../../motion/pointer'
import { evidenceFan as F, three as T } from '../../motion/tokens'
import { damp, fitDistance, offsetIn, toWorld, useLayout, useLiveSignal, useTextures, PLANE_MATERIAL, textureSet, type SceneProps } from './common'
import { SceneCanvas } from './SceneCanvas'
import idle1 from './textures/ev-photo-1.webp'
import idle2 from './textures/ev-photo-2.webp'
import idle3 from './textures/ev-photo-3.webp'
import active1 from './textures/ev-photo-1-active.webp'
import active2 from './textures/ev-photo-2-active.webp'
import active3 from './textures/ev-photo-3-active.webp'
import idle1Lo from './textures/ev-photo-1-1.5x.webp'
import idle2Lo from './textures/ev-photo-2-1.5x.webp'
import idle3Lo from './textures/ev-photo-3-1.5x.webp'
import active1Lo from './textures/ev-photo-1-active-1.5x.webp'
import active2Lo from './textures/ev-photo-2-active-1.5x.webp'
import active3Lo from './textures/ev-photo-3-active-1.5x.webp'

/** Transparent margin baked around each capture (CSS px), holding the card's shadow. */
const PAD = 96
/** How far the canvas extends past the stack on every side (CSS px): fan travel + shadow + lift. */
const MARGIN = 180
const URLS = textureSet(
  [idle1, idle2, idle3, active1, active2, active3],
  [idle1Lo, idle2Lo, idle3Lo, active1Lo, active2Lo, active3Lo],
)
const CAMERA_ROT = T.cameraRot * 0.75
const CARD_ROT = T.cardRot[0]

export type EvidenceSceneProps = SceneProps & {
  /** `.ev-stack-wrap`: positioned; holds the Level 2 stack and this canvas. */
  wrap: RefObject<HTMLDivElement | null>
  /** The Level 2 timeline's progress (0 → 1 over the section). */
  progress: RefObject<number>
}

type Box = { left: number; top: number; w: number; h: number; cx: number; cy: number; pw: number; ph: number }

function measure(wrap: HTMLElement): Box | null {
  const stack = wrap.querySelector<HTMLElement>('.ev-stack')
  const photo = stack?.querySelector<HTMLElement>('.ev-photo')
  if (!stack || !photo) return null
  const o = offsetIn(stack, wrap)
  return {
    left: o.left - MARGIN,
    top: o.top - MARGIN,
    w: stack.offsetWidth + MARGIN * 2,
    h: stack.offsetHeight + MARGIN * 2,
    cx: MARGIN + photo.offsetLeft + photo.offsetWidth / 2,
    cy: MARGIN + photo.offsetTop + photo.offsetHeight / 2,
    pw: photo.offsetWidth,
    ph: photo.offsetHeight,
  }
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t

function Photos({ box, progress, onLive }: { box: Box } & Omit<EvidenceSceneProps, 'wrap'>) {
  const textures = useTextures(URLS)
  const size = useThree((s) => s.size)
  const camera = useThree((s) => s.camera)
  const base = useRef<(Mesh | null)[]>([])
  const glow = useRef<(Mesh | null)[]>([])
  const lift = useRef([1, 0, 0])
  const live = useLiveSignal(onLive)

  // Photos sit on the z = 0 plane at rest, as in Level 2 (its CSS perspective, 1200 px, is close to
  // this camera's distance, so the fan's depth reads the same).
  const D = fitDistance(size.height)
  const origin = toWorld(box.cx, box.cy, 0, size.width, size.height, D)
  const w = (box.pw + PAD * 2) / T.pxPerUnit
  const h = (box.ph + PAD * 2) / T.pxPerUnit

  useFrame(() => {
    if (!textures) return
    const p = Math.min(1, Math.max(0, progress.current ?? 0))
    const t = Math.min(1, p / 0.5) // the fan plays over the first half, then holds
    const active = Math.min(2, Math.floor(p * 3))
    const px = pointerState.x
    const py = pointerState.y

    const ry = -px * CAMERA_ROT
    const rx = py * CAMERA_ROT
    camera.position.set(D * Math.sin(ry) * Math.cos(rx), D * Math.sin(rx), D * Math.cos(ry) * Math.cos(rx))
    camera.lookAt(0, 0, 0)

    // Fan depth per photo, and the front of the fan: the active photo comes forward past it.
    const fanZ = [0, 1, 2].map((i) => lerp(F.from(i).z, F.out[i].z, t) / T.pxPerUnit)
    const front = Math.max(...fanZ)
    const zs: number[] = []
    for (let i = 0; i < 3; i++) {
      const a = F.from(i)
      const b = F.out[i]
      lift.current[i] = damp(lift.current[i], i === active ? 1 : 0, F.activeDamp)
      const l = lift.current[i]
      const x = origin.x + lerp(a.x, b.x, t) / T.pxPerUnit
      const y = origin.y - lerp(a.y, b.y, t) / T.pxPerUnit
      const z = fanZ[i] + l * (front - fanZ[i] + F.activeLift)
      zs.push(z)
      for (const m of [base.current[i], glow.current[i]]) {
        if (!m) continue
        m.position.set(x, y, z)
        m.rotation.set(py * CARD_ROT, F.yaw[i] * t + px * CARD_ROT, -((lerp(a.rotate, b.rotate, t) * Math.PI) / 180))
      }
      const g = glow.current[i]
      if (g) (g.material as MeshBasicMaterial).opacity = l
    }
    // Back to front by depth: planes are transparent and don't write depth.
    const order = [0, 1, 2].sort((a, b) => zs[a] - zs[b])
    order.forEach((i, rank) => {
      if (base.current[i]) base.current[i]!.renderOrder = rank * 2
      if (glow.current[i]) glow.current[i]!.renderOrder = rank * 2 + 1
    })
    live()
  })

  if (!textures) return null
  return (
    <>
      {[0, 1, 2].map((i) => (
        <group key={i}>
          <mesh ref={(m) => void (base.current[i] = m)}>
            <planeGeometry args={[w, h]} />
            <meshBasicMaterial map={textures[i]} {...PLANE_MATERIAL} />
          </mesh>
          <mesh ref={(m) => void (glow.current[i] = m)}>
            <planeGeometry args={[w, h]} />
            <meshBasicMaterial map={textures[i + 3]} {...PLANE_MATERIAL} opacity={0} />
          </mesh>
        </group>
      ))}
    </>
  )
}

export default function EvidenceScene({ wrap, progress, onLive }: EvidenceSceneProps) {
  const box = useLayout(wrap, measure)
  if (!box) return null
  return (
    <SceneCanvas className="ev-3d" style={{ left: box.left, top: box.top, width: box.w, height: box.h }} onLive={onLive}>
      <Photos box={box} progress={progress} onLive={onLive} />
    </SceneCanvas>
  )
}

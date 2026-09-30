// E8 decision stack, Level 3 (Part H): six evidence-backed layers in real perspective.
// The DOM stack remains underneath as the accessible and low-power fallback.
import { useEffect, useRef, useState, type RefObject } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Camera, CanvasTexture, LinearMipmapLinearFilter, Mesh, MeshBasicMaterial, PlaneGeometry, Scene, SRGBColorSpace, WebGLRenderer, type Texture } from 'three'
import { condition, recommendation } from '../sample'
import { pointerState } from '../../motion/pointer'
import { three as T, decisionStack as D } from '../../motion/tokens'
import { damp, fitDistance, offsetIn, toWorld, useLayout, useLiveSignal, PLANE_MATERIAL, type SceneProps } from './common'
import { SceneCanvas } from './SceneCanvas'

type Box = { left: number; top: number; width: number; height: number; cx: number; cy: number; layerTops: number[]; layerHeights: number[] }

const LAYERS = [
  ['Evidence', '3 photos - references checked'],
  ['Identity', 'Product identity: Yes - records match'],
  ['Condition', `${condition.grade} - USB cable missing`],
  ['Recommendation', `${recommendation.route} - ${recommendation.rule}`],
  ['Operator review', 'Accept or override, with reason'],
  ['Final disposition', `${recommendation.route} - confirmed by operator`],
] as const

function createCardTexture(label: string, value: string, index: number, widthPx: number, heightPx: number): Texture {
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(widthPx * 2))
  canvas.height = Math.max(1, Math.round(heightPx * 2))
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Decision card canvas unavailable')
  context.scale(canvas.width / 900, canvas.height / 150)
  const accent = index === 4 ? '#2563eb' : index === 5 ? '#15803d' : '#64748b'
  const background = index === 4 ? '#eff6ff' : index === 5 ? '#f0fdf4' : '#ffffff'
  context.fillStyle = background
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.strokeStyle = accent
  context.lineWidth = index > 3 ? 3 : 2
  context.strokeRect(2, 2, canvas.width - 4, canvas.height - 4)
  context.fillStyle = accent
  context.fillRect(24, 28, 5, 94)
  context.fillStyle = '#64748b'
  context.font = '600 18px Arial, sans-serif'
  context.fillText(label.toUpperCase(), 52, 58)
  context.fillStyle = '#0f172a'
  context.font = '700 26px Arial, sans-serif'
  context.fillText(value, 52, 98)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  texture.minFilter = LinearMipmapLinearFilter
  texture.needsUpdate = true
  return texture
}

function useDecisionTextures(gl: WebGLRenderer, camera: Camera, layerHeights: number[], layerWidth: number) {
  const [textures, setTextures] = useState<Texture[] | null>(null)
  useEffect(() => {
    const created = LAYERS.map(([label, value], index) => createCardTexture(label, value, index, layerWidth, layerHeights[index]))
    created.forEach((texture) => gl.initTexture(texture))
    const proxy = new Mesh(new PlaneGeometry(), new MeshBasicMaterial({ map: created[0], transparent: true, depthWrite: false, depthTest: false }))
    const scene = new Scene().add(proxy)
    let active = true
    gl.compileAsync(scene, camera).then(() => active && setTextures(created)).catch(() => undefined)
    return () => {
      active = false
      created.forEach((texture) => texture.dispose())
      proxy.geometry.dispose()
      proxy.material.dispose()
    }
  }, [camera, gl, layerHeights, layerWidth])
  return textures
}

function measure(wrap: HTMLElement): Box | null {
  const stack = wrap.querySelector<HTMLElement>('.ds-stack')
  if (!stack) return null
  const offset = offsetIn(stack, wrap)
  const layers = [...wrap.querySelectorAll<HTMLElement>('.ds-layer')]
  return {
    left: offset.left - D.margin,
    top: offset.top - D.margin,
    width: stack.offsetWidth + D.margin * 2,
    height: stack.offsetHeight + D.margin * 2,
    cx: D.margin + stack.offsetWidth / 2,
    cy: D.margin + stack.offsetHeight / 2,
    layerTops: layers.map((layer) => layer.offsetTop),
    layerHeights: layers.map((layer) => layer.offsetHeight),
  }
}

export type DecisionSceneProps = SceneProps & {
  wrap: RefObject<HTMLDivElement | null>
  progress: RefObject<number>
}

function Layers({ box, progress, onLive }: { box: Box } & Omit<DecisionSceneProps, 'wrap'>) {
  const gl = useThree((state) => state.gl)
  const camera = useThree((state) => state.camera)
  const layerWidth = box.width - D.margin * 2
  const textures = useDecisionTextures(gl, camera, box.layerHeights, layerWidth)
  const size = useThree((state) => state.size)
  const meshes = useRef<(Mesh | null)[]>([])
  const offsets = useRef<number[]>(LAYERS.map(() => 0))
  const live = useLiveSignal(onLive)
  const distance = fitDistance(size.height)

  useFrame((state) => {
    if (!textures) return
    const p = Math.max(0, Math.min(1, progress.current ?? 0))
    const pointerX = pointerState.x
    const pointerY = pointerState.y
    const orbitY = -pointerX * T.cameraRot * 0.6
    const orbitX = pointerY * T.cameraRot * 0.6
    camera.position.set(distance * Math.sin(orbitY), distance * Math.sin(orbitX), distance * Math.cos(orbitY) * Math.cos(orbitX))
    camera.lookAt(0, 0, 0)
    LAYERS.forEach((_, index) => {
      const target = p * (index * D.spread) - (1 - p) * index * D.depth
      offsets.current[index] = damp(offsets.current[index], target, D.damping)
      const mesh = meshes.current[index]
      if (!mesh) return
      const layerCenterY = D.margin + box.layerTops[index] + box.layerHeights[index] / 2
      const layerOrigin = toWorld(box.cx, layerCenterY, 0, size.width, size.height, distance)
      const y = layerOrigin.y - offsets.current[index] / T.pxPerUnit
      const z = D.layerZ[index] + offsets.current[index] / T.pxPerUnit
      mesh.position.set(layerOrigin.x, y, z)
      mesh.rotation.set(pointerY * T.cardRot[0], pointerX * T.cardRot[0], 0)
      mesh.renderOrder = index
    })
    live()
    void state
  })

  if (!textures) return null
  return (
    <>
      {textures.map((texture, index) => (
        <mesh key={index} ref={(mesh) => void (meshes.current[index] = mesh)}>
          <planeGeometry args={[layerWidth / T.pxPerUnit, box.layerHeights[index] / T.pxPerUnit]} />
          <meshBasicMaterial map={texture} {...PLANE_MATERIAL} />
        </mesh>
      ))}
    </>
  )
}

export default function DecisionScene({ wrap, progress, onLive }: DecisionSceneProps) {
  const box = useLayout(wrap, measure)
  if (!box) return null
  return (
    <SceneCanvas className="decision-3d" style={{ left: box.left, top: box.top, width: box.width, height: box.height }} onLive={onLive}>
      <Layers box={box} progress={progress} onLive={onLive} />
    </SceneCanvas>
  )
}
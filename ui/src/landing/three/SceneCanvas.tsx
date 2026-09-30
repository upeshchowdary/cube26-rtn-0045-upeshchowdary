// The one canvas setup every Level 3 scene uses (Part H). Only scene chunks import this file.
import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { three as T } from '../../motion/tokens'
import type { SceneProps } from './common'
import { useOnScreen } from './support'

/**
 * The canvas every scene uses: transparent, DPR capped at 2, no tone mapping, render loop running
 * only while the host is on screen and the tab is visible. The host is aria-hidden: the Level 2
 * DOM underneath keeps the content for assistive technology.
 */
export function SceneCanvas({
  className,
  style,
  onLive,
  children,
}: SceneProps & { className: string; style?: CSSProperties; children: ReactNode }) {
  const host = useRef<HTMLDivElement>(null)
  const onScreen = useOnScreen(host)
  useEffect(() => () => onLive(false), [onLive])
  return (
    <div ref={host} className={`lp-3d ${className}`} style={style} aria-hidden="true">
      <Canvas
        frameloop={onScreen ? 'always' : 'never'}
        dpr={[1, T.dprMax]}
        flat
        gl={{ antialias: false, alpha: true, powerPreference: 'default' }}
        camera={{ fov: T.fov, near: 0.1, far: 100, position: [0, 0, 10] }}
        // R3F measures its box with a scroll-debounced ResizeObserver by default (50 ms, restarted
        // by every scroll event), so a scene mounted mid-scroll under Lenis got no size, and so
        // never rendered or loaded, until the visitor stopped scrolling. The scenes use no R3F
        // pointer events, so scroll-tracked bounds aren't needed: measure on resize only, at once.
        resize={{ scroll: false, debounce: 0 }}
      >
        {children}
      </Canvas>
    </div>
  )
}

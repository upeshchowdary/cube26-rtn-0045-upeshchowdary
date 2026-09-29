import { useEffect, useRef } from 'react'

interface AmbientCanvasProps {
  intensity?: number
  showParticles?: boolean
  className?: string
}

export default function AmbientCanvas({
  intensity = 0.8,
  showParticles = true,
  className = '',
}: AmbientCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !showParticles) return

    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return

    let animId: number
    let width = 0
    let height = 0

    const handleResize = () => {
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = width
      canvas.height = height
    }

    handleResize()
    window.addEventListener('resize', handleResize)

    // Ambient floating particles (lightweight: < 0.01ms per frame)
    const particleCount = 26
    const particles = Array.from({ length: particleCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      size: 0.8 + Math.random() * 1.6,
      speedX: (Math.random() - 0.5) * 0.16,
      speedY: -0.12 - Math.random() * 0.22, // gentle upward drift
      alpha: 0.15 + Math.random() * 0.35,
      hue: Math.random() > 0.6 ? 152 : Math.random() > 0.3 ? 174 : 204, // emerald, teal, blue
    }))

    // Mouse movement subtle parallax
    let targetX = 0
    let targetY = 0
    let currentX = 0
    let currentY = 0

    const handleMouseMove = (e: MouseEvent) => {
      targetX = (e.clientX / (width || 1) - 0.5) * 18
      targetY = (e.clientY / (height || 1) - 0.5) * 18
    }
    window.addEventListener('mousemove', handleMouseMove, { passive: true })

    const render = () => {
      if (document.hidden) {
        animId = requestAnimationFrame(render)
        return
      }

      // Smooth mouse follow
      currentX += (targetX - currentX) * 0.04
      currentY += (targetY - currentY) * 0.04
      if (containerRef.current) {
        containerRef.current.style.transform = `translate3d(${currentX.toFixed(1)}px, ${currentY.toFixed(1)}px, 0)`
      }

      ctx.clearRect(0, 0, width, height)

      // Draw subtle luminous ambient motes (zero gradient fills for 240 FPS)
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        p.x += p.speedX
        p.y += p.speedY

        if (p.y < -5) {
          p.y = height + 5
          p.x = Math.random() * width
        }
        if (p.x < 0) p.x = width
        if (p.x > width) p.x = 0

        ctx.fillStyle = `hsla(${p.hue}, 68%, 62%, ${p.alpha * intensity})`
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx.fill()
      }

      animId = requestAnimationFrame(render)
    }

    animId = requestAnimationFrame(render)

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('mousemove', handleMouseMove)
    }
  }, [intensity, showParticles])

  return (
    <div
      ref={containerRef}
      className={`ambient-background-layer ${className}`}
      style={{
        position: 'fixed',
        inset: '-30px',
        pointerEvents: 'none',
        zIndex: 0,
        overflow: 'hidden',
        willChange: 'transform',
      }}
    >
      {/* GPU Hardware-Composited CSS Aurora Meshes (Zero CPU fill overhead) */}
      <div
        className="ambient-orb ambient-orb-1"
        style={{ opacity: 0.45 * intensity }}
      />
      <div
        className="ambient-orb ambient-orb-2"
        style={{ opacity: 0.38 * intensity }}
      />
      <div
        className="ambient-orb ambient-orb-3"
        style={{ opacity: 0.3 * intensity }}
      />

      {showParticles && (
        <canvas
          ref={canvasRef}
          className="ambient-motion-canvas"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
          }}
        />
      )}
    </div>
  )
}


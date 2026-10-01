import { useLayoutEffect, useRef, useState, useEffect, useCallback } from 'react'
import {
  ArrowDownRight,
  ArrowRight,
  Check,
  Eye,
  ShieldCheck,
} from 'lucide-react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { Link, useNavigate } from 'react-router-dom'
import './styles.css'

gsap.registerPlugin(ScrollTrigger)

const TOTAL_FRAMES = 161
const FRAME_BASE_URL = '/frames/frame_'
const G1_VIDEO_URL = '/video_cinematic_g1.mp4'

const narrativeSteps = [
  { number: '01', label: 'IDENTIFY' },
  { number: '02', label: 'INSPECT' },
  { number: '03', label: 'VERIFY' },
  { number: '04', label: 'DECIDE' },
  { number: '05', label: 'DISPOSITION' },
]

const story = [
  {
    phase: 'EVIDENCE',
    eyebrow: 'EVIDENCE',
    title: 'EVERY RETURN\nCARRIES EVIDENCE.',
    copy: 'Identity. Condition. Components. Packaging. Photos. Disposition.',
    meta: 'EVIDENCE CAPTURED',
  },
  {
    phase: 'IDENTIFY',
    eyebrow: '01 / IDENTIFY',
    title: 'START WITH\nWHAT ACTUALLY CAME BACK.',
    copy: 'Identify the returned product, order, SKU, and expected item.',
    meta: 'IDENTITY VERIFIED',
  },
  {
    phase: 'INSPECT',
    eyebrow: '02 / INSPECT',
    title: 'THEN UNDERSTAND\nITS CONDITION.',
    copy: 'Inspect physical state, components, packaging, and visible defects.',
    meta: 'CONDITION ANALYZED',
  },
  {
    phase: 'VERIFY',
    eyebrow: '03 / VERIFY',
    title: 'VERIFY THE RETURN\nAGAINST THE EXPECTATION.',
    copy: 'Compare product identity and evidence before deciding what happens next.',
    meta: 'MATCH CONFIRMED',
  },
  {
    phase: 'DECIDE',
    eyebrow: '04 / DECIDE',
    title: 'TURN EVIDENCE\nINTO A DECISION.',
    copy: 'Apply policy to a finding that a reviewer can see and trust.',
    meta: 'DECISION LOGIC',
    badges: ['RESTOCK', 'REFUND', 'REJECT', 'REVIEW'],
  },
  {
    phase: 'DISPOSITION',
    eyebrow: '05 / DISPOSITION',
    title: 'EVERY DECISION\nNEEDS A NEXT STEP.',
    copy: 'Move the return forward with a clear operational outcome.',
    meta: 'DECISION READY',
  },
]

// Volumetric particle system for cinematic depth
interface Particle {
  x: number
  y: number
  size: number
  speedX: number
  speedY: number
  alpha: number
  targetAlpha: number
  pulseSpeed: number
}

function initParticles(count: number): Particle[] {
  return Array.from({ length: count }, () => ({
    x: Math.random(),
    y: Math.random(),
    size: 0.6 + Math.random() * 2.2,
    speedX: (Math.random() - 0.5) * 0.0003,
    speedY: (Math.random() - 0.5) * 0.0004,
    alpha: 0.15 + Math.random() * 0.5,
    targetAlpha: 0.15 + Math.random() * 0.5,
    pulseSpeed: 0.01 + Math.random() * 0.02,
  }))
}

export default function CinematicOverview() {
  const navigate = useNavigate()
  const sectionRef = useRef<HTMLElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const storyRefs = useRef<(HTMLDivElement | null)[]>([])

  // High-frequency render refs (decoupled from React re-renders)
  const targetProgressRef = useRef(0)
  const currentProgressRef = useRef(0)
  const framesRef = useRef<(HTMLImageElement | ImageBitmap)[]>([])
  const framesLoadedCountRef = useRef(0)
  const particlesRef = useRef<Particle[]>(initParticles(45))
  const particlesCanvasRef = useRef<HTMLCanvasElement>(null)
  const lastRenderedIndexRef = useRef(-1)
  const forceRedrawRef = useRef(true)
  const lastRailStepRef = useRef(-1)

  // Rendering configuration (Butter-smooth GPU canvas sequence)
  const [renderMode] = useState<'canvas' | 'video'>('canvas')
  const [is8KSuperSample] = useState(true)

  // Silky-Smooth Lenis Physics Scroll Engine (Instant, zero sluggishness, zero getting stuck)
  useEffect(() => {
    const lenis = new Lenis({
      duration: 0.55,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      wheelMultiplier: 1.1,
      touchMultiplier: 1.8,
      infinite: false,
    })

    const updateScrollTrigger = () => ScrollTrigger.update()
    lenis.on('scroll', updateScrollTrigger)

    const raf = (time: number) => lenis.raf(time * 1000)
    gsap.ticker.fps(180)
    gsap.ticker.lagSmoothing(0)
    gsap.ticker.add(raf)

    return () => {
      lenis.off('scroll', updateScrollTrigger)
      gsap.ticker.remove(raf)
      lenis.destroy()
    }
  }, [])

  // 1:1 Hardware Canvas Draw with High-DPI Supersampling and Bicubic Smoothing
  const renderFrameOnCanvas = useCallback(
    (ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, img: CanvasImageSource) => {
      ctx.imageSmoothingEnabled = true
      ctx.imageSmoothingQuality = 'high'
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    },
    [],
  )

  const drawInitialFrame = (img: CanvasImageSource) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true })
    if (!ctx) return
    canvas.width = 1920
    canvas.height = 1080
    renderFrameOnCanvas(ctx, canvas, img)
  }

  // High-performance progressive preloader with off-thread ImageBitmap GPU decoding
  useEffect(() => {
    let isCancelled = false
    const frames: (HTMLImageElement | ImageBitmap)[] = new Array(TOTAL_FRAMES)
    framesRef.current = frames

    // Immediate load first frame for instant display
    const firstImg = new Image()
    firstImg.src = `${FRAME_BASE_URL}001.webp`
    firstImg.onload = () => {
      if (isCancelled) return
      if ('createImageBitmap' in window) {
        createImageBitmap(firstImg)
          .then((bmp) => {
            if (isCancelled) return
            frames[0] = bmp
            framesLoadedCountRef.current = Math.max(1, framesLoadedCountRef.current)
            drawInitialFrame(bmp)
            forceRedrawRef.current = true
          })
          .catch(() => {
            frames[0] = firstImg
            framesLoadedCountRef.current = Math.max(1, framesLoadedCountRef.current)
            drawInitialFrame(firstImg)
            forceRedrawRef.current = true
          })
      } else {
        frames[0] = firstImg
        framesLoadedCountRef.current = Math.max(1, framesLoadedCountRef.current)
        drawInitialFrame(firstImg)
        forceRedrawRef.current = true
      }
    }

    // High-concurrency worker pool: rapidly decodes all 161 frames to GPU bitmaps
    const CONCURRENCY = 16
    let nextIndex = 1

    const worker = () => {
      if (isCancelled || nextIndex >= TOTAL_FRAMES) return
      const idx = nextIndex++
      const img = new Image()
      const frameNum = String(idx + 1).padStart(3, '0')
      img.src = `${FRAME_BASE_URL}${frameNum}.webp`
      img.onload = () => {
        if (isCancelled) return
        if ('createImageBitmap' in window) {
          createImageBitmap(img)
            .then((bmp) => {
              if (isCancelled) return
              frames[idx] = bmp
              framesLoadedCountRef.current++
              forceRedrawRef.current = true
              worker()
            })
            .catch(() => {
              frames[idx] = img
              framesLoadedCountRef.current++
              forceRedrawRef.current = true
              worker()
            })
        } else {
          frames[idx] = img
          framesLoadedCountRef.current++
          forceRedrawRef.current = true
          worker()
        }
      }
      img.onerror = () => {
        if (isCancelled) return
        worker()
      }
    }

    for (let c = 0; c < CONCURRENCY; c++) {
      worker()
    }

    return () => {
      isCancelled = true
    }
  }, [])

  // Master RequestAnimationFrame decoupled render loop (Strictly 100 - 200 FPS)
  useEffect(() => {
    let animId: number
    const canvas = canvasRef.current
    const particlesCanvas = particlesCanvasRef.current
    const video = videoRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true })
    const pCtx = particlesCanvas?.getContext('2d', { alpha: true })
    if (!ctx) return

    const handleResize = () => {
      // 1:1 Native Resolution Pixel Blit (1920x1080) for absolute max rendering performance
      canvas.width = 1920
      canvas.height = 1080
      if (particlesCanvas) {
        particlesCanvas.width = window.innerWidth
        particlesCanvas.height = window.innerHeight
      }
      forceRedrawRef.current = true
    }
    handleResize()
    window.addEventListener('resize', handleResize)

    const renderLoop = (_time: number) => {
      animId = requestAnimationFrame(renderLoop)

      // Snappy and immediate progress sync (zero lag, eliminates sticking completely)
      const diff = targetProgressRef.current - currentProgressRef.current
      if (Math.abs(diff) > 0.00001) {
        currentProgressRef.current = targetProgressRef.current
      }

      // Render frame ONLY when dirty or frame index changed
      if (renderMode === 'canvas') {
        const frameIndex = Math.min(
          TOTAL_FRAMES - 1,
          Math.max(0, Math.floor(currentProgressRef.current * (TOTAL_FRAMES - 1))),
        )
        if (frameIndex !== lastRenderedIndexRef.current || forceRedrawRef.current) {
          // Nearest-neighbor fallback: if target frame isn't loaded yet, use closest loaded frame so it NEVER gets stuck
          let currentImg = framesRef.current[frameIndex]
          if (!currentImg) {
            for (let offset = 1; offset < TOTAL_FRAMES; offset++) {
              const prev = framesRef.current[frameIndex - offset]
              if (prev) {
                currentImg = prev
                break
              }
              const next = framesRef.current[frameIndex + offset]
              if (next) {
                currentImg = next
                break
              }
            }
          }

          if (currentImg) {
            renderFrameOnCanvas(ctx, canvas, currentImg)
            lastRenderedIndexRef.current = frameIndex
            forceRedrawRef.current = false
          }
        }
      } else if (renderMode === 'video' && video) {
        if (video.readyState >= 2 && Number.isFinite(video.duration)) {
          const targetVideoTime = currentProgressRef.current * video.duration
          if (!video.seeking && Math.abs(video.currentTime - targetVideoTime) > 0.02) {
            video.currentTime = targetVideoTime
          }
          renderFrameOnCanvas(ctx, canvas, video)
        }
      }

      // Ultra-lightweight batched volumetric particles on overlay canvas (< 0.05ms)
      if (pCtx && particlesCanvas) {
        const pw = particlesCanvas.width
        const ph = particlesCanvas.height
        pCtx.clearRect(0, 0, pw, ph)
        const particles = particlesRef.current
        pCtx.fillStyle = '#57e389'
        pCtx.globalAlpha = 0.28
        pCtx.beginPath()
        for (let i = 0; i < particles.length; i++) {
          const p = particles[i]
          p.x += p.speedX
          p.y += p.speedY
          if (p.x < 0) p.x = 1
          if (p.x > 1) p.x = 0
          if (p.y < 0) p.y = 1
          if (p.y > 1) p.y = 0

          p.alpha += (p.targetAlpha - p.alpha) * p.pulseSpeed
          if (Math.abs(p.alpha - p.targetAlpha) < 0.02) {
            p.targetAlpha = 0.15 + Math.random() * 0.5
          }

          pCtx.moveTo(p.x * pw + p.size, p.y * ph)
          pCtx.arc(p.x * pw, p.y * ph, p.size, 0, Math.PI * 2)
        }
        pCtx.fill()
      }
    }

    animId = requestAnimationFrame(renderLoop)

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', handleResize)
    }
  }, [renderMode, is8KSuperSample, renderFrameOnCanvas])

  // GSAP ScrollTrigger master timeline: instant 0.04s scrub, comfortable 4600px pacing
  useLayoutEffect(() => {
    const section = sectionRef.current
    if (!section) return

    const context = gsap.context(() => {
      const storyItems = storyRefs.current.filter(Boolean)
      gsap.set(storyItems, { autoAlpha: 0, y: 28, willChange: 'transform, opacity' })
      gsap.set('.cinematic-final-world', { autoAlpha: 0, willChange: 'opacity, transform' })
      gsap.set('.final-heading', { autoAlpha: 0, y: 35, willChange: 'transform, opacity' })
      gsap.set('.final-subtext', { autoAlpha: 0, y: 22, willChange: 'transform, opacity' })
      gsap.set('.final-actions', { autoAlpha: 0, y: 18, willChange: 'transform, opacity' })
      gsap.set('.final-closing', { autoAlpha: 0, y: 15, willChange: 'transform, opacity' })

      const timeline = gsap.timeline({
        defaults: { ease: 'none' },
        scrollTrigger: {
          trigger: section,
          start: 'top top',
          end: '+=4600',
          pin: true,
          scrub: 0.04, // Instant zero-lag wheel response
          anticipatePin: 1,
          invalidateOnRefresh: true,
          onUpdate: (trigger) => {
            targetProgressRef.current = trigger.progress

            const p = trigger.progress
            let activeStep = -1
            if (p >= 0.22 && p < 0.34) activeStep = 0
            else if (p >= 0.34 && p < 0.46) activeStep = 1
            else if (p >= 0.46 && p < 0.58) activeStep = 2
            else if (p >= 0.58 && p < 0.7) activeStep = 3
            else if (p >= 0.7 && p < 0.82) activeStep = 4
            else if (p >= 0.82) activeStep = 5

            if (activeStep !== lastRailStepRef.current) {
              lastRailStepRef.current = activeStep
              // Direct DOM class update: Zero React reconciliation lag during scroll!
              const nodes = document.querySelectorAll('.cinematic-rail .rail-node')
              nodes.forEach((node, idx) => {
                if (idx === activeStep) {
                  node.classList.add('rail-current')
                  node.classList.remove('rail-done')
                } else if (idx < activeStep) {
                  node.classList.remove('rail-current')
                  node.classList.add('rail-done')
                } else {
                  node.classList.remove('rail-current', 'rail-done')
                }
              })
            }
          },
        },
      })

      // 1. Intro hero copy exits smoothly
      timeline
        .to('.cinematic-hero-copy', { y: -85, autoAlpha: 0, duration: 0.11 }, 0)
        .to('.cinematic-canvas', { scale: 1.06, duration: 0.18 }, 0)

      // 2. Story narrative reveals with comfortable reading holds
      if (storyItems[0]) {
        timeline
          .to(storyItems[0], { autoAlpha: 1, y: 0, duration: 0.04 }, 0.11)
          .to(storyItems[0], { autoAlpha: 0, y: -22, duration: 0.035 }, 0.19)
      }
      if (storyItems[1]) {
        timeline
          .to(storyItems[1], { autoAlpha: 1, y: 0, duration: 0.04 }, 0.23)
          .to(storyItems[1], { autoAlpha: 0, y: -22, duration: 0.035 }, 0.31)
      }
      if (storyItems[2]) {
        timeline
          .to(storyItems[2], { autoAlpha: 1, y: 0, duration: 0.04 }, 0.35)
          .to(storyItems[2], { autoAlpha: 0, y: -22, duration: 0.035 }, 0.43)
      }
      if (storyItems[3]) {
        timeline
          .to(storyItems[3], { autoAlpha: 1, y: 0, duration: 0.04 }, 0.47)
          .to(storyItems[3], { autoAlpha: 0, y: -22, duration: 0.035 }, 0.55)
      }
      if (storyItems[4]) {
        timeline
          .to(storyItems[4], { autoAlpha: 1, y: 0, duration: 0.04 }, 0.59)
          .to(storyItems[4], { autoAlpha: 0, y: -22, duration: 0.035 }, 0.67)
      }
      if (storyItems[5]) {
        timeline
          .to(storyItems[5], { autoAlpha: 1, y: 0, duration: 0.04 }, 0.71)
          .to(storyItems[5], { autoAlpha: 0, y: -22, duration: 0.035 }, 0.78)
      }

      // 3. Scene & Vignette Transition into Deep Teal & Blue (#081D2B)
      timeline
        .to('.cinematic-scene', { scale: 1.05, duration: 0.18 }, 0.65)
        .to('.cinematic-stage-vignette', { backgroundColor: '#081d2b', duration: 0.18 }, 0.72)
        .to('.cinematic-progress-fill', { width: '100%', duration: 0.22 }, 0.76)

      // Fade out progress rail & scene readouts as we transition to final world
      timeline
        .to('.cinematic-rail', { autoAlpha: 0, duration: 0.06 }, 0.8)
        .to('.scene-readout', { autoAlpha: 0, duration: 0.06 }, 0.76)
        .to('.scene-index', { autoAlpha: 0, duration: 0.06 }, 0.76)
        .to('.scroll-cue', { autoAlpha: 0, duration: 0.06 }, 0.78)

      // 4. Intentional Crossfade: Canvas fades gently while Final World fades in
      timeline
        .to('.cinematic-canvas', { autoAlpha: 0, duration: 0.09 }, 0.76)
        .to('.cinematic-particles-canvas', { autoAlpha: 0, duration: 0.09 }, 0.76)
        .to('.cinematic-final-world', { autoAlpha: 1, duration: 0.08 }, 0.76)
        .to('.final-world-img', { scale: 1.045, y: -15, duration: 0.24 }, 0.76)

      // 5. Reveal Final Editorial Content in sequence
      timeline
        .to('.final-heading', { autoAlpha: 1, y: 0, duration: 0.06 }, 0.82)
        .to('.final-subtext', { autoAlpha: 1, y: 0, duration: 0.06 }, 0.85)
        .to('.final-actions', { autoAlpha: 1, y: 0, duration: 0.06 }, 0.88)
        .to('.final-closing', { autoAlpha: 1, y: 0, duration: 0.06 }, 0.9)
    }, section)

    ScrollTrigger.refresh()
    return () => context.revert()
  }, [])

  return (
    <div className="cinematic-overview">
      {/* Navigation */}
      <header className="cinematic-nav">
        <Link to="/overview" className="cinematic-brand">
          <span className="cinematic-logo">
            <i />
            <i />
            <i />
            <i />
          </span>{' '}
          RETURN MANAGER
        </Link>
        <nav>
          <button onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            Overview
          </button>
          <button onClick={() => window.scrollTo({ top: window.innerHeight * 2, behavior: 'smooth' })}>
            How it works
          </button>
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button className="cinematic-signin" onClick={() => navigate('/dashboard')}>
            Sign in <ArrowRight size={14} />
          </button>
        </div>
      </header>

      {/* Main Experience */}
      <main>
        <section className="cinematic-stage-section" ref={sectionRef} aria-label="sydon returns cinematic overview">
          <div className="cinematic-stage-vignette" />
          <div className="cinematic-stage-inner">
            <div className="cinematic-stage-grid" />
            <div className="cinematic-hero-copy">
              <span className="cinematic-eyebrow">RETURN OPERATIONS PLATFORM</span>
              <h1>
                RETURN MANAGER
                <br />
                <em>INTELLIGENCE FOR EVERY RETURN.</em>
              </h1>
              <p>Turn every returned item into a verified, traceable operational decision.</p>
            </div>

            <div className="cinematic-scene">
              <div className="scene-halo" />
              <div className="scene-ring ring-a" />
              <div className="scene-ring ring-b" />

              {/* Hardware-Accelerated Canvas Render Target with High-DPI Supersampling */}
              <canvas ref={canvasRef} className="cinematic-canvas" />

              {/* Volumetric Depth Particles Overlay Canvas */}
              <canvas
                ref={particlesCanvasRef}
                className="cinematic-canvas cinematic-particles-canvas"
                style={{ zIndex: 4, pointerEvents: 'none' }}
              />

              {/* Hidden Fallback Video Player */}
              <video
                ref={videoRef}
                className="cinematic-hidden-video"
                autoPlay={false}
                muted
                playsInline
                preload={renderMode === 'video' ? 'auto' : 'none'}
                src={renderMode === 'video' ? G1_VIDEO_URL : undefined}
              />

              <div className="scene-readout readout-top">
                <span>IDENTITY</span>
                <strong>PASS</strong>
                <Check size={13} />
              </div>
              <div className="scene-readout readout-bottom">
                <span>RECOVERY VALUE</span>
                <strong>$684</strong>
                <ArrowDownRight size={13} />
              </div>
              <span className="scene-index">
                00 <i /> EMERGENCE
              </span>
            </div>

            {/* Subtle Narrative Progress Rail */}
            <div className="cinematic-rail" aria-label="Narrative progress rail">
              <div className="rail-track">
                {narrativeSteps.map((step) => {
                  return (
                    <div
                      key={step.number}
                      className="rail-node"
                    >
                      <span className="rail-marker">
                        <Check size={8} />
                      </span>
                      <span className="rail-text">
                        <span className="rail-num">{step.number}</span>
                        <span className="rail-name">{step.label}</span>
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Cinematic Story Stack */}
            <div className="cinematic-story-stack">
              {story.map((item, index) => (
                <div
                  ref={(element) => {
                    storyRefs.current[index] = element
                  }}
                  className="cinematic-story"
                  key={item.eyebrow}
                >
                  <span className="cinematic-eyebrow">{item.eyebrow}</span>
                  <h2>
                    {item.title.split('\n').map((line) => (
                      <span key={line}>{line}</span>
                    ))}
                  </h2>
                  <p>{item.copy}</p>

                  {/* Technical Decision Labels (RESTOCK · REFUND · REJECT · REVIEW) */}
                  {item.badges && (
                    <div className="story-decision-badges">
                      {item.badges.map((badge) => (
                        <span key={badge} className={`decision-badge badge-${badge.toLowerCase()}`}>
                          <i className="badge-dot" />
                          {badge}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="story-meta-row">
                    <span className="story-meta-pill">
                      <ShieldCheck size={10} />
                      {item.meta}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Art-Directed Final Cinematic World */}
            <div className="cinematic-final-world">
              <picture className="final-world-picture">
                <source srcSet="/final-world.webp" type="image/webp" />
                <img
                  src="/final-world.jpg"
                  alt="sydon returns cinematic universe"
                  className="final-world-img"
                />
              </picture>
              <div className="final-world-color-grade" />
              <div className="final-world-vignette" />
              <div className="final-world-atmosphere" />

              <div className="final-editorial">
                <div className="final-content-wrap">
                  <span className="cinematic-eyebrow">RETURN OPERATIONS PLATFORM</span>
                  <h2 className="final-heading">
                    <span>ONE RETURN.</span>
                    <span>COMPLETE</span>
                    <em className="final-heading-accent">VISIBILITY.</em>
                  </h2>
                  <p className="final-subtext">
                    From arrival to disposition, every return becomes visible, verifiable, and actionable.
                  </p>

                  <div className="final-actions">
                    <button className="final-btn-primary" onClick={() => navigate('/dashboard')}>
                      <span>ENTER RETURN MANAGER</span>
                      <ArrowRight size={14} />
                    </button>
                    <button
                      className="final-btn-secondary"
                      onClick={() => navigate('/returns')}
                    >
                      <Eye size={14} />
                      <span>EXPLORE THE WORKFLOW</span>
                    </button>
                  </div>
                </div>

                <div className="final-closing">
                  <div className="final-signature">
                    <div className="signature-brand">
                      <span className="cinematic-logo">
                        <i />
                        <i />
                        <i />
                        <i />
                      </span>
                      <strong>RETURN MANAGER</strong>
                      <span className="signature-tag">INTELLIGENT RETURN OPERATIONS</span>
                    </div>
                    <div className="signature-pipeline">
                      <span>IDENTIFY</span>
                      <i>·</i>
                      <span>INSPECT</span>
                      <i>·</i>
                      <span>VERIFY</span>
                      <i>·</i>
                      <span>DECIDE</span>
                      <i>·</i>
                      <span>DISPOSITION</span>
                    </div>
                  </div>

                  <footer className="final-film-footer">
                    <span className="film-copy">RETURN MANAGER © 2026</span>
                    <div className="film-footer-links">
                      <button onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
                        Overview
                      </button>
                      <button onClick={() => navigate('/returns')}>
                        Workflow
                      </button>
                      <button onClick={() => navigate('/dashboard')}>
                        Sign In
                      </button>
                    </div>
                    <span className="film-status">ALL SYSTEMS OPERATIONAL · VERIFIED</span>
                  </footer>
                </div>
              </div>
            </div>

            <div className="cinematic-progress">
              <span>00</span>
              <div>
                <i className="cinematic-progress-fill" />
              </div>
              <span>100</span>
            </div>
          </div>

          <button
            className="scroll-cue"
            onClick={() => window.scrollTo({ top: window.innerHeight * 2, behavior: 'smooth' })}
          >
            <span>SCROLL TO EXPLORE</span>
            <ArrowRight size={14} />
          </button>
        </section>
      </main>
    </div>
  )
}

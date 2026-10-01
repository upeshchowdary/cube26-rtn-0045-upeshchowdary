// Shared Return Manager components (Part D): wordmark, buttons, eyebrow, card, FAQ, site header,
// footer and back-to-top. Level 1 motion only (CSS transitions from tokens.css).
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ChevronDown, ChevronUp, Menu, X } from 'lucide-react'
import { scrollToTarget } from '../motion/scroll'
import './components.css'

export function Mark({ size = 26, className = '' }: { size?: number; className?: string }) {
  return (
    <img
      src="/sydon-mark.png"
      alt="sydon mark"
      width={size}
      height={size}
      className={`rm-mark sydon-mark ${className}`.trim()}
      style={{ objectFit: 'contain', display: 'inline-block', verticalAlign: 'middle', flexShrink: 0 }}
    />
  )
}

export function Wordmark({ to = '/overview' }: { to?: string }) {
  return (
    <Link to={to} className="rm-wordmark sydon-wordmark" aria-label="sydon home">
      <img src="/sydon-logo.png" alt="sydon" className="sydon-logo-img sydon-logo-light" />
      <img src="/sydon-logo-dark.png" alt="sydon" className="sydon-logo-img sydon-logo-dark" />
    </Link>
  )
}

type ButtonProps = {
  children: ReactNode
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'md' | 'lg'
  arrow?: boolean
  className?: string
} & ({ to: string; onClick?: never; href?: never } | { href: string; to?: never; onClick?: () => void } | { onClick: () => void; to?: never; href?: never })

export function Button(props: ButtonProps) {
  const { children, variant = 'primary', size = 'md', arrow = false, className = '' } = props
  const cls = `rm-btn rm-btn-${variant} rm-btn-${size} ${className}`.trim()
  const inner = (
    <>
      <span>{children}</span>
      {arrow && <ArrowRight className="rm-btn-arrow" size={16} strokeWidth={2.2} aria-hidden="true" />}
    </>
  )
  if ('to' in props && props.to) {
    return (
      <Link className={cls} to={props.to}>
        {inner}
      </Link>
    )
  }
  if ('href' in props && props.href) {
    const href = props.href
    return (
      <a
        className={cls}
        href={href}
        onClick={(event) => {
          if (href.startsWith('#')) {
            event.preventDefault()
            scrollToTarget(href, -72)
          }
          props.onClick?.()
        }}
      >
        {inner}
      </a>
    )
  }
  return (
    <button type="button" className={cls} onClick={props.onClick}>
      {inner}
    </button>
  )
}

export function Eyebrow({ children, tone = 'blue' }: { children: ReactNode; tone?: 'blue' | 'neutral' | 'plain' }) {
  return <span className={`rm-eyebrow rm-eyebrow-${tone}`}>{children}</span>
}

export function Card({ children, className = '', interactive = false }: { children: ReactNode; className?: string; interactive?: boolean }) {
  return <div className={`rm-card ${interactive ? 'rm-card-hover' : ''} ${className}`.trim()}>{children}</div>
}

/** "Sample data" label: every mockup value that isn't read from a real row carries one (Part B8). */
export function SampleTag({ children = 'Sample data' }: { children?: ReactNode }) {
  return <span className="rm-sample-tag">{children}</span>
}

export type FaqItem = { q: string; a: ReactNode }

export function Faq({ items }: { items: FaqItem[] }) {
  const [open, setOpen] = useState<number | null>(0)
  const base = useId()
  return (
    <div className="rm-faq">
      {items.map((item, i) => {
        const isOpen = open === i
        const panelId = `${base}-panel-${i}`
        const btnId = `${base}-btn-${i}`
        return (
          <div className={`rm-faq-item ${isOpen ? 'open' : ''}`} key={item.q}>
            <h3>
              <button
                id={btnId}
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                onClick={() => setOpen(isOpen ? null : i)}
              >
                <span className="rm-faq-num">{String(i + 1).padStart(2, '0')}</span>
                <span className="rm-faq-q">{item.q}</span>
                <span className="rm-faq-chev" aria-hidden="true">
                  <ChevronDown size={16} strokeWidth={2.2} />
                </span>
              </button>
            </h3>
            <div id={panelId} role="region" aria-labelledby={btnId} className="rm-faq-panel" inert={!isOpen}>
              <div className="rm-faq-panel-inner">
                <div className="rm-faq-a">{item.a}</div>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export type NavItem = { label: string; href?: string; to?: string }

export function SiteHeader({ anchors, appLinks }: { anchors: NavItem[]; appLinks: NavItem[] }) {
  const [scrolled, setScrolled] = useState(false)
  const [menu, setMenu] = useState(false)
  const sentinel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // IntersectionObserver on a 1px sentinel: no scroll handler, no per-frame state.
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver(([entry]) => setScrolled(!entry.isIntersecting), { rootMargin: '24px 0px 0px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!menu) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menu])

  const go = (href: string) => {
    setMenu(false)
    scrollToTarget(href, -72)
  }

  const links = (onMobile: boolean) => (
    <>
      {anchors.map((a) => (
        <a
          key={a.label}
          href={a.href}
          className="rm-nav-link"
          onClick={(e) => {
            e.preventDefault()
            if (a.href) go(a.href)
          }}
        >
          {a.label}
        </a>
      ))}
      {!onMobile && <span className="rm-nav-sep" aria-hidden="true" />}
      {appLinks.map((a) => (
        <Link key={a.label} to={a.to || '/dashboard'} className="rm-nav-link rm-nav-app" onClick={() => setMenu(false)}>
          {a.label}
        </Link>
      ))}
    </>
  )

  return (
    <>
      <div ref={sentinel} className="rm-header-sentinel" aria-hidden="true" />
      <header className={`rm-header ${scrolled ? 'scrolled' : ''}`}>
        <span className="rm-progress" aria-hidden="true" data-scroll-progress />
        <div className="rm-header-inner">
          <Wordmark />
          <nav className="rm-nav" aria-label="Page sections and app screens">
            {links(false)}
          </nav>
          <div className="rm-header-cta">
            <Button to="/dashboard" arrow>
              Open sydon
            </Button>
            <button
              type="button"
              className="rm-menu-btn"
              aria-label={menu ? 'Close menu' : 'Open menu'}
              aria-expanded={menu}
              aria-controls="rm-mobile-nav"
              onClick={() => setMenu(!menu)}
            >
              {menu ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
        <nav id="rm-mobile-nav" className={`rm-mobile-nav ${menu ? 'open' : ''}`} aria-label="Menu" inert={!menu}>
          {links(true)}
          <Button to="/dashboard" arrow className="rm-mobile-cta">
            Open sydon
          </Button>
        </nav>
      </header>
    </>
  )
}

export function BackToTop() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    // Appears once the first screen has scrolled away; an observer, not a scroll handler.
    const probe = document.createElement('div')
    probe.style.cssText = 'position:absolute;top:0;left:0;width:1px;height:110vh;pointer-events:none;visibility:hidden'
    document.body.appendChild(probe)
    const io = new IntersectionObserver(([entry]) => setShow(!entry.isIntersecting))
    io.observe(probe)
    return () => {
      io.disconnect()
      probe.remove()
    }
  }, [])
  return (
    <button
      type="button"
      className={`rm-top ${show ? 'show' : ''}`}
      aria-label="Back to top"
      tabIndex={show ? 0 : -1}
      aria-hidden={!show}
      onClick={() => scrollToTarget(0)}
    >
      <ChevronUp size={20} strokeWidth={2.4} />
    </button>
  )
}

export function SiteFooter({ statement, links }: { statement: ReactNode; links: NavItem[] }) {
  return (
    <footer className="rm-footer">
      <div className="rm-footer-statement" data-footer-statement>
        {statement}
      </div>
      <div className="rm-footer-rule" />
      <div className="rm-footer-bottom">
        <Wordmark />
        <p className="rm-footer-copy">© 2026 sydon. Built for Cube Buildathon 04.</p>
        <nav className="rm-footer-nav" aria-label="Footer">
          {links.map((l) =>
            l.to ? (
              <Link key={l.label} to={l.to}>
                {l.label}
              </Link>
            ) : (
              <a
                key={l.label}
                href={l.href}
                onClick={(e) => {
                  e.preventDefault()
                  if (l.href) scrollToTarget(l.href, -72)
                }}
              >
                {l.label}
              </a>
            ),
          )}
        </nav>
      </div>
    </footer>
  )
}

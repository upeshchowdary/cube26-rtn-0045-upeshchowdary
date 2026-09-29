import type { ReactNode } from 'react'
import { ArrowUpRight, Sparkles, type LucideIcon } from 'lucide-react'
import { motion } from 'framer-motion'

export function Header({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string
  title: string
  subtitle: string
  actions?: ReactNode
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="header-actions">{actions}</div>
    </div>
  )
}

export function Button({
  children,
  icon: Icon,
  primary = false,
  onClick,
  disabled = false,
}: {
  children: ReactNode
  icon?: LucideIcon
  primary?: boolean
  onClick?: () => void
  disabled?: boolean
}) {
  return (
    <button disabled={disabled} className={`button ${primary ? 'primary' : ''}`} onClick={onClick}>
      {Icon && <Icon size={15} />}
      {children}
    </button>
  )
}

export function Pill({ value }: { value: string }) {
  return <span className={`pill ${value.toLowerCase().replaceAll(' ', '-').replaceAll('·', '')}`}>{value}</span>
}

export function Metric({
  label,
  value,
  note,
  icon: Icon,
  tone = 'teal',
}: {
  label: string
  value: string
  note: string
  icon: LucideIcon
  tone?: string
}) {
  return (
    <motion.div className="metric" whileHover={{ y: -2 }}>
      <span className={`metric-icon ${tone}`}>
        <Icon size={17} />
      </span>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
      <ArrowUpRight className="metric-arrow" size={15} />
    </motion.div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <div className="demo-note">
      <Sparkles size={13} /> {children}
    </div>
  )
}

export function InlineError({ children }: { children: ReactNode }) {
  return <div className="inline-error">{children}</div>
}

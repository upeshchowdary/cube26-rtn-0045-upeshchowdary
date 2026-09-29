// Line illustrations of the sample unit (SKU-LAMP-LED). The repo holds no product photo that can be
// shown (FACTS.md §11), so the page never pretends these are photos: every frame is captioned
// "Illustration, not a product photo".

type LampProps = { variant?: 'reference' | 'returned'; angle?: 0 | 1 | 2; className?: string }

/** A desk lamp: round weighted base, arm with a touch switch, LED head. */
export function LampArt({ variant = 'returned', angle = 0, className }: LampProps) {
  const tilt = [0, -8, 10][angle]
  const bg = variant === 'reference' ? '#F5F9FF' : '#F8FAFC'
  return (
    <svg className={className} viewBox="0 0 240 180" role="img" aria-label="Illustration of an LED desk lamp">
      <rect width="240" height="180" rx="14" fill={bg} />
      <g transform={`rotate(${tilt} 120 140)`}>
        {/* shadow */}
        <ellipse cx="120" cy="150" rx="46" ry="6" fill="#0B0F19" opacity="0.06" />
        {/* round weighted base */}
        <ellipse cx="120" cy="142" rx="40" ry="10" fill="#1F2937" />
        <rect x="80" y="134" width="80" height="8" rx="4" fill="#111827" />
        {/* arm */}
        <path d="M120 134 L106 84 L150 52" fill="none" stroke="#374151" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="106" cy="84" r="5" fill="#4B5563" />
        {/* touch switch on the arm */}
        <circle cx="113" cy="108" r="4" fill="#60A5FA" stroke="#fff" strokeWidth="1.5" />
        {/* LED head */}
        <rect x="140" y="40" width="54" height="14" rx="7" transform="rotate(18 150 52)" fill="#374151" />
        <rect x="143" y="50" width="46" height="3" rx="1.5" transform="rotate(18 150 52)" fill="#BFDBFE" />
      </g>
    </svg>
  )
}

export function CableArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 160 120" role="img" aria-label="Illustration of a USB cable">
      <rect width="160" height="120" rx="14" fill="#F8FAFC" />
      <path d="M30 86 C 30 40, 80 30, 90 58 S 130 90, 132 38" fill="none" stroke="#6B7280" strokeWidth="4" strokeLinecap="round" />
      <rect x="22" y="84" width="16" height="22" rx="3" fill="#374151" />
      <rect x="26" y="102" width="8" height="8" rx="1" fill="#9CA3AF" />
      <rect x="124" y="18" width="16" height="22" rx="3" fill="#374151" />
      <rect x="128" y="12" width="8" height="8" rx="1" fill="#9CA3AF" />
    </svg>
  )
}

export function ManualArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 160 120" role="img" aria-label="Illustration of a printed manual">
      <rect width="160" height="120" rx="14" fill="#F8FAFC" />
      <rect x="46" y="20" width="68" height="84" rx="4" fill="#fff" stroke="#D1D5DB" />
      <rect x="56" y="32" width="36" height="5" rx="2.5" fill="#2563EB" opacity="0.7" />
      {[46, 56, 66, 76, 86].map((y) => (
        <rect key={y} x="56" y={y} width={y === 86 ? 30 : 48} height="3" rx="1.5" fill="#E5E7EB" />
      ))}
    </svg>
  )
}

/** A barcode crop, for the scanner-beam effect. */
export function BarcodeArt({ className }: { className?: string }) {
  const bars = [3, 1, 2, 1, 1, 3, 1, 2, 2, 1, 3, 1, 1, 2, 1, 3, 2, 1, 1, 2, 3, 1, 2, 1, 1, 3, 1, 2]
  let x = 14
  return (
    <svg className={className} viewBox="0 0 200 72" role="img" aria-label="Illustration of a barcode label">
      <rect width="200" height="72" rx="10" fill="#fff" stroke="#E5E7EB" />
      {bars.map((b, i) => {
        const rect = i % 2 === 0 ? <rect key={i} x={x} y="12" width={b * 1.9} height="38" fill="#111827" /> : null
        x += b * 1.9 + 1.6
        return rect
      })}
      <text x="100" y="63" textAnchor="middle" fontFamily="DM Mono, monospace" fontSize="9" fill="#6B7280">
        SKU-LAMP-LED
      </text>
    </svg>
  )
}

export function IllustrationNote({ children = 'Illustration, not a product photo' }: { children?: string }) {
  return <span className="art-note">{children}</span>
}

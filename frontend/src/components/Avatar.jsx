export default function Avatar({ state = 'idle', size = 120 }) {
  // state: idle | listening | speaking | thinking
  return (
    <div className={`avatar avatar-${state}`} style={{ width: size, height: size }}>
      <svg viewBox="0 0 120 120" width={size} height={size}>
        <defs>
          <linearGradient id="avbg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#0d9488" />
            <stop offset="100%" stopColor="#065f5b" />
          </linearGradient>
        </defs>
        <circle cx="60" cy="60" r="58" fill="url(#avbg)" />
        <circle cx="60" cy="60" r="58" fill="none" stroke="#f59e0b" strokeWidth="2.5" className="avatar-ring" />
        {/* face */}
        <circle cx="60" cy="56" r="30" fill="#fde7d1" />
        {/* hair */}
        <path d="M30 52 Q32 24 60 24 Q88 24 90 52 Q86 40 74 36 Q64 33 46 36 Q34 40 30 52 Z" fill="#3b2f2f" />
        {/* eyes */}
        <g className="avatar-eyes">
          <ellipse cx="49" cy="55" rx="3.6" ry="4.6" fill="#2d2a26" />
          <ellipse cx="71" cy="55" rx="3.6" ry="4.6" fill="#2d2a26" />
          <circle cx="50.2" cy="53.6" r="1.1" fill="#fff" />
          <circle cx="72.2" cy="53.6" r="1.1" fill="#fff" />
        </g>
        {/* brows */}
        <path d="M44 47 Q49 44 54 46.5" stroke="#3b2f2f" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path d="M66 46.5 Q71 44 76 47" stroke="#3b2f2f" strokeWidth="2" fill="none" strokeLinecap="round" />
        {/* mouth */}
        <g className="avatar-mouth">
          <path className="mouth-idle" d="M51 70 Q60 76 69 70" stroke="#b45309" strokeWidth="2.6" fill="none" strokeLinecap="round" />
          <ellipse className="mouth-talk" cx="60" cy="71.5" rx="6.5" ry="4.5" fill="#8a3d1f" />
        </g>
        {/* collar — banker touch */}
        <path d="M38 96 Q60 84 82 96 L82 120 L38 120 Z" fill="#0f766e" />
        <path d="M56 90 L60 96 L64 90 L60 87 Z" fill="#f59e0b" />
      </svg>
      {state === 'listening' && <div className="pulse-ring" />}
    </div>
  )
}

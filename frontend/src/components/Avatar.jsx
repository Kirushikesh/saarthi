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
          <linearGradient id="avhair" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2b2119" />
            <stop offset="100%" stopColor="#171009" />
          </linearGradient>
          <linearGradient id="avjacket" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#115e59" />
            <stop offset="100%" stopColor="#0b3f3b" />
          </linearGradient>
          <clipPath id="avclip"><circle cx="60" cy="60" r="58" /></clipPath>
        </defs>

        <circle cx="60" cy="60" r="58" fill="url(#avbg)" />
        <circle cx="60" cy="60" r="58" fill="none" stroke="#f59e0b" strokeWidth="2.5" className="avatar-ring" />

        <g clipPath="url(#avclip)">
          <g className="avatar-head">
            {/* hair behind shoulders */}
            <path d="M28 50 Q26 96 34 112 L86 112 Q94 96 92 50 Q90 22 60 22 Q30 22 28 50 Z" fill="url(#avhair)" />
            {/* neck */}
            <rect x="53" y="78" width="14" height="14" rx="6" fill="#eab68f" />
            {/* face */}
            <ellipse cx="60" cy="57" rx="24" ry="26.5" fill="#f6c9a0" />
            {/* ears + jhumka earrings */}
            <ellipse cx="35.5" cy="58" rx="3.4" ry="5" fill="#eab68f" />
            <ellipse cx="84.5" cy="58" rx="3.4" ry="5" fill="#eab68f" />
            <circle cx="35.5" cy="64.5" r="2" fill="#f59e0b" />
            <circle cx="84.5" cy="64.5" r="2" fill="#f59e0b" />
            {/* center-parted front hair */}
            <path d="M36 52 Q36 27 60 26 Q84 27 84 52 Q82 36 62 33 L60 30 L58 33 Q38 36 36 52 Z" fill="url(#avhair)" />
            {/* bindi */}
            <circle cx="60" cy="43.5" r="1.7" fill="#b91c1c" />
            {/* brows */}
            <g className="avatar-brows">
              <path d="M45 47.5 Q50 44.8 55 46.8" stroke="#2b2119" strokeWidth="2.1" fill="none" strokeLinecap="round" />
              <path d="M65 46.8 Q70 44.8 75 47.5" stroke="#2b2119" strokeWidth="2.1" fill="none" strokeLinecap="round" />
            </g>
            {/* eyes: whites + iris that can glance (thinking) */}
            <g className="avatar-eyes">
              <ellipse cx="50" cy="55" rx="5" ry="4.4" fill="#fff" />
              <ellipse cx="70" cy="55" rx="5" ry="4.4" fill="#fff" />
              <g className="avatar-pupils">
                <circle cx="50" cy="55.4" r="2.7" fill="#3a2a1c" />
                <circle cx="70" cy="55.4" r="2.7" fill="#3a2a1c" />
                <circle cx="51" cy="54.4" r="0.9" fill="#fff" />
                <circle cx="71" cy="54.4" r="0.9" fill="#fff" />
              </g>
              {/* lash line */}
              <path d="M45 53.4 Q50 50.4 55 53.4" stroke="#2b2119" strokeWidth="1.4" fill="none" strokeLinecap="round" />
              <path d="M65 53.4 Q70 50.4 75 53.4" stroke="#2b2119" strokeWidth="1.4" fill="none" strokeLinecap="round" />
            </g>
            {/* nose */}
            <path d="M59.5 58 Q58.5 63 60.5 64.5" stroke="#d99e6d" strokeWidth="1.5" fill="none" strokeLinecap="round" />
            {/* blush */}
            <ellipse cx="45" cy="64" rx="3.6" ry="2" fill="#f0a884" opacity="0.5" />
            <ellipse cx="75" cy="64" rx="3.6" ry="2" fill="#f0a884" opacity="0.5" />
            {/* mouth: warm smile at rest, animated open mouth while speaking */}
            <g className="avatar-mouth">
              <path className="mouth-idle" d="M52 70.5 Q60 76.5 68 70.5" stroke="#b4472e" strokeWidth="2.6" fill="none" strokeLinecap="round" />
              <g className="mouth-talk">
                <ellipse cx="60" cy="72" rx="6.6" ry="4.8" fill="#7f2d17" />
                <path d="M54.5 70.5 Q60 68.5 65.5 70.5 L65.5 71.5 Q60 70 54.5 71.5 Z" fill="#fff" />
                <ellipse cx="60" cy="74.6" rx="3.4" ry="1.7" fill="#c4543a" />
              </g>
            </g>
          </g>
          {/* blazer + kurta — banker touch */}
          <path d="M30 120 Q31 95 47 90 L60 96 L73 90 Q89 95 90 120 Z" fill="url(#avjacket)" />
          <path d="M52 89 L60 96 L68 89 L68 120 L52 120 Z" fill="#f8dcb8" />
          <path d="M56 92 L60 97 L64 92" stroke="#f59e0b" strokeWidth="2" fill="none" />
          {/* IDBI-ish lapel pin */}
          <circle cx="73" cy="101" r="2.6" fill="#f59e0b" />
        </g>

        {/* thinking dots */}
        <g className="think-dots" fill="#fff">
          <circle cx="90" cy="26" r="2.4" />
          <circle cx="98" cy="19" r="3.2" />
          <circle cx="107" cy="11" r="4" />
        </g>
      </svg>
      {state === 'listening' && <div className="pulse-ring" />}
    </div>
  )
}

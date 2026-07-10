import { useEffect, useRef } from 'react'

/**
 * Saarthi's animated advisor — a "talking" character, not a static icon.
 *
 * state: idle | listening | speaking | thinking
 * levelRef: optional mutable ref (0..1) with the CURRENT loudness of the
 *   voice being played. While speaking, the mouth opens to match it — real
 *   amplitude lip-sync (live voice reports playback RMS from the audio
 *   worklet; browser TTS pulses it on each word boundary). Read at animation-frame
 *   rate via rAF so no React re-renders happen during speech. Without a
 *   levelRef, a natural procedural mouth cycle plays instead.
 */
export default function Avatar({ state = 'idle', size = 120, levelRef }) {
  const mouthRef = useRef(null)   // open-mouth group, scaleY-driven
  const smileRef = useRef(null)   // resting smile, cross-fades out as mouth opens
  const jawRef = useRef(null)     // chin drops a touch with the mouth
  const smooth = useRef(0)

  useEffect(() => {
    let raf
    const tick = (t) => {
      let target = 0
      if (state === 'speaking') {
        const live = levelRef?.current
        target = live != null && live > 0.02
          ? live
          // procedural fallback: two overlapping sines ≈ natural syllable rhythm
          : 0.3 + 0.7 * Math.abs(Math.sin(t / 92)) * (0.55 + 0.45 * Math.sin(t / 410))
      }
      if (levelRef && levelRef.current > 0) levelRef.current *= 0.9 // decay word pulses
      smooth.current += (target - smooth.current) * 0.35
      const v = Math.max(0, Math.min(1, smooth.current))
      if (mouthRef.current) {
        mouthRef.current.style.transform = `scaleY(${0.12 + 0.88 * v})`
        mouthRef.current.style.opacity = v > 0.06 ? 1 : 0
      }
      if (smileRef.current) smileRef.current.style.opacity = v > 0.06 ? 0 : 1
      if (jawRef.current) jawRef.current.style.transform = `translateY(${v * 1.1}px)`
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [state, levelRef])

  return (
    <div className={`avatar avatar-${state}`} style={{ width: size, height: size }}
      role="img" aria-label={`Saarthi, your advisor — ${state}`}>
      <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
        <defs>
          <radialGradient id="avbg" cx="0.5" cy="0.35" r="0.9">
            <stop offset="0%" stopColor="#14a89a" />
            <stop offset="100%" stopColor="#054b47" />
          </radialGradient>
          <linearGradient id="avhair" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#33261b" />
            <stop offset="100%" stopColor="#150d06" />
          </linearGradient>
          <linearGradient id="avjacket" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#136e67" />
            <stop offset="100%" stopColor="#0a3d39" />
          </linearGradient>
          <radialGradient id="avface" cx="0.5" cy="0.4" r="0.75">
            <stop offset="0%" stopColor="#f8d0a8" />
            <stop offset="100%" stopColor="#efbd8f" />
          </radialGradient>
          <clipPath id="avclip"><circle cx="60" cy="60" r="58" /></clipPath>
        </defs>

        <circle cx="60" cy="60" r="58" fill="url(#avbg)" />
        <circle cx="60" cy="60" r="58" fill="none" stroke="#f59e0b" strokeWidth="2.5" className="avatar-ring" />

        <g clipPath="url(#avclip)">
          <g className="avatar-head">
            {/* hair behind shoulders */}
            <path d="M28 50 Q26 96 34 112 L86 112 Q94 96 92 50 Q90 22 60 22 Q30 22 28 50 Z" fill="url(#avhair)" />
            {/* neck */}
            <rect x="53" y="78" width="14" height="14" rx="6" fill="#e6ae83" />
            {/* face */}
            <ellipse cx="60" cy="57" rx="24" ry="26.5" fill="url(#avface)" />
            {/* ears + jhumka earrings */}
            <ellipse cx="35.5" cy="58" rx="3.4" ry="5" fill="#eab68f" />
            <ellipse cx="84.5" cy="58" rx="3.4" ry="5" fill="#eab68f" />
            <circle cx="35.5" cy="64.5" r="2" fill="#f59e0b" />
            <circle cx="84.5" cy="64.5" r="2" fill="#f59e0b" />
            <circle cx="35.5" cy="67.3" r="1.1" fill="#fbbf24" />
            <circle cx="84.5" cy="67.3" r="1.1" fill="#fbbf24" />
            {/* center-parted front hair + shine */}
            <path d="M36 52 Q36 27 60 26 Q84 27 84 52 Q82 36 62 33 L60 30 L58 33 Q38 36 36 52 Z" fill="url(#avhair)" />
            <path d="M42 33 Q50 28.5 57 29.5" stroke="#5a4432" strokeWidth="1.3" fill="none" opacity="0.6" strokeLinecap="round" />
            {/* bindi */}
            <circle cx="60" cy="43.5" r="1.7" fill="#b91c1c" />
            {/* brows */}
            <g className="avatar-brows">
              <path d="M45 47.5 Q50 44.8 55 46.8" stroke="#2b2119" strokeWidth="2.1" fill="none" strokeLinecap="round" />
              <path d="M65 46.8 Q70 44.8 75 47.5" stroke="#2b2119" strokeWidth="2.1" fill="none" strokeLinecap="round" />
            </g>
            {/* eyes: whites + warm brown iris that glances (thinking) */}
            <g className="avatar-eyes">
              <ellipse cx="50" cy="55" rx="5" ry="4.4" fill="#fff" />
              <ellipse cx="70" cy="55" rx="5" ry="4.4" fill="#fff" />
              <g className="avatar-pupils">
                <circle cx="50" cy="55.4" r="3" fill="#6b4423" />
                <circle cx="70" cy="55.4" r="3" fill="#6b4423" />
                <circle cx="50" cy="55.4" r="1.6" fill="#241505" />
                <circle cx="70" cy="55.4" r="1.6" fill="#241505" />
                <circle cx="51" cy="54.2" r="0.9" fill="#fff" />
                <circle cx="71" cy="54.2" r="0.9" fill="#fff" />
              </g>
              {/* lash line */}
              <path d="M45 53.4 Q50 50.4 55 53.4" stroke="#2b2119" strokeWidth="1.5" fill="none" strokeLinecap="round" />
              <path d="M65 53.4 Q70 50.4 75 53.4" stroke="#2b2119" strokeWidth="1.5" fill="none" strokeLinecap="round" />
            </g>
            {/* nose */}
            <path d="M59.5 58 Q58.5 63 60.5 64.5" stroke="#d99e6d" strokeWidth="1.5" fill="none" strokeLinecap="round" />
            {/* blush */}
            <ellipse cx="45" cy="64" rx="3.6" ry="2" fill="#f0a884" opacity="0.5" />
            <ellipse cx="75" cy="64" rx="3.6" ry="2" fill="#f0a884" opacity="0.5" />
            {/* mouth — jaw group nudges down as the mouth opens */}
            <g ref={jawRef}>
              {/* resting warm smile (fades while talking) */}
              <path ref={smileRef} d="M52 70.5 Q60 76.5 68 70.5" stroke="#b4472e" strokeWidth="2.6"
                fill="none" strokeLinecap="round" style={{ transition: 'opacity 0.12s' }} />
              {/* open mouth, scaleY = live voice loudness */}
              <g ref={mouthRef} style={{ transformOrigin: '60px 71px', opacity: 0 }}>
                <ellipse cx="60" cy="72" rx="6.6" ry="5.2" fill="#7f2d17" />
                <path d="M54 70 Q60 67.8 66 70 L66 71.4 Q60 69.6 54 71.4 Z" fill="#fff" />
                <ellipse cx="60" cy="75" rx="3.6" ry="1.9" fill="#c4543a" />
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

        {/* listening: little sound waves entering the ear */}
        <g className="listen-waves" stroke="#fbbf24" strokeWidth="2" fill="none" strokeLinecap="round">
          <path d="M14 52 Q17 57 14 62" />
          <path d="M8 47 Q13 57 8 67" />
        </g>
      </svg>
      {state === 'listening' && <div className="pulse-ring" />}
    </div>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { bcp47 } from './i18n'

// Saarthi's avatar is a woman, so her spoken voice should read female too. The
// realtime voice (Gemini Live) is set female in the backend; this is the browser
// SpeechSynthesis fallback used for text-chat replies and read-aloud. Pick a
// language-matched voice, preferring female-sounding ones so the fallback stays
// consistent with the persona instead of defaulting to whatever (often male)
// voice the OS lists first.
const FEMALE_HINTS = /female|woman|zira|samantha|salli|joanna|kendra|ivy|aria|jenny|neerja|swara|kalpana|heera|google.*(female| उ)|\bf\b/i
const MALE_HINTS = /male|man|david|mark|guy|ravi|hemant|prabhat|\bm\b/i

function pickVoice(voices, target) {
  const short = target.slice(0, 2)
  const matches = voices.filter((v) => v.lang === target)
  const near = voices.filter((v) => v.lang.startsWith(short))
  const pool = matches.length ? matches : near
  if (!pool.length) return null
  return (
    pool.find((v) => FEMALE_HINTS.test(v.name)) ||
    pool.find((v) => !MALE_HINTS.test(v.name)) ||
    pool[0]
  )
}

// Standalone read-aloud for screen-optional banking: any component can have
// numbers/notifications spoken without wiring up the full speech hook.
export function speakPlain(text, lang = 'en') {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const plain = String(text).replace(/[*#_`>|]/g, ' ').replace(/\s+/g, ' ').trim()
  const u = new SpeechSynthesisUtterance(plain.slice(0, 500))
  const target = bcp47(lang)
  u.voice = pickVoice(window.speechSynthesis.getVoices(), target)
  u.lang = target
  window.speechSynthesis.speak(u)
}

export function useSpeech(lang) {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  // Mouth-drive level for the avatar (0..1): browser TTS gives no audio
  // stream to analyse, but fires a boundary event per spoken word — each one
  // pulses this ref and the avatar decays it, so the mouth moves word-by-word.
  const levelRef = useRef(0)
  const recRef = useRef(null)
  const supported = typeof window !== 'undefined' && ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)

  const listen = useCallback((onResult) => {
    if (!supported || listening) return
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    const rec = new SR()
    rec.lang = bcp47(lang)
    rec.interimResults = false
    rec.maxAlternatives = 1
    rec.onresult = (e) => onResult(e.results[0][0].transcript)
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    setListening(true)
    rec.start()
  }, [supported, listening, lang])

  const stopListening = useCallback(() => {
    recRef.current?.stop()
    setListening(false)
  }, [])

  const speak = useCallback((text) => {
    if (!window.speechSynthesis) return
    window.speechSynthesis.cancel()
    // strip markdown for natural speech
    const plain = text.replace(/[*#_`>|-]/g, ' ').replace(/\[(.*?)\]\(.*?\)/g, '$1').replace(/\s+/g, ' ').trim()
    const u = new SpeechSynthesisUtterance(plain.slice(0, 800))
    const target = bcp47(lang)
    u.voice = pickVoice(window.speechSynthesis.getVoices(), target)
    u.lang = target
    u.rate = 1.02
    u.onstart = () => { setSpeaking(true); levelRef.current = 0.8 }
    u.onboundary = () => { levelRef.current = 1 } // word-by-word mouth pulses
    u.onend = () => { setSpeaking(false); levelRef.current = 0 }
    u.onerror = () => { setSpeaking(false); levelRef.current = 0 }
    window.speechSynthesis.speak(u)
  }, [lang])

  const stopSpeaking = useCallback(() => {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
    levelRef.current = 0
  }, [])

  useEffect(() => () => { window.speechSynthesis?.cancel(); recRef.current?.abort?.() }, [])

  return { supported, listening, speaking, levelRef, listen, stopListening, speak, stopSpeaking }
}

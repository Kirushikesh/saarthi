import { useCallback, useEffect, useRef, useState } from 'react'
import { bcp47 } from './i18n'

// Standalone read-aloud for screen-optional banking: any component can have
// numbers/notifications spoken without wiring up the full speech hook.
export function speakPlain(text, lang = 'en') {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const plain = String(text).replace(/[*#_`>|]/g, ' ').replace(/\s+/g, ' ').trim()
  const u = new SpeechSynthesisUtterance(plain.slice(0, 500))
  const target = bcp47(lang)
  const voices = window.speechSynthesis.getVoices()
  u.voice = voices.find((v) => v.lang === target) || voices.find((v) => v.lang.startsWith(target.slice(0, 2))) || null
  u.lang = target
  window.speechSynthesis.speak(u)
}

export function useSpeech(lang) {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
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
    const voices = window.speechSynthesis.getVoices()
    u.voice = voices.find((v) => v.lang === target) || voices.find((v) => v.lang.startsWith(target.slice(0, 2))) || null
    u.lang = target
    u.rate = 1.02
    u.onstart = () => setSpeaking(true)
    u.onend = () => setSpeaking(false)
    u.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(u)
  }, [lang])

  const stopSpeaking = useCallback(() => {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
  }, [])

  useEffect(() => () => { window.speechSynthesis?.cancel(); recRef.current?.abort?.() }, [])

  return { supported, listening, speaking, listen, stopListening, speak, stopSpeaking }
}

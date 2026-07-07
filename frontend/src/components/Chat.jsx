import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { useSpeech } from '../useSpeech'
import { useVoiceSession } from '../useVoiceSession'
import Avatar from './Avatar'

import { GREET, SUGGESTIONS, UI, t } from '../i18n'

export default function Chat({ customer, householdMode, lang, voiceOn, sugam, onLead }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const speech = useSpeech(lang)
  const bottomRef = useRef(null)
  const speechRef = useRef(speech)
  speechRef.current = speech

  // Realtime voice session (Gemini Live via ADK). Transcripts land in the
  // same message list; leads flash the RM console tab like text chat does.
  const voice = useVoiceSession({
    onTranscript: (who, text) =>
      setMessages((m) => {
        const role = who === 'user' ? 'user' : 'assistant'
        const last = m[m.length - 1]
        if (last?.role === role && last?.live) {
          return [...m.slice(0, -1), { ...last, content: last.content + text }]
        }
        return [...m, { role, content: text, live: true }]
      }),
    onLead: (lead) => {
      setMessages((m) => [...m, { role: 'assistant', content: '', lead, live: true }])
      onLead?.(lead)
    },
  })

  const toggleLive = () => {
    if (voice.live) voice.stop()
    else voice.start(customer.id, householdMode)
  }

  useEffect(() => {
    setMessages([{ role: 'assistant', content: (GREET[lang] || GREET.en)(customer.name.split(' ')[0]) }])
  }, [customer.id, householdMode, lang]) // eslint-disable-line

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const send = async (text) => {
    const msg = (text ?? input).trim()
    if (!msg || busy) return
    setInput('')
    const history = messages.map(({ role, content }) => ({ role, content }))
    setMessages((m) => [...m, { role: 'user', content: msg }])
    setBusy(true)
    try {
      const res = await api.chat({
        customer_id: customer.id, message: msg, history, household_mode: householdMode,
        sugam_mode: !!sugam,
      })
      setMessages((m) => [...m, { role: 'assistant', content: res.reply, lead: res.lead, events: res.events }])
      if (res.lead) onLead?.(res.lead)
      if (voiceOn) speechRef.current.speak(res.reply)
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ ${e.message}` }])
    } finally {
      setBusy(false)
    }
  }

  const avatarState =
    voice.speaking || speech.speaking ? 'speaking'
    : voice.thinking || busy ? 'thinking'
    : voice.live || speech.listening ? 'listening'
    : 'idle'
  const sugg = t(SUGGESTIONS[householdMode ? 'household' : 'individual'], lang)

  return (
    <div className="chat">
      <div className="chat-avatar-strip">
        <Avatar state={avatarState} size={86} />
        <div className="avatar-status" role="status">
          {voice.error ? `⚠️ ${voice.error}`
            : avatarState === 'speaking' ? (lang === 'hi' ? 'बोल रही हूँ…' : 'Speaking…')
            : avatarState === 'thinking' ? (lang === 'hi' ? 'सोच रही हूँ…' : 'Consulting your portfolio…')
            : voice.live ? (lang === 'hi' ? 'लाइव — बोलिए…' : 'Live — just start talking')
            : avatarState === 'listening' ? (lang === 'hi' ? 'सुन रही हूँ…' : 'Listening…')
            : householdMode ? 'Humsafar mode · advising your household' : `Advising ${customer.name.split(' ')[0]} · ${customer.risk_profile}`}
        </div>
        <button className={`chip live-chip ${voice.live ? 'on' : ''}`} onClick={toggleLive}>
          {voice.live ? '◼ End live' : '🎙 Live voice'}
        </button>
        {speech.speaking && (
          <button className="chip stop-chip" onClick={speech.stopSpeaking}>◼ Stop voice</button>
        )}
      </div>

      <div className="chat-scroll" role="log" aria-live="polite" aria-label="Conversation with Saarthi">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            <ReactMarkdown>{m.content}</ReactMarkdown>
            {m.lead && (
              <div className="lead-card">
                <div className="lead-title">🤝 RM callback booked</div>
                <div>{m.lead.product} · Lead {m.lead.id} · Priority {m.lead.priority}</div>
                <div className="lead-sub">A certified IDBI Relationship Manager will call you within 24 hours.</div>
              </div>
            )}
            {m.events?.length > 0 && (
              <div className="events">
                {m.events.map((e, j) => (
                  <span key={j} className="event-tag">⚙ {e.tool.replaceAll('_', ' ')}</span>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="bubble assistant typing"><span /><span /><span /></div>}
        <div ref={bottomRef} />
      </div>

      <div className="suggestions">
        {sugg.map((s) => (
          <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>{s}</button>
        ))}
      </div>

      <div className="chat-input">
        {speech.supported && !voice.live && (
          <button
            className={`mic ${speech.listening ? 'on' : ''}`}
            onClick={() => (speech.listening ? speech.stopListening() : speech.listen((t) => send(t)))}
            title="Dictate (offline fallback)"
            aria-label={speech.listening ? 'Stop dictating' : 'Dictate your question'}
            aria-pressed={speech.listening}
          >
            {speech.listening ? '◼' : '🎤'}
          </button>
        )}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={t(UI.placeholder, lang)}
          aria-label={t(UI.placeholder, lang)}
        />
        <button className="send" onClick={() => send()} disabled={busy || !input.trim()} aria-label="Send message">➤</button>
      </div>
    </div>
  )
}

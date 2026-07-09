import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { useSpeech } from '../useSpeech'
import { useVoiceSession } from '../useVoiceSession'
import Avatar from './Avatar'

import { GREET, SUGGESTIONS, UI, t } from '../i18n'

// Friendly labels for streamed tool-status pings — the customer sees what
// Saarthi is doing during the wait instead of a silent spinner.
const TOOL_STATUS = {
  get_portfolio: 'Fetching your 360° portfolio…',
  get_household_view: 'Combining your household finances…',
  simulate_loan_affordability: 'Running the EMI & FOIR math…',
  plan_goal: 'Crunching your goal plan…',
  plan_sip_target: 'Calculating the SIP you need…',
  project_retirement: 'Projecting your retirement corpus…',
  get_tax_summary: 'Checking your 80C / NPS headroom…',
  get_market_pulse: 'Reading today’s markets…',
  get_financial_health: 'Scoring your financial health…',
  check_suitability: 'Running suitability checks…',
  get_behavioral_profile: 'Reading your spending patterns…',
  get_product_catalog: 'Looking up current rates…',
  create_rm_lead: 'Arranging your Relationship Manager…',
}

export default function Chat({ customer, householdMode, lang, voiceOn, sugam, onLead }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [statusText, setStatusText] = useState(null)
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
    // Stream the reply: tool-status pings + tokens render live, then the
    // final `done` payload (authoritative — includes the compliance fallback)
    // replaces the streamed text.
    let streaming = false
    const upsertStream = (updater) =>
      setMessages((m) => {
        const last = m[m.length - 1]
        if (streaming && last?.role === 'assistant' && last?.streaming) {
          return [...m.slice(0, -1), updater(last)]
        }
        streaming = true
        return [...m, updater({ role: 'assistant', content: '', streaming: true })]
      })
    try {
      const res = await api.chatStream(
        { customer_id: customer.id, message: msg, history, household_mode: householdMode, sugam_mode: !!sugam },
        (ev) => {
          if (ev.type === 'status') setStatusText(TOOL_STATUS[ev.tool] || 'Working on it…')
          if (ev.type === 'token') upsertStream((b) => ({ ...b, content: b.content + ev.text }))
        },
      )
      setMessages((m) => {
        const rest = streaming ? m.slice(0, -1) : m
        return [...rest, { role: 'assistant', content: res.reply, lead: res.lead, events: res.events }]
      })
      if (res.lead) onLead?.(res.lead)
      if (voiceOn) speechRef.current.speak(res.reply)
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ ${e.message}` }])
    } finally {
      setBusy(false)
      setStatusText(null)
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
        <Avatar state={avatarState} size={148}
          levelRef={voice.live ? voice.levelRef : speech.levelRef} />
        <div className="avatar-status" role="status">
          {voice.error ? `⚠️ ${voice.error}`
            : avatarState === 'speaking' ? (lang === 'hi' ? 'बोल रही हूँ…' : 'Speaking…')
            : avatarState === 'thinking' ? (statusText || (lang === 'hi' ? 'सोच रही हूँ…' : 'Consulting your portfolio…'))
            : voice.live ? (lang === 'hi' ? 'लाइव — बोलिए…' : 'Live — just start talking')
            : avatarState === 'listening' ? (lang === 'hi' ? 'सुन रही हूँ…' : 'Listening…')
            : householdMode ? 'Household mode · advising your household' : `Advising ${customer.name.split(' ')[0]} · ${customer.risk_profile}`}
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
                <div className="lead-sub">A certified IDBI Relationship Manager will reach out to you shortly.</div>
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
        {busy && !messages[messages.length - 1]?.streaming && (
          <div className="bubble assistant typing">
            {statusText && <span className="typing-status">{statusText}</span>}
            <span /><span /><span />
          </div>
        )}
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

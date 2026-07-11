import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { useSpeech } from '../useSpeech'
import { useVoiceSession } from '../useVoiceSession'
import Avatar3D, { AvatarLoading } from './Avatar3D'

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

export default function Chat({ customer, householdMode, lang, textScale = 'md', onLead }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [statusText, setStatusText] = useState(null)
  // Voice is opt-in: tapping the avatar opens this confirm popup; a second tap
  // (while live) ends the session. There is no separate voice button anymore.
  const [voicePrompt, setVoicePrompt] = useState(false)
  // The transcript is a scrollable log that stays pinned to the newest line
  // unless the user has deliberately scrolled up to read history.
  const scrollRef = useRef(null)
  const stick = useRef(true)
  // useSpeech now only powers offline dictation (speech-to-text). Spoken replies
  // (TTS) were removed — for a voice conversation the customer uses live voice.
  const speech = useSpeech(lang)

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

  // Tapping the avatar: if a voice session is live, end it; otherwise ask
  // first (the confirm popup), so the mic is never opened without consent.
  const onAvatarTap = () => {
    if (voice.live) voice.stop()
    else setVoicePrompt(true)
  }
  const startVoice = () => {
    setVoicePrompt(false)
    voice.start(customer.id, householdMode)
  }

  useEffect(() => {
    setMessages([{ role: 'assistant', content: (GREET[lang] || GREET.en)(customer.name.split(' ')[0]) }])
  }, [customer.id, householdMode, lang]) // eslint-disable-line

  // Keep the transcript pinned to the newest line as it grows — but only while
  // the user is already at the bottom, so scrolling up to read history sticks.
  const onScroll = () => {
    const el = scrollRef.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
  }
  useEffect(() => {
    const el = scrollRef.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [messages, busy, statusText])

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
        { customer_id: customer.id, message: msg, history, household_mode: householdMode },
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
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ ${e.message}` }])
    } finally {
      setBusy(false)
      setStatusText(null)
    }
  }

  const avatarState =
    voice.speaking ? 'speaking'
    : voice.thinking || busy ? 'thinking'
    : voice.live || speech.listening ? 'listening'
    : 'idle'
  const sugg = t(SUGGESTIONS[householdMode ? 'household' : 'individual'], lang)

  const statusLine =
    voice.error ? `⚠️ ${voice.error}`
    : avatarState === 'speaking' ? (lang === 'hi' ? 'बोल रही हूँ…' : 'Speaking…')
    : avatarState === 'thinking' ? (statusText || (lang === 'hi' ? 'सोच रही हूँ…' : 'Consulting your portfolio…'))
    : voice.live ? (lang === 'hi' ? 'लाइव — बोलिए…' : 'Live — just start talking')
    : avatarState === 'listening' ? (lang === 'hi' ? 'सुन रही हूँ…' : 'Listening…')
    : householdMode ? 'Household mode · advising your household' : `Advising ${customer.name.split(' ')[0]} · ${customer.risk_profile}`

  return (
    <div className={`stage ${householdMode ? 'household' : ''}`}>
      {/* Full-screen 3D advisor — the figure you talk to. Tap her to start (or
          end) a live voice conversation. Transparent canvas so the transcript
          floats over the very same stage background. */}
      <div
        className={`stage-scene ${voice.live ? 'live' : ''}`}
        role="button"
        tabIndex={0}
        aria-label={voice.live ? 'End voice conversation with Saarthi' : 'Tap Saarthi to start a voice conversation'}
        onClick={onAvatarTap}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onAvatarTap())}
      >
        <Avatar3D state={avatarState} levelRef={voice.levelRef} />
      </div>
      <AvatarLoading />

      <div className="stage-top">
        <div className={`stage-status ${avatarState}`} role="status">{statusLine}</div>
      </div>

      {/* Affordance so it's discoverable that the avatar itself is the mic. */}
      <button className={`voice-hint ${voice.live ? 'live' : ''}`} onClick={onAvatarTap}>
        {voice.live ? '● Live · tap to end' : '🎙 Tap Saarthi to talk'}
      </button>

      {/* Floating transcript: newest at the bottom, older lines rising and fading
          into the backdrop. Scrollable — drag up to revisit history; it re-pins
          to the newest line once you're back at the bottom. No bubbles. */}
      <div className={`transcript scale-${textScale}`} role="log" aria-live="polite" aria-label="Conversation with Saarthi"
        ref={scrollRef} onScroll={onScroll}>
        <div className="transcript-inner">
          {messages.map((m, i) => (
            <div key={i} className={`floater ${m.role}`}>
              {m.content && <div className="floater-text"><ReactMarkdown>{m.content}</ReactMarkdown></div>}
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
            <div className="floater assistant">
              <div className="floater-text typing-dots">
                {statusText && <span className="typing-status">{statusText}</span>}
                <span /><span /><span />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="stage-dock">
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

      {voicePrompt && (
        <div className="modal-overlay" onClick={() => setVoicePrompt(false)}>
          <div className="modal voice-modal" onClick={(e) => e.stopPropagation()}>
            <div className="voice-modal-orb" aria-hidden="true">🎙</div>
            <div className="modal-title">Talk to Saarthi</div>
            <p className="modal-sub">
              Start a live voice conversation? Saarthi will use your microphone and reply out loud —
              just start speaking. Tap her again any time to end the call.
            </p>
            <button className="consent-btn" onClick={startVoice}>Start voice conversation</button>
            <button className="modal-close" onClick={() => setVoicePrompt(false)}>Not now</button>
          </div>
        </div>
      )}
    </div>
  )
}

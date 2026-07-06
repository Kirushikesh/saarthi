import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { useSpeech } from '../useSpeech'
import Avatar from './Avatar'

const GREET = {
  en: (name) => `Namaste ${name.split(' ')[0]}! I'm **Saarthi**, your personal wealth companion. Ask me about your portfolio, goals, or whether you can afford that next big step.`,
  hi: (name) => `नमस्ते ${name.split(' ')[0]}! मैं **सारथी** हूँ, आपका व्यक्तिगत वेल्थ साथी। अपने निवेश, लक्ष्य या किसी बड़े खर्च की योजना के बारे में पूछिए।`,
}

const SUGGESTIONS = {
  individual: {
    en: ['How are my investments doing?', 'Can I afford a ₹50 lakh home loan for 20 years?', 'Where does my money go every month?', 'I want to buy term insurance'],
    hi: ['मेरे निवेश कैसे चल रहे हैं?', 'क्या मैं 20 साल के लिए ₹50 लाख का होम लोन ले सकता हूँ?', 'मेरा पैसा हर महीने कहाँ जाता है?'],
  },
  household: {
    en: ['Can WE afford a ₹80 lakh home loan together?', 'How should we split savings for our home goal?', "What happens if one of us takes a 6-month sabbatical?", 'Show our combined net worth'],
    hi: ['क्या हम मिलकर ₹80 लाख का होम लोन ले सकते हैं?', 'घर के लक्ष्य के लिए बचत कैसे बाँटें?'],
  },
}

export default function Chat({ customer, householdMode, lang, voiceOn, onLead }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const speech = useSpeech(lang)
  const bottomRef = useRef(null)
  const speechRef = useRef(speech)
  speechRef.current = speech

  useEffect(() => {
    setMessages([{ role: 'assistant', content: GREET[lang](customer.name) }])
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

  const mic = () => {
    if (speech.listening) speech.stopListening()
    else speech.listen((text) => send(text))
  }

  const avatarState = speech.speaking ? 'speaking' : speech.listening ? 'listening' : busy ? 'thinking' : 'idle'
  const sugg = SUGGESTIONS[householdMode ? 'household' : 'individual'][lang] || []

  return (
    <div className="chat">
      <div className="chat-avatar-strip">
        <Avatar state={avatarState} size={86} />
        <div className="avatar-status">
          {avatarState === 'speaking' ? (lang === 'hi' ? 'बोल रही हूँ…' : 'Speaking…')
            : avatarState === 'listening' ? (lang === 'hi' ? 'सुन रही हूँ…' : 'Listening…')
            : avatarState === 'thinking' ? (lang === 'hi' ? 'सोच रही हूँ…' : 'Analysing your finances…')
            : householdMode ? 'Humsafar mode · advising your household' : `Advising ${customer.name.split(' ')[0]} · ${customer.risk_profile}`}
        </div>
        {speech.speaking && (
          <button className="chip stop-chip" onClick={speech.stopSpeaking}>◼ Stop voice</button>
        )}
      </div>

      <div className="chat-scroll">
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
        {speech.supported && (
          <button className={`mic ${speech.listening ? 'on' : ''}`} onClick={mic} title="Speak">
            {speech.listening ? '◼' : '🎤'}
          </button>
        )}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={lang === 'hi' ? 'अपना सवाल पूछें…' : 'Ask about your money…'}
        />
        <button className="send" onClick={() => send()} disabled={busy || !input.trim()}>➤</button>
      </div>
    </div>
  )
}

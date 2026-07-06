import { useCallback, useEffect, useRef, useState } from 'react'

const INPUT_SAMPLE_RATE = 16000
const OUTPUT_SAMPLE_RATE = 24000

function floatToPcm16(float32) {
  const out = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

function pcm16ToFloat(int16) {
  const out = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) out[i] = int16[i] / 0x8000
  return out
}

function base64ToArrayBuffer(b64) {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}

function arrayBufferToBase64(buffer) {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

/**
 * Live voice session with the Saarthi voice agent (Gemini Live via ADK).
 * Streams mic PCM up a WebSocket; plays the model's PCM reply; surfaces
 * transcripts, tool activity ("thinking") and RM leads to the caller.
 */
export function useVoiceSession({ onTranscript, onLead }) {
  const [live, setLive] = useState(false)          // session open
  const [speaking, setSpeaking] = useState(false)  // model audio playing
  const [thinking, setThinking] = useState(false)  // brain tool in flight
  const [error, setError] = useState(null)

  const wsRef = useRef(null)
  const micCtxRef = useRef(null)
  const playCtxRef = useRef(null)
  const playerRef = useRef(null)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const speakTimerRef = useRef(null)
  const cbRef = useRef({})
  cbRef.current = { onTranscript, onLead }

  const teardown = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    recorderRef.current?.disconnect()
    playerRef.current?.disconnect()
    micCtxRef.current?.close().catch(() => {})
    playCtxRef.current?.close().catch(() => {})
    clearTimeout(speakTimerRef.current)
    wsRef.current = micCtxRef.current = playCtxRef.current = null
    playerRef.current = recorderRef.current = streamRef.current = null
    setLive(false); setSpeaking(false); setThinking(false)
  }, [])

  const stop = useCallback(() => {
    wsRef.current?.close()
    teardown()
  }, [teardown])

  const start = useCallback(async (customerId, householdMode) => {
    if (wsRef.current) return
    setError(null)
    const base = import.meta.env.VITE_API_URL || window.location.origin
    const wsBase = base.replace(/^http/, 'ws')
    const ws = new WebSocket(`${wsBase}/ws/voice/${customerId}?household=${householdMode}`)
    wsRef.current = ws

    ws.onopen = async () => {
      try {
        // Playback graph (24 kHz)
        const playCtx = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE })
        await playCtx.audioWorklet.addModule('/pcm-player-processor.js')
        const player = new AudioWorkletNode(playCtx, 'pcm-player-processor')
        player.connect(playCtx.destination)
        playCtxRef.current = playCtx
        playerRef.current = player

        // Capture graph (16 kHz)
        const micCtx = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE })
        await micCtx.audioWorklet.addModule('/pcm-recorder-processor.js')
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        })
        const source = micCtx.createMediaStreamSource(stream)
        const recorder = new AudioWorkletNode(micCtx, 'pcm-recorder-processor')
        recorder.port.onmessage = (event) => {
          if (ws.readyState !== WebSocket.OPEN) return
          const pcm16 = floatToPcm16(event.data)
          ws.send(JSON.stringify({ type: 'audio', data: arrayBufferToBase64(pcm16.buffer) }))
        }
        source.connect(recorder)
        micCtxRef.current = micCtx
        recorderRef.current = recorder
        streamRef.current = stream
        setLive(true)
      } catch (e) {
        setError(`Mic setup failed: ${e.message}`)
        ws.close()
      }
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'audio') {
        const pcm = new Int16Array(base64ToArrayBuffer(msg.data))
        playerRef.current?.port.postMessage(pcm16ToFloat(pcm))
        setSpeaking(true)
        setThinking(false)
        // Audio arrives in bursts; fall back to idle shortly after the last chunk.
        clearTimeout(speakTimerRef.current)
        speakTimerRef.current = setTimeout(() => setSpeaking(false), 900)
      } else if (msg.type === 'interrupted') {
        playerRef.current?.port.postMessage('clear')
        setSpeaking(false)
      } else if (msg.type === 'transcript') {
        cbRef.current.onTranscript?.(msg.who, msg.text)
      } else if (msg.type === 'thinking') {
        setThinking(true)
      } else if (msg.type === 'lead') {
        cbRef.current.onLead?.(msg.lead)
      }
    }

    ws.onclose = () => teardown()
    ws.onerror = () => { setError('Voice connection error'); teardown() }
  }, [teardown])

  useEffect(() => stop, [stop])

  return { live, speaking, thinking, error, start, stop }
}

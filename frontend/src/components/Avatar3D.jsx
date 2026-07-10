import { memo, Suspense, useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { useGLTF, useAnimations, useProgress } from '@react-three/drei'

/**
 * Saarthi as a real 3D advisor — a full-body Ready Player Me avatar (Wolf3D
 * meshes, ARKit blendshapes) rendered with react-three-fiber.
 *
 * Drop-in for the old SVG <Avatar>: same { state, levelRef } contract.
 *   state:    idle | listening | speaking | thinking  → body animation
 *   levelRef: mutable ref (0..1) with the CURRENT playback loudness of the
 *             voice. While speaking, `jawOpen` tracks it — the same real
 *             amplitude signal the SVG mouth used (Gemini Live worklet RMS;
 *             browser-TTS word pulses). No viseme/Azure dependency.
 *
 * Body motion (Idle / Talking) comes from a separate animation GLB retargeted
 * to the same skeleton; those clips touch only bones, so our morph-target
 * lip-sync and blink never fight them.
 */

const AVATAR_URL = '/saarthi-avatar.glb'
const ANIM_URL = '/saarthi-anims.glb'
const DRACO_PATH = '/draco/' // local decoder — anims GLB is draco-compressed

// The avatar is uncompressed (no draco); the animations GLB needs the decoder.
useGLTF.preload(AVATAR_URL, false)
useGLTF.preload(ANIM_URL, DRACO_PATH)

function SaarthiModel({ state, levelRef }) {
  const group = useRef()
  const { scene } = useGLTF(AVATAR_URL, false)
  const { animations } = useGLTF(ANIM_URL, DRACO_PATH)
  const { actions } = useAnimations(animations, group)

  // Meshes that carry the face blendshapes (head + teeth + eyes).
  const morphMeshes = useMemo(() => {
    const meshes = []
    scene.traverse((o) => {
      if (!o.isMesh) return
      o.frustumCulled = false
      if (o.morphTargetDictionary && 'jawOpen' in o.morphTargetDictionary) meshes.push(o)
    })
    return meshes
  }, [scene])

  // Re-style the stock avatar into "Saarthi, IDBI wealth advisor": natural dark
  // hair and a professional teal blazer instead of the lavender-hair /
  // leather-jacket default. Material tints multiply the baked textures.
  useEffect(() => {
    scene.traverse((o) => {
      if (!o.isMesh || !o.material) return
      if (o.name === 'Wolf3D_Hair') {
        o.material.color.set('#2a1c11') // dark brown
        o.material.roughness = 0.9
      }
      if (o.name === 'Wolf3D_Outfit_Top') {
        // Kill the glossy "leather" highlights → matte blazer, with a faint teal.
        o.material.color.set('#1c534c')
        o.material.roughness = 1.0
        o.material.metalness = 0.0
        o.material.roughnessMap = null
        o.material.metalnessMap = null
        o.material.needsUpdate = true
      }
      if (o.name === 'Wolf3D_Outfit_Bottom') {
        o.material.color.set('#123b39')
        o.material.roughness = 1.0
        o.material.metalness = 0.0
        o.material.roughnessMap = null
        o.material.metalnessMap = null
        o.material.needsUpdate = true
      }
    })
  }, [scene])

  // Crossfade the body animation with the conversational state.
  useEffect(() => {
    const name = state === 'speaking' ? 'Talking_1' : 'Idle'
    const action = actions[name]
    if (!action) return
    action.reset().fadeIn(0.4).play()
    return () => { action.fadeOut(0.4) }
  }, [state, actions])

  const jaw = useRef(0)
  const blink = useRef({ t: 0, next: 2.5, val: 0, phase: 'wait' })

  useFrame((_, delta) => {
    const dt = Math.min(delta, 0.05)

    // --- lip-sync: jawOpen follows real playback loudness while speaking ---
    const loud = levelRef?.current || 0
    const target = state === 'speaking' ? Math.min(1, loud) : 0
    jaw.current += (target - jaw.current) * Math.min(1, dt * 20)
    // Decay browser-TTS word pulses (the Gemini worklet overwrites levelRef
    // continuously, so this only matters for the SpeechSynthesis fallback).
    if (levelRef && levelRef.current > 0) levelRef.current *= Math.pow(0.9, dt * 60)

    // --- blink: quick close, slower open, then wait a random beat ---
    const b = blink.current
    b.t += dt
    if (b.phase === 'wait') {
      if (b.t >= b.next) { b.phase = 'close'; b.t = 0 }
    } else if (b.phase === 'close') {
      b.val = Math.min(1, b.val + dt / 0.05)
      if (b.val >= 1) b.phase = 'open'
    } else {
      b.val = Math.max(0, b.val - dt / 0.11)
      if (b.val <= 0) { b.phase = 'wait'; b.t = 0; b.next = 2 + Math.random() * 4 }
    }

    const jawV = jaw.current * 0.42
    // A soft resting smile when she isn't talking — warmth, not a blank stare.
    const smileV = state === 'idle' || state === 'listening' ? 0.14 : 0.04
    for (const m of morphMeshes) {
      const d = m.morphTargetDictionary
      const inf = m.morphTargetInfluences
      if (d.jawOpen != null) inf[d.jawOpen] = jawV
      if (d.mouthClose != null) inf[d.mouthClose] = jawV * 0.15
      if (d.eyeBlinkLeft != null) inf[d.eyeBlinkLeft] = b.val
      if (d.eyeBlinkRight != null) inf[d.eyeBlinkRight] = b.val
      if (d.mouthSmileLeft != null) inf[d.mouthSmileLeft] = smileV
      if (d.mouthSmileRight != null) inf[d.mouthSmileRight] = smileV
    }
  })

  // Framed as a head-and-shoulders "figure you talk to". position lifts the
  // full-body model so the face sits at the camera's eye line.
  return <primitive ref={group} object={scene} position={[0, -1.48, 0]} />
}

/** Loading veil shown until the GLBs finish downloading/decoding. */
export function AvatarLoading() {
  const { active, progress } = useProgress()
  if (!active) return null
  return (
    <div className="stage-loading" role="status">
      <div className="stage-spinner" />
      <div className="stage-loading-text">Summoning Saarthi… {Math.round(progress)}%</div>
    </div>
  )
}

function Avatar3D({ state = 'idle', levelRef }) {
  return (
    <Canvas
      className="avatar3d-canvas"
      dpr={[1, 2]}
      gl={{ alpha: true, antialias: true }}
      camera={{ position: [0, 0.02, 1.5], fov: 30, near: 0.1, far: 20 }}
      aria-label={`Saarthi, your advisor — ${state}`}
    >
      {/* soft, warm banking light — no HDRI so it stays fully self-contained */}
      <hemisphereLight args={['#fff6e6', '#20423c', 0.9]} />
      <directionalLight position={[2.5, 4, 3]} intensity={2.1} />
      <directionalLight position={[-3, 2, 1.5]} intensity={0.5} color="#bfe3dd" />
      <directionalLight position={[0, 2.5, -4]} intensity={1.2} color="#ffd98a" />
      <Suspense fallback={null}>
        <SaarthiModel state={state} levelRef={levelRef} />
      </Suspense>
    </Canvas>
  )
}

// Memoized: Chat re-renders on every streamed token, but the heavy WebGL canvas
// only needs to react to `state`/`levelRef` changes.
export default memo(Avatar3D)

import { ref, onUnmounted } from 'vue'
import type { MidiTrack, MidiNote } from './useMidiEditor'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getWaveform(instrument: number, isDrum: boolean): OscillatorType {
  if (isDrum) return 'square'
  if (instrument < 8) return 'sine'       // Piano
  if (instrument < 16) return 'sine'      // Chromatic Percussion
  if (instrument < 24) return 'sine'      // Organ
  if (instrument < 32) return 'sawtooth'  // Guitar
  if (instrument < 40) return 'triangle'  // Bass
  if (instrument < 48) return 'sawtooth'  // Strings
  return 'sine'
}

function pitchToFreq(pitch: number): number {
  return 440 * Math.pow(2, (pitch - 69) / 12)
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useMidiPlayback() {
  // --- Exported reactive state ------------------------------------------------
  const isPlaying = ref(false)
  const currentBeat = ref(0)
  const loopEnabled = ref(false)
  const loopStart = ref(0)
  const loopEnd = ref(0)

  // --- Internal state ---------------------------------------------------------
  let audioContext: AudioContext | null = null
  let tempo = 120
  let tracks: MidiTrack[] = []
  let animationFrameId = 0
  let startTime = 0
  let startBeat = 0
  const scheduledNotes = new Set<string>()

  // --- Internal helpers -------------------------------------------------------

  function ensureAudioContext(): AudioContext {
    if (!audioContext) {
      audioContext = new AudioContext()
    }
    return audioContext
  }

  /** Unique key for a scheduled note so we don't trigger it twice. */
  function noteKey(trackIndex: number, note: MidiNote): string {
    return `${trackIndex}:${note.pitch}:${note.startBeat}`
  }

  function scheduleNote(note: MidiNote, track: MidiTrack, when: number) {
    if (!audioContext) return

    const freq = pitchToFreq(note.pitch)
    const osc = audioContext.createOscillator()
    const gain = audioContext.createGain()

    osc.type = getWaveform(track.instrument, track.isDrum)
    osc.frequency.value = freq

    const volume = (note.velocity / 127) * 0.15
    gain.gain.value = volume

    // Duration in seconds based on current tempo
    const durationSec = note.duration / (tempo / 60)

    // Quick fade-out to avoid clicks
    const fadeStart = Math.max(when, when + durationSec - 0.02)
    gain.gain.setValueAtTime(volume, fadeStart)
    gain.gain.linearRampToValueAtTime(0, when + durationSec)

    osc.connect(gain).connect(audioContext.destination)
    osc.start(when)
    osc.stop(when + durationSec)
  }

  /** Convert a beat position to an audioContext timestamp. */
  function beatToTime(beat: number): number {
    if (!audioContext) return 0
    return startTime + ((beat - startBeat) / (tempo / 60))
  }

  /** Find the beat position that is the furthest any note extends to. */
  function lastBeat(): number {
    let last = 0
    for (const track of tracks) {
      if (track.muted) continue
      for (const note of track.notes) {
        const end = note.startBeat + note.duration
        if (end > last) last = end
      }
    }
    return last
  }

  // --- Animation frame loop ---------------------------------------------------

  function tick() {
    if (!audioContext || !isPlaying.value) return

    const elapsed = audioContext.currentTime - startTime
    let beat = startBeat + elapsed * (tempo / 60)

    // Handle looping
    if (loopEnabled.value && loopEnd.value > loopStart.value && beat >= loopEnd.value) {
      // Jump back to loop start
      startBeat = loopStart.value
      startTime = audioContext.currentTime
      beat = loopStart.value
      scheduledNotes.clear()
    }

    currentBeat.value = beat

    // Look-ahead window in seconds
    const lookAhead = 0.1
    const lookAheadBeat = beat + lookAhead * (tempo / 60)

    // Schedule notes that fall within the look-ahead window
    for (let ti = 0; ti < tracks.length; ti++) {
      const track = tracks[ti]
      if (track.muted) continue
      for (const note of track.notes) {
        if (note.startBeat >= beat && note.startBeat < lookAheadBeat) {
          const key = noteKey(ti, note)
          if (!scheduledNotes.has(key)) {
            scheduledNotes.add(key)
            const when = beatToTime(note.startBeat)
            scheduleNote(note, track, when)
          }
        }
      }
    }

    // If not looping, stop once past all notes
    if (!loopEnabled.value && beat > lastBeat()) {
      stop()
      return
    }

    animationFrameId = requestAnimationFrame(tick)
  }

  // --- Public methods ---------------------------------------------------------

  function setTempo(bpm: number) {
    tempo = bpm
  }

  function setTracks(t: MidiTrack[]) {
    tracks = t
  }

  function play() {
    const ctx = ensureAudioContext()

    startTime = ctx.currentTime
    startBeat = currentBeat.value
    scheduledNotes.clear()

    isPlaying.value = true
    animationFrameId = requestAnimationFrame(tick)
  }

  function pause() {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
    isPlaying.value = false
  }

  function stop() {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
    isPlaying.value = false
    currentBeat.value = 0
    scheduledNotes.clear()
  }

  function seekToBeat(beat: number) {
    currentBeat.value = beat
    scheduledNotes.clear()

    if (isPlaying.value) {
      // Restart playback from the new position
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId)
        animationFrameId = 0
      }
      const ctx = ensureAudioContext()
      startTime = ctx.currentTime
      startBeat = beat
      animationFrameId = requestAnimationFrame(tick)
    }
  }

  function setLoop(start: number, end: number) {
    loopStart.value = start
    loopEnd.value = end
    loopEnabled.value = end > start
  }

  function playNote(pitch: number, velocity = 100, duration = 0.3) {
    const ctx = ensureAudioContext()

    const freq = pitchToFreq(pitch)
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    // Use noise-like square for drums (GM drum range: pitches 27–87 on channel 10,
    // simplified here to pitch < 35 or typical GM drum range)
    const isDrumish = pitch < 35
    osc.type = isDrumish ? 'square' : 'sine'
    osc.frequency.value = freq

    const volume = (velocity / 127) * 0.3
    gain.gain.value = volume

    // Quick fade-out to avoid clicks
    const fadeStart = Math.max(ctx.currentTime, ctx.currentTime + duration - 0.02)
    gain.gain.setValueAtTime(volume, fadeStart)
    gain.gain.linearRampToValueAtTime(0, ctx.currentTime + duration)

    osc.connect(gain).connect(ctx.destination)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + duration)
  }

  // --- Cleanup ----------------------------------------------------------------

  onUnmounted(() => {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
    if (audioContext) {
      audioContext.close()
      audioContext = null
    }
  })

  // --- Return -----------------------------------------------------------------

  return {
    isPlaying,
    currentBeat,
    loopEnabled,
    loopStart,
    loopEnd,
    play,
    pause,
    stop,
    seekToBeat,
    setLoop,
    setTempo,
    setTracks,
    playNote,
  }
}

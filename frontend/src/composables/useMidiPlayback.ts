import { ref, onUnmounted } from 'vue'
import type { MidiTrack, MidiNote } from './useMidiEditor'
import { useSoundFontSynth } from './useSoundFontSynth'

// ---------------------------------------------------------------------------
// Oscillator fallback helpers
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
// Channel assignment: drum → ch9, other tracks → ch 0-8, 10-15
// ---------------------------------------------------------------------------

function assignChannel(trackIndex: number, isDrum: boolean): number {
  if (isDrum) return 9
  // Skip channel 9 for melodic tracks
  if (trackIndex < 9) return trackIndex
  if (trackIndex < 15) return trackIndex + 1
  return trackIndex % 15  // wrap around for 16+ tracks
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
  const activeTimeouts: number[] = []  // ALL scheduled setTimeout ids (noteOn + noteOff)

  // --- SoundFont synth -------------------------------------------------------
  const sfSynth = useSoundFontSynth()
  let sfInitialized = false

  // --- Internal helpers -------------------------------------------------------

  function ensureAudioContext(): AudioContext {
    if (!audioContext) {
      audioContext = new AudioContext()
    }
    return audioContext
  }

  async function ensureSoundFont(): Promise<void> {
    if (sfInitialized) return
    const ctx = ensureAudioContext()
    sfInitialized = await sfSynth.init(ctx)
    if (sfInitialized) {
      // Sync all track programs
      syncTrackPrograms()
    }
  }

  /** Check if a track should be audible (considering mute + solo logic). */
  function isTrackAudible(trackIndex: number): boolean {
    const track = tracks[trackIndex]
    if (!track || track.muted) return false
    const hasSolo = tracks.some(t => t.solo)
    return !hasSolo || track.solo
  }

  function syncTrackPrograms() {
    if (!sfSynth.isLoaded) return
    for (let i = 0; i < tracks.length; i++) {
      const track = tracks[i]
      const ch = assignChannel(i, track.isDrum)
      sfSynth.programSelect(ch, track.instrument, track.isDrum)
      sfSynth.setVolume(ch, isTrackAudible(i) ? (track.volume ?? 100) : 0)
      if (track.pan !== undefined) {
        sfSynth.setPan(ch, track.pan)
      }
    }
  }

  /** Unique key for a scheduled note so we don't trigger it twice. */
  function noteKey(trackIndex: number, note: MidiNote): string {
    return `${trackIndex}:${note.pitch}:${note.start}`
  }

  // --- SoundFont note scheduling ---

  function scheduleSFNote(note: MidiNote, track: MidiTrack, trackIndex: number, when: number) {
    if (!audioContext) return
    const ch = assignChannel(trackIndex, track.isDrum)
    const delay = Math.max(0, (when - audioContext.currentTime) * 1000)
    const durationMs = (note.duration / (tempo / 60)) * 1000

    const onId = window.setTimeout(() => {
      if (!isPlaying.value) return  // guard: don't start note if already stopped
      sfSynth.noteOn(ch, note.pitch, note.velocity)
    }, delay)
    activeTimeouts.push(onId)

    const offId = window.setTimeout(() => {
      sfSynth.noteOff(ch, note.pitch)
    }, delay + durationMs)
    activeTimeouts.push(offId)
  }

  // --- Oscillator fallback note scheduling ---

  function scheduleOscNote(note: MidiNote, track: MidiTrack, when: number) {
    if (!audioContext) return

    const freq = pitchToFreq(note.pitch)
    const osc = audioContext.createOscillator()
    const gain = audioContext.createGain()

    osc.type = getWaveform(track.instrument, track.isDrum)
    osc.frequency.value = freq

    const volume = (note.velocity / 127) * 0.15
    gain.gain.value = volume

    const durationSec = note.duration / (tempo / 60)
    const fadeStart = Math.max(when, when + durationSec - 0.02)
    gain.gain.setValueAtTime(volume, fadeStart)
    gain.gain.linearRampToValueAtTime(0, when + durationSec)

    osc.connect(gain).connect(audioContext.destination)
    osc.start(when)
    osc.stop(when + durationSec)
  }

  function scheduleNote(note: MidiNote, track: MidiTrack, trackIndex: number, when: number) {
    if (sfSynth.isLoaded) {
      scheduleSFNote(note, track, trackIndex, when)
    } else {
      scheduleOscNote(note, track, when)
    }
  }

  /** Convert a beat position to an audioContext timestamp. */
  function beatToTime(beat: number): number {
    if (!audioContext) return 0
    return startTime + ((beat - startBeat) / (tempo / 60))
  }

  /** Find the beat position that is the furthest any note extends to. */
  function lastBeat(): number {
    let last = 0
    for (let i = 0; i < tracks.length; i++) {
      const track = tracks[i]
      if (!isTrackAudible(i)) continue
      for (const note of track.notes) {
        const end = note.start + note.duration
        if (end > last) last = end
      }
    }
    return last
  }

  function clearActiveTimeouts() {
    for (const id of activeTimeouts) {
      clearTimeout(id)
    }
    activeTimeouts.length = 0
  }

  // --- Animation frame loop ---------------------------------------------------

  function tick() {
    if (!audioContext || !isPlaying.value) return

    const elapsed = audioContext.currentTime - startTime
    let beat = startBeat + elapsed * (tempo / 60)

    // Handle looping
    if (loopEnabled.value && loopEnd.value > loopStart.value && beat >= loopEnd.value) {
      startBeat = loopStart.value
      startTime = audioContext.currentTime
      beat = loopStart.value
      scheduledNotes.clear()
      clearActiveTimeouts()
      sfSynth.allNotesOff()
    }

    currentBeat.value = beat

    // Look-ahead window in seconds
    const lookAhead = 0.1
    const lookAheadBeat = beat + lookAhead * (tempo / 60)

    // Schedule notes that fall within the look-ahead window
    for (let ti = 0; ti < tracks.length; ti++) {
      const track = tracks[ti]
      if (!isTrackAudible(ti)) continue
      for (const note of track.notes) {
        if (note.start >= beat && note.start < lookAheadBeat) {
          const key = noteKey(ti, note)
          if (!scheduledNotes.has(key)) {
            scheduledNotes.add(key)
            const when = beatToTime(note.start)
            scheduleNote(note, track, ti, when)
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
    syncTrackPrograms()
  }

  async function play() {
    const ctx = ensureAudioContext()

    // Try to initialize SoundFont (non-blocking if already done)
    await ensureSoundFont()

    startTime = ctx.currentTime
    startBeat = currentBeat.value
    scheduledNotes.clear()
    clearActiveTimeouts()

    isPlaying.value = true
    animationFrameId = requestAnimationFrame(tick)
  }

  function pause() {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
    isPlaying.value = false
    clearActiveTimeouts()
    sfSynth.allNotesOff()
  }

  function stop() {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
    isPlaying.value = false
    currentBeat.value = 0
    scheduledNotes.clear()
    clearActiveTimeouts()
    sfSynth.allNotesOff()
  }

  function seekToBeat(beat: number) {
    currentBeat.value = beat
    scheduledNotes.clear()
    clearActiveTimeouts()
    sfSynth.allNotesOff()

    if (isPlaying.value) {
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

  function playNote(pitch: number, velocity = 100, duration = 0.3, trackIndex = 0) {
    const ctx = ensureAudioContext()

    if (sfSynth.isLoaded) {
      const track = tracks[trackIndex]
      const ch = track ? assignChannel(trackIndex, track.isDrum) : 0
      sfSynth.noteOn(ch, pitch, velocity)
      setTimeout(() => {
        sfSynth.noteOff(ch, pitch)
      }, duration * 1000)
      return
    }

    // Oscillator fallback — use track instrument for waveform if available
    const track = tracks[trackIndex]
    const freq = pitchToFreq(pitch)
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    osc.type = track ? getWaveform(track.instrument, track.isDrum) : 'sine'
    osc.frequency.value = freq

    const volume = (velocity / 127) * 0.3
    gain.gain.value = volume

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
    clearActiveTimeouts()
    sfSynth.dispose()
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

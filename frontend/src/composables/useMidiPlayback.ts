import { ref, onUnmounted } from 'vue'
import * as Tone from 'tone'
import type { MidiTrack } from './useMidiEditor'
import { useToneSynth } from './useToneSynth'

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
  let tempo = 120
  let tracks: MidiTrack[] = []
  let animationFrameId = 0

  // --- Tone.js synth ----------------------------------------------------------
  const synth = useToneSynth()

  // --- Internal helpers -------------------------------------------------------

  /** Convert beats to seconds at current tempo. */
  function beatsToSeconds(beats: number): number {
    return beats * (60 / tempo)
  }

  /** Check if a track should be audible (considering mute + solo logic). */
  function isTrackAudible(trackIndex: number): boolean {
    const track = tracks[trackIndex]
    if (!track || track.muted) return false
    const hasSolo = tracks.some(t => t.solo)
    return !hasSolo || track.solo
  }

  /** Find the beat position that is the furthest any note extends to. */
  function lastBeat(): number {
    let last = 0
    for (let i = 0; i < tracks.length; i++) {
      const track = tracks[i]
      for (const note of track.notes) {
        const end = note.start + note.duration
        if (end > last) last = end
      }
    }
    return last
  }

  /** Sync volume and pan for all tracks via synth channels. */
  function syncTrackMixing() {
    for (let i = 0; i < tracks.length; i++) {
      const track = tracks[i]
      const audible = isTrackAudible(i)
      synth.setTrackVolume(i, track.volume ?? 100, !audible)
      if (track.pan !== undefined) {
        synth.setTrackPan(i, track.pan)
      }
    }
  }

  /** Pre-load per-track samplers. */
  async function preloadInstruments(): Promise<void> {
    const promises: Promise<unknown>[] = []

    for (let i = 0; i < tracks.length; i++) {
      const track = tracks[i]
      promises.push(synth.loadTrackSampler(i, track.instrument, track.isDrum))
    }

    await Promise.all(promises)
  }

  /**
   * Cancel all Transport events and schedule all notes from scratch.
   * Uses Tone.Transport.schedule() to fire noteOn/noteOff at the correct time.
   */
  function scheduleAllNotes() {
    Tone.getTransport().cancel()

    const total = lastBeat()

    for (let ti = 0; ti < tracks.length; ti++) {
      if (!isTrackAudible(ti)) continue
      const track = tracks[ti]

      for (const note of track.notes) {
        if (note.start < 0 || note.start >= total) continue

        const noteOnTime = beatsToSeconds(note.start)
        const noteOffTime = beatsToSeconds(note.start + note.duration)
        const trackIndex = ti
        const { pitch, velocity } = note
        const { instrument, isDrum } = track

        // Schedule noteOn (pass time from Transport for sample-accurate timing)
        Tone.getTransport().schedule((time) => {
          synth.noteOnAt(trackIndex, pitch, velocity, instrument, isDrum, time)
        }, noteOnTime)

        // Schedule noteOff
        Tone.getTransport().schedule((time) => {
          synth.noteOffAt(trackIndex, pitch, instrument, isDrum, time)
        }, noteOffTime)
      }
    }

    // Schedule stop at end of song (only when not looping)
    if (!loopEnabled.value) {
      const endTime = beatsToSeconds(total)
      Tone.getTransport().schedule((_time) => {
        // Use setTimeout to defer Vue reactive state update outside Tone's audio thread
        setTimeout(() => stop(), 0)
      }, endTime)
    }
  }

  // --- Beat tracking via requestAnimationFrame --------------------------------

  function startBeatTracking() {
    if (animationFrameId) return

    function tick() {
      if (!isPlaying.value) return

      // Tone.Transport.seconds is the current playhead position in seconds
      const seconds = Tone.getTransport().seconds
      currentBeat.value = seconds / (60 / tempo)

      animationFrameId = requestAnimationFrame(tick)
    }

    animationFrameId = requestAnimationFrame(tick)
  }

  function stopBeatTracking() {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
  }

  // --- Public methods ---------------------------------------------------------

  function setTempo(bpm: number) {
    tempo = bpm
    Tone.getTransport().bpm.value = bpm
  }

  function setTracks(t: MidiTrack[]) {
    tracks = t
    syncTrackMixing()
  }

  async function play() {
    // Init Tone.js (requires user gesture; safe to call multiple times)
    await synth.init()

    // Set tempo on Transport
    Tone.getTransport().bpm.value = tempo

    // Configure loop
    if (loopEnabled.value && loopEnd.value > loopStart.value) {
      Tone.getTransport().loop = true
      Tone.getTransport().loopStart = beatsToSeconds(loopStart.value)
      Tone.getTransport().loopEnd = beatsToSeconds(loopEnd.value)
    } else {
      Tone.getTransport().loop = false
    }

    // Pre-load all instruments, then schedule notes
    await preloadInstruments()
    scheduleAllNotes()

    // Sync mixing
    syncTrackMixing()

    isPlaying.value = true
    Tone.getTransport().start()
    startBeatTracking()
  }

  function pause() {
    Tone.getTransport().pause()
    isPlaying.value = false
    stopBeatTracking()
    synth.allNotesOff()
  }

  function stop() {
    Tone.getTransport().stop()
    Tone.getTransport().cancel()
    isPlaying.value = false
    currentBeat.value = 0
    stopBeatTracking()
    synth.allNotesOff()
  }

  function seekToBeat(beat: number) {
    const wasPlaying = isPlaying.value

    if (wasPlaying) {
      Tone.getTransport().pause()
      stopBeatTracking()
    }

    synth.allNotesOff()

    const seekSeconds = beatsToSeconds(beat)
    Tone.getTransport().seconds = seekSeconds
    currentBeat.value = beat

    if (wasPlaying) {
      // Reschedule from new position
      scheduleAllNotes()
      Tone.getTransport().start()
      startBeatTracking()
    }
  }

  function setLoop(start: number, end: number) {
    loopStart.value = start
    loopEnd.value = end
    loopEnabled.value = end > start

    if (loopEnabled.value) {
      Tone.getTransport().loop = true
      Tone.getTransport().loopStart = beatsToSeconds(start)
      Tone.getTransport().loopEnd = beatsToSeconds(end)
    } else {
      Tone.getTransport().loop = false
    }
  }

  /**
   * Play a single note preview (e.g. piano roll key click).
   * Uses setTimeout for noteOff since this is a one-shot preview, not Transport-scheduled.
   */
  async function playNote(pitch: number, velocity = 100, duration = 0.3, trackIndex = 0) {
    await synth.init()
    const track = tracks[trackIndex]
    const program = track?.instrument ?? 0
    const isDrum = track?.isDrum ?? false

    await synth.loadTrackSampler(trackIndex, program, isDrum)
    synth.noteOn(trackIndex, pitch, velocity, program, isDrum)
    setTimeout(() => {
      synth.noteOff(trackIndex, pitch, program, isDrum)
    }, duration * 1000)
  }

  // --- Cleanup ----------------------------------------------------------------

  onUnmounted(() => {
    stopBeatTracking()
    Tone.getTransport().stop()
    Tone.getTransport().cancel()
    synth.dispose()
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

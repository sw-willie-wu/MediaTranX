/**
 * useToneSynth — singleton composable for Tone.js instrument loading and effects chain.
 *
 * Architecture:
 *   Tone.Sampler (per instrument)
 *     → Tone.Channel (per track, volume/pan/mute)
 *       → masterChannel
 *         → EQ (Tone.EQ3)
 *           → Compressor (Tone.Compressor)
 *             → Delay (Tone.FeedbackDelay)
 *               → Reverb (Tone.Reverb)
 *                 → Destination
 *
 * Sampler pool keys:
 *   'drum'       — GM percussion (channel 9)
 *   'inst_N'     — melodic instrument, program N (e.g. 'inst_0' = acoustic grand piano)
 */

import { ref, reactive } from 'vue'
import * as Tone from 'tone'
import { GM_SOUNDFONT_NAMES, GM_DRUM_SOUNDFONT_NAME } from '@/constants/gmSoundfontNames'
import { getApiBase } from './useApi'

// ── Interpolation note set (every minor third, A0 → C8) ────────────────────

function buildNoteSet(): string[] {
  const notes: string[] = []
  // Start from A0
  notes.push('A0')
  // C1 upward, cycling Eb/Gb/A/C per octave group
  const sequence: Array<{ name: string; octave: number }> = []
  for (let oct = 1; oct <= 7; oct++) {
    sequence.push({ name: 'C', octave: oct })
    sequence.push({ name: 'Eb', octave: oct })
    sequence.push({ name: 'Gb', octave: oct })
    sequence.push({ name: 'A', octave: oct })
  }
  // C8 is the last note on a standard piano
  sequence.push({ name: 'C', octave: 8 })

  for (const { name, octave } of sequence) {
    notes.push(`${name}${octave}`)
  }
  return notes
}

const SAMPLE_NOTES = buildNoteSet()

// ── MIDI conversion helpers ─────────────────────────────────────────────────

/** MIDI volume (0-127) → dB */
function midiVolumeToDB(volume: number): number {
  return (volume / 127) * 60 - 60
}

/** MIDI pan (0-127) → -1..+1 */
function midiPanToFloat(pan: number): number {
  return (pan - 64) / 64
}

// ── Module-level singleton state ────────────────────────────────────────────

const _isInitialized = ref(false)

// Sampler pool: 'drum' | 'inst_N' → Tone.Sampler
const _samplers = new Map<string, Tone.Sampler>()

// Per-track mixing: gain + panner
interface TrackMixer {
  gain: Tone.Gain
  panner: Tone.Panner
  muted: boolean
  rawVolume: number // dB before mute
}
const _trackMixers = new Map<number, TrackMixer>()

// Master channel and effects nodes (created on init)
let _masterChannel: Tone.Channel | null = null
let _eq: Tone.EQ3 | null = null
let _compressor: Tone.Compressor | null = null
let _delay: Tone.FeedbackDelay | null = null
let _reverb: Tone.Reverb | null = null

// In-progress init promise (prevents double-init)
let _initPromise: Promise<boolean> | null = null

// Soundfonts path cache
let _soundfontsPath: string | null = null
let _soundfontsAvailable = false

// ── Reactive effects state (module-level, importable directly) ──────────────

export const effectsState = reactive({
  eq: {
    low: 0,
    mid: 0,
    high: 0,
  },
  compressor: {
    threshold: -24,
    ratio: 4,
  },
  delay: {
    time: 0.25,
    feedback: 0.3,
    wet: 0,
  },
  reverb: {
    decay: 1.5,
    wet: 0.15,
  },
})

// ── Internal helpers ────────────────────────────────────────────────────────

async function _fetchSoundfontsInfo(): Promise<{ path: string; exists: boolean }> {
  try {
    const resp = await fetch(`${getApiBase()}/audio/soundfonts/info`)
    if (!resp.ok) return { path: '', exists: false }
    return await resp.json()
  } catch {
    return { path: '', exists: false }
  }
}

/**
 * Load a single MP3 sample for a given instrument directory + note name.
 * Prefers Electron's readLocalFile; falls back to backend HTTP API.
 * Returns a blob URL string, or null if the file doesn't exist.
 */
async function _loadSampleUrl(dirName: string, note: string): Promise<string | null> {
  const electron = (window as any).electron

  if (_soundfontsPath && electron?.readLocalFile) {
    // Electron path: {soundfontsPath}/{dirName}/{note}.mp3
    const filePath = `${_soundfontsPath}/${dirName}/${note}.mp3`
    try {
      const data: Uint8Array = await electron.readLocalFile(filePath)
      const blob = new Blob([data], { type: 'audio/mp3' })
      return URL.createObjectURL(blob)
    } catch {
      // File doesn't exist for this note — skip
      return null
    }
  }

  // HTTP fallback
  const url = `${getApiBase()}/audio/soundfonts/sample/${dirName}/${note}.mp3`
  try {
    const resp = await fetch(url, { method: 'HEAD' })
    if (!resp.ok) return null
    // Return the URL directly — Tone.Sampler can fetch it
    return url
  } catch {
    return null
  }
}

/**
 * Build the samples map for a Tone.Sampler by probing available notes.
 * Only includes notes that actually exist in the soundfont directory.
 */
async function _buildSamplesMap(dirName: string): Promise<Record<string, string>> {
  const samples: Record<string, string> = {}

  await Promise.all(
    SAMPLE_NOTES.map(async (note) => {
      const url = await _loadSampleUrl(dirName, note)
      if (url) {
        samples[note] = url
      }
    })
  )

  return samples
}

/**
 * Build samples map for GM drum kit (WebAudioFont).
 * Drum samples are stored as {midiNote}.mp3 (e.g., 35.mp3 = kick, 38.mp3 = snare).
 */
async function _buildDrumSamplesMap(): Promise<Record<string, string>> {
  const samples: Record<string, string> = {}
  const dirName = `${GM_DRUM_SOUNDFONT_NAME}-mp3`

  await Promise.all(
    Array.from({ length: 81 - 35 + 1 }, (_, i) => i + 35).map(async (midiNote) => {
      const url = await _loadSampleUrl(dirName, String(midiNote))
      if (url) {
        // Convert MIDI note number to note name for Tone.Sampler
        const noteName = Tone.Frequency(midiNote, 'midi').toNote()
        samples[noteName] = url
      }
    })
  )

  return samples
}

/**
 * Create per-track gain + panner chain, connected to masterChannel.
 * Uses Tone.Gain + Tone.Panner instead of Tone.Channel (Channel→Channel doesn't route audio).
 */
function _createTrackMixer(trackIndex: number): TrackMixer {
  const gain = new Tone.Gain(1)
  const panner = new Tone.Panner(0)

  // Chain: input → panner → gain → (connected later when init is done)
  panner.connect(gain)
  _connectMixerToEffects(gain)

  const mixer: TrackMixer = { gain, panner, muted: false, rawVolume: 0 }
  _trackMixers.set(trackIndex, mixer)
  return mixer
}

/** Connect a gain node to the effects chain (or do nothing if not yet initialized). */
function _connectMixerToEffects(gain: Tone.Gain): void {
  if (_eq) {
    gain.connect(_eq)
  }
}

/** Reconnect all existing track mixers to the effects chain (called after init). */
function _reconnectAllMixers(): void {
  for (const mixer of _trackMixers.values()) {
    _connectMixerToEffects(mixer.gain)
  }
}

// ── Public composable ───────────────────────────────────────────────────────

export function useToneSynth() {
  /**
   * Initialize AudioContext and create the master effects chain.
   * Safe to call multiple times — returns cached promise.
   */
  async function init(): Promise<boolean> {
    if (_isInitialized.value) return true
    if (_initPromise) return _initPromise

    _initPromise = _doInit()
    const result = await _initPromise
    if (!result) {
      // Allow retry on next call
      _initPromise = null
    }
    return result
  }

  // Cache of sample URL maps by instrument key (avoids re-fetching files)
  const _samplesMaps = new Map<string, Record<string, string>>()

  /**
   * Get (or build) the samples URL map for a given instrument.
   */
  async function _getSamplesMap(program: number, isDrum: boolean): Promise<Record<string, string> | null> {
    const key = isDrum ? 'drum' : `inst_${program}`
    if (_samplesMaps.has(key)) return _samplesMaps.get(key)!

    const dirName = isDrum ? GM_DRUM_SOUNDFONT_NAME : GM_SOUNDFONT_NAMES[program]
    if (!dirName) return null
    if (!_soundfontsAvailable) return null

    const samplesMap = isDrum
      ? await _buildDrumSamplesMap()
      : await _buildSamplesMap(`${dirName}-mp3`)
    if (Object.keys(samplesMap).length === 0) return null

    _samplesMaps.set(key, samplesMap)
    return samplesMap
  }

  /**
   * Load (or return cached) per-track Tone.Sampler.
   * Each track gets its own sampler → channel → masterChannel for independent volume/pan/mute.
   */
  async function loadTrackSampler(trackIndex: number, program: number, isDrum: boolean): Promise<Tone.Sampler | null> {
    if (!_isInitialized.value) {
      const ok = await init()
      if (!ok) return null
    }

    const trackKey = `track_${trackIndex}`

    // Return cached sampler for this track
    if (_samplers.has(trackKey)) return _samplers.get(trackKey)!

    const samplesMap = await _getSamplesMap(program, isDrum)
    if (!samplesMap) return null

    try {
      const sampler = new Tone.Sampler({ urls: { ...samplesMap } })
      await Tone.loaded()

      // Connect: sampler → per-track gain/pan → masterChannel
      const ch = getChannel(trackIndex)
      sampler.connect(ch)

      _samplers.set(trackKey, sampler)
      return sampler
    } catch (err) {
      console.error(`[ToneSynth] Failed to load instrument for track ${trackIndex} (program=${program}, isDrum=${isDrum}):`, err)
      return null
    }
  }

  /**
   * Get (or create) the per-track mixer. Returns the panner (input node for samplers).
   */
  function getChannel(trackIndex: number): Tone.Panner {
    const mixer = _trackMixers.get(trackIndex) ?? _createTrackMixer(trackIndex)
    return mixer.panner
  }

  /**
   * Set track volume and mute state.
   * volume: MIDI 0-127
   */
  function setTrackVolume(trackIndex: number, volume: number, muted: boolean): void {
    const mixer = _trackMixers.get(trackIndex) ?? _createTrackMixer(trackIndex)
    const db = midiVolumeToDB(volume)
    mixer.rawVolume = db
    mixer.muted = muted
    mixer.gain.gain.value = muted ? 0 : Math.pow(10, db / 20) // dB to linear gain
  }

  /**
   * Set track pan.
   * pan: MIDI 0-127 (64 = center)
   */
  function setTrackPan(trackIndex: number, pan: number): void {
    const mixer = _trackMixers.get(trackIndex) ?? _createTrackMixer(trackIndex)
    mixer.panner.pan.value = midiPanToFloat(pan)
  }

  /**
   * Trigger a note-on event (async — loads sampler if needed).
   */
  async function noteOn(
    trackIndex: number,
    pitch: number,
    velocity: number,
    program: number,
    isDrum: boolean
  ): Promise<void> {
    const sampler = await loadTrackSampler(trackIndex, program, isDrum)
    if (!sampler) return

    const noteName = Tone.Frequency(pitch, 'midi').toNote()
    sampler.triggerAttack(noteName, Tone.now(), velocity / 127)
  }

  /**
   * Trigger a note-on at a specific time (for Transport scheduling).
   * Synchronous — track sampler must already be loaded via loadTrackSampler().
   */
  function noteOnAt(
    trackIndex: number,
    pitch: number,
    velocity: number,
    _program: number,
    _isDrum: boolean,
    time: number
  ): void {
    const sampler = _samplers.get(`track_${trackIndex}`)
    if (!sampler) return

    const noteName = Tone.Frequency(pitch, 'midi').toNote()
    sampler.triggerAttack(noteName, time, velocity / 127)
  }

  /**
   * Trigger a note-off at a specific time (for Transport scheduling).
   */
  function noteOffAt(
    trackIndex: number,
    pitch: number,
    _program: number,
    _isDrum: boolean,
    time: number
  ): void {
    const sampler = _samplers.get(`track_${trackIndex}`)
    if (!sampler) return

    const noteName = Tone.Frequency(pitch, 'midi').toNote()
    sampler.triggerRelease(noteName, time)
  }

  /**
   * Trigger a note-off event.
   */
  async function noteOff(
    trackIndex: number,
    pitch: number,
    program: number,
    isDrum: boolean
  ): Promise<void> {
    const sampler = _samplers.get(`track_${trackIndex}`)
    if (!sampler) return

    const noteName = Tone.Frequency(pitch, 'midi').toNote()
    sampler.triggerRelease(noteName, Tone.now())
  }

  /**
   * Send note-off to all loaded samplers.
   */
  function allNotesOff(): void {
    for (const sampler of _samplers.values()) {
      try {
        sampler.releaseAll()
      } catch {
        // Ignore errors during cleanup
      }
    }
  }

  /**
   * Update effects parameters and apply to active nodes.
   */
  function updateEffects(params: {
    eq?: Partial<typeof effectsState.eq>
    compressor?: Partial<typeof effectsState.compressor>
    delay?: Partial<typeof effectsState.delay>
    reverb?: Partial<typeof effectsState.reverb>
  }): void {
    if (params.eq) {
      Object.assign(effectsState.eq, params.eq)
      if (_eq) {
        if (params.eq.low !== undefined) _eq.low.value = params.eq.low
        if (params.eq.mid !== undefined) _eq.mid.value = params.eq.mid
        if (params.eq.high !== undefined) _eq.high.value = params.eq.high
      }
    }
    if (params.compressor) {
      Object.assign(effectsState.compressor, params.compressor)
      if (_compressor) {
        if (params.compressor.threshold !== undefined)
          (_compressor.threshold as Tone.Param<'decibels'>).value = params.compressor.threshold
        if (params.compressor.ratio !== undefined)
          (_compressor.ratio as Tone.Param<'positive'>).value = params.compressor.ratio
      }
    }
    if (params.delay) {
      Object.assign(effectsState.delay, params.delay)
      if (_delay) {
        if (params.delay.time !== undefined) _delay.delayTime.value = params.delay.time
        if (params.delay.feedback !== undefined)
          (_delay.feedback as Tone.Param<'normalRange'>).value = params.delay.feedback
        if (params.delay.wet !== undefined) _delay.wet.value = params.delay.wet
      }
    }
    if (params.reverb) {
      Object.assign(effectsState.reverb, params.reverb)
      if (_reverb) {
        if (params.reverb.decay !== undefined) _reverb.decay = params.reverb.decay
        if (params.reverb.wet !== undefined) _reverb.wet.value = params.reverb.wet
      }
    }
  }

  /**
   * Dispose all Tone nodes and reset singleton state.
   */
  function dispose(): void {
    allNotesOff()

    for (const sampler of _samplers.values()) {
      try { sampler.dispose() } catch { /* ignore */ }
    }
    _samplers.clear()

    for (const mixer of _trackMixers.values()) {
      try { mixer.gain.dispose() } catch { /* ignore */ }
      try { mixer.panner.dispose() } catch { /* ignore */ }
    }
    _trackMixers.clear()
    _samplesMaps.clear()

    if (_reverb) { try { _reverb.dispose() } catch { /* ignore */ } ; _reverb = null }
    if (_delay) { try { _delay.dispose() } catch { /* ignore */ } ; _delay = null }
    if (_compressor) { try { _compressor.dispose() } catch { /* ignore */ } ; _compressor = null }
    if (_eq) { try { _eq.dispose() } catch { /* ignore */ } ; _eq = null }
    if (_masterChannel) { try { _masterChannel.dispose() } catch { /* ignore */ } ; _masterChannel = null }

    _isInitialized.value = false
    _initPromise = null
    _soundfontsPath = null
    _soundfontsAvailable = false
  }

  return {
    isInitialized: _isInitialized,
    effectsState,
    init,
    loadTrackSampler,
    getChannel,
    setTrackVolume,
    setTrackPan,
    noteOn,
    noteOnAt,
    noteOff,
    noteOffAt,
    allNotesOff,
    updateEffects,
    dispose,
  }
}

// ── Internal init ───────────────────────────────────────────────────────────

async function _doInit(): Promise<boolean> {
  try {
    // Start AudioContext (Tone.start() requires user gesture; caller should handle that)
    await Tone.start()

    // Fetch soundfonts info from backend
    const info = await _fetchSoundfontsInfo()
    _soundfontsAvailable = info.exists
    _soundfontsPath = info.path ?? null

    // Build master effects chain:
    //   masterChannel → EQ → Compressor → Delay → Reverb → Destination

    _reverb = new Tone.Reverb({
      decay: effectsState.reverb.decay,
      wet: effectsState.reverb.wet,
    })
    await _reverb.ready  // wait for reverb IR to generate

    _delay = new Tone.FeedbackDelay({
      delayTime: effectsState.delay.time,
      feedback: effectsState.delay.feedback,
      wet: effectsState.delay.wet,
    })

    _compressor = new Tone.Compressor({
      threshold: effectsState.compressor.threshold,
      ratio: effectsState.compressor.ratio,
    })

    _eq = new Tone.EQ3({
      low: effectsState.eq.low,
      mid: effectsState.eq.mid,
      high: effectsState.eq.high,
    })

    _masterChannel = new Tone.Channel()

    // Connect chain: masterChannel → EQ → Compressor → Delay → Reverb → Destination
    _masterChannel.connect(_eq)
    _eq.connect(_compressor)
    _compressor.connect(_delay)
    _delay.connect(_reverb)
    _reverb.toDestination()

    // Reconnect any track mixers created before init
    _reconnectAllMixers()

    _isInitialized.value = true
    return true
  } catch (err) {
    console.error('[ToneSynth] init failed:', err)
    _isInitialized.value = false
    return false
  }
}

/**
 * SoundFont synthesizer singleton — wraps js-synthesizer (FluidSynth WASM)
 * for real-time MIDI playback with GM instrument sounds.
 *
 * SF2 loading priority:
 *   1. Electron: window.electron.readLocalFile(path) — direct disk read
 *   2. Web dev:  fetch /api/audio/soundfont/download  — HTTP fallback
 */

import { getApiBase } from './useApi'

// ── Module-level singleton state ──

let synth: any = null          // js-synthesizer Synthesizer instance
let audioNode: AudioNode | null = null
let sfontId = -1
let _isLoaded = false
let _isLoading = false
let _initPromise: Promise<boolean> | null = null
let _audioContext: AudioContext | null = null

// ── Public API ──

export function useSoundFontSynth() {
  /**
   * Initialize the synthesizer and load the SoundFont.
   * Safe to call multiple times — returns cached promise if already loading/loaded.
   */
  async function init(audioContext: AudioContext): Promise<boolean> {
    if (_isLoaded && _audioContext === audioContext) return true
    if (_isLoading && _initPromise) return _initPromise

    _isLoading = true
    _initPromise = _doInit(audioContext)
    const result = await _initPromise
    _isLoading = false
    return result
  }

  function programSelect(channel: number, program: number, isDrum: boolean) {
    if (!synth || !_isLoaded) return
    if (isDrum) {
      synth.midiSetChannelType(channel, true)
    }
    // GM: bank 0 for melodic, bank 128 for drums
    const bank = isDrum ? 128 : 0
    synth.midiProgramSelect(channel, sfontId, bank, program)
  }

  function noteOn(channel: number, pitch: number, velocity: number) {
    if (!synth || !_isLoaded) return
    synth.midiNoteOn(channel, pitch, velocity)
  }

  function noteOff(channel: number, pitch: number) {
    if (!synth || !_isLoaded) return
    synth.midiNoteOff(channel, pitch)
  }

  function setVolume(channel: number, volume: number) {
    if (!synth || !_isLoaded) return
    // CC7 = channel volume, value already 0-127
    synth.midiControl(channel, 7, Math.max(0, Math.min(127, Math.round(volume))))
  }

  function setPan(channel: number, pan: number) {
    if (!synth || !_isLoaded) return
    // CC10 = pan (0=left, 64=center, 127=right), value already 0-127
    synth.midiControl(channel, 10, Math.max(0, Math.min(127, Math.round(pan))))
  }

  function allNotesOff() {
    if (!synth || !_isLoaded) return
    for (let ch = 0; ch < 16; ch++) {
      synth.midiAllNotesOff(ch)
      synth.midiAllSoundsOff(ch)
    }
  }

  function dispose() {
    if (synth) {
      try {
        allNotesOff()
        synth.close()
      } catch { /* ignore */ }
      synth = null
    }
    if (audioNode) {
      try { audioNode.disconnect() } catch { /* ignore */ }
      audioNode = null
    }
    sfontId = -1
    _isLoaded = false
    _isLoading = false
    _initPromise = null
    _audioContext = null
  }

  return {
    get isLoaded() { return _isLoaded },
    get isLoading() { return _isLoading },
    init,
    programSelect,
    noteOn,
    noteOff,
    setVolume,
    setPan,
    allNotesOff,
    dispose,
  }
}

// ── Internal ──

let _wasmLoaded = false

/** Load libfluidsynth WASM module via script tag (once). */
function _loadWasmModule(): Promise<void> {
  if (_wasmLoaded) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = new URL('/libfluidsynth.js', window.location.origin).href
    script.onload = () => { _wasmLoaded = true; resolve() }
    script.onerror = () => reject(new Error('Failed to load libfluidsynth WASM module'))
    document.head.appendChild(script)
  })
}

async function _doInit(audioContext: AudioContext): Promise<boolean> {
  try {
    // 1. Load libfluidsynth WASM module (sets global Module)
    await _loadWasmModule()

    // 2. Import js-synthesizer and wait for WASM ready
    const JSSynth = await import('js-synthesizer')
    await JSSynth.waitForReady()

    // Create synthesizer
    const s = new JSSynth.Synthesizer()
    s.init(audioContext.sampleRate)

    // Load SoundFont binary
    const sf2Data = await _loadSF2()
    if (!sf2Data) {
      s.close()
      return false
    }

    sfontId = await s.loadSFont(sf2Data)

    // Create ScriptProcessor audio node and connect to destination
    audioNode = s.createAudioNode(audioContext, 8192)
    audioNode.connect(audioContext.destination)

    synth = s
    _audioContext = audioContext
    _isLoaded = true
    return true
  } catch (err) {
    console.error('[SoundFontSynth] init failed:', err)
    _isLoaded = false
    return false
  }
}

async function _loadSF2(): Promise<ArrayBuffer | null> {
  try {
    // 1. Ask backend for SF2 path
    const infoResp = await fetch(getApiBase() + '/audio/soundfont/info')
    if (!infoResp.ok) return null
    const info = await infoResp.json()
    if (!info.exists) return null

    // 2. Prefer local file read (Electron)
    if (info.path && (window as any).electron?.readLocalFile) {
      const buffer: Uint8Array = await (window as any).electron.readLocalFile(info.path)
      return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength)
    }

    // 3. Fallback: HTTP stream
    const resp = await fetch(getApiBase() + '/audio/soundfont/download')
    if (!resp.ok) return null
    return await resp.arrayBuffer()
  } catch (err) {
    console.error('[SoundFontSynth] SF2 load failed:', err)
    return null
  }
}

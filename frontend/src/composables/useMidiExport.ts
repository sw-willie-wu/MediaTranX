/**
 * useMidiExport — offline rendering of MIDI tracks to audio files.
 *
 * Uses Tone.Offline to render all MIDI tracks with effects into a WAV
 * AudioBuffer, then either saves directly (WAV) or uploads to backend
 * for FFmpeg conversion (MP3/FLAC/OGG/AAC).
 *
 * Architecture:
 *   Tone.Offline context:
 *     New Tone.Sampler instances (per instrument, isolated from live context)
 *       → New Tone.Channel (per track, volume/pan)
 *         → masterChannel
 *           → EQ3 → Compressor → FeedbackDelay → Reverb → Destination
 *   ResultingAudioBuffer → WAV encode → save or upload
 */

import { ref } from 'vue'
import * as Tone from 'tone'
import { useI18n } from 'vue-i18n'
import { useToast } from './useToast'
import { effectsState } from './useToneSynth'
import { apiFetch, getApiBase } from './useApi'
import { GM_SOUNDFONT_NAMES, GM_DRUM_SOUNDFONT_NAME } from '@/constants/gmSoundfontNames'
import { useTaskStore } from '@/stores/tasks'
import type { MidiTrack } from './useMidiEditor'

// ── Note set (same as useToneSynth) ────────────────────────────────────────

function buildNoteSet(): string[] {
  const notes: string[] = []
  notes.push('A0')
  const sequence: Array<{ name: string; octave: number }> = []
  for (let oct = 1; oct <= 7; oct++) {
    sequence.push({ name: 'C', octave: oct })
    sequence.push({ name: 'Eb', octave: oct })
    sequence.push({ name: 'Gb', octave: oct })
    sequence.push({ name: 'A', octave: oct })
  }
  sequence.push({ name: 'C', octave: 8 })
  for (const { name, octave } of sequence) {
    notes.push(`${name}${octave}`)
  }
  return notes
}

const SAMPLE_NOTES = buildNoteSet()

// ── MIDI conversion helpers ─────────────────────────────────────────────────

function midiVolumeToDB(volume: number): number {
  return (volume / 127) * 60 - 60
}

function midiPanToFloat(pan: number): number {
  return (pan - 64) / 64
}

// ── Sample URL loading (mirrors useToneSynth._loadSampleUrl) ────────────────

async function _fetchSoundfontsInfo(): Promise<{ path: string; exists: boolean }> {
  try {
    const resp = await fetch(`${getApiBase()}/audio/soundfonts/info`)
    if (!resp.ok) return { path: '', exists: false }
    return await resp.json()
  } catch {
    return { path: '', exists: false }
  }
}

async function _loadSampleUrl(
  soundfontsPath: string | null,
  dirName: string,
  note: string,
): Promise<string | null> {
  const electron = (window as any).electron

  if (soundfontsPath && electron?.readLocalFile) {
    const filePath = `${soundfontsPath}/${dirName}/${note}.mp3`
    try {
      const data: Uint8Array = await electron.readLocalFile(filePath)
      const blob = new Blob([data], { type: 'audio/mp3' })
      return URL.createObjectURL(blob)
    } catch {
      return null
    }
  }

  // HTTP fallback
  const url = `${getApiBase()}/audio/soundfonts/sample/${dirName}/${note}.mp3`
  try {
    const resp = await fetch(url, { method: 'HEAD' })
    if (!resp.ok) return null
    return url
  } catch {
    return null
  }
}

async function _buildSamplesMap(
  soundfontsPath: string | null,
  dirName: string,
): Promise<Record<string, string>> {
  const samples: Record<string, string> = {}

  await Promise.all(
    SAMPLE_NOTES.map(async (note) => {
      const url = await _loadSampleUrl(soundfontsPath, dirName, note)
      if (url) {
        samples[note] = url
      }
    }),
  )

  return samples
}

/**
 * Build samples map for GM drum kit (notes 35-81, stored as {midiNote}.mp3).
 */
async function _buildDrumSamplesMap(
  soundfontsPath: string | null,
  dirName: string,
): Promise<Record<string, string>> {
  const samples: Record<string, string> = {}

  await Promise.all(
    Array.from({ length: 81 - 35 + 1 }, (_, i) => i + 35).map(async (midiNote) => {
      const url = await _loadSampleUrl(soundfontsPath, dirName, String(midiNote))
      if (url) {
        // Key by note name so it matches the pitch lookup in rendering
        const noteName = Tone.Frequency(midiNote, 'midi').toNote()
        samples[noteName] = url
      }
    })
  )

  return samples
}

// ── WAV encoding ────────────────────────────────────────────────────────────

function audioBufferToWav(buffer: AudioBuffer): Blob {
  const numChannels = buffer.numberOfChannels
  const sampleRate = buffer.sampleRate
  const length = buffer.length
  const bytesPerSample = 2
  const blockAlign = numChannels * bytesPerSample
  const dataSize = length * blockAlign
  const headerSize = 44
  const arrayBuffer = new ArrayBuffer(headerSize + dataSize)
  const view = new DataView(arrayBuffer)

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
  }

  writeString(0, 'RIFF')
  view.setUint32(4, headerSize + dataSize - 8, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bytesPerSample * 8, true)
  writeString(36, 'data')
  view.setUint32(40, dataSize, true)

  const channelData: Float32Array[] = []
  for (let c = 0; c < numChannels; c++) {
    channelData.push(buffer.getChannelData(c))
  }

  let offset = headerSize
  for (let i = 0; i < length; i++) {
    for (let c = 0; c < numChannels; c++) {
      const sample = Math.max(-1, Math.min(1, channelData[c][i]))
      view.setInt16(offset, sample * 0x7fff, true)
      offset += 2
    }
  }

  return new Blob([arrayBuffer], { type: 'audio/wav' })
}

// ── Audibility check (mirrors useMidiPlayback) ──────────────────────────────

function isTrackAudible(tracks: MidiTrack[], trackIndex: number): boolean {
  const track = tracks[trackIndex]
  if (!track || track.muted) return false
  const hasSolo = tracks.some((t) => t.solo)
  return !hasSolo || track.solo
}

// ── Composable ──────────────────────────────────────────────────────────────

export function useMidiExport() {
  const { t } = useI18n()
  const toast = useToast()
  const isExporting = ref(false)
  const exportStatus = ref('')

  /**
   * Export all MIDI tracks to an audio file.
   *
   * @param tracks   - MidiTrack[] from useMidiEditor
   * @param tempo    - BPM
   * @param format   - 'wav' | 'mp3' | 'flac' | 'ogg' | 'aac'
   * @param outputPath - Absolute filesystem path for the output file
   */
  async function exportMidi(
    tracks: MidiTrack[],
    tempo: number,
    format: string,
    outputPath: string,
  ): Promise<void> {
    isExporting.value = true
    exportStatus.value = t('audio.midi.export_loading_samples')

    const taskStore = useTaskStore()
    const taskId = `midi-export-${Date.now()}`
    const fileName = outputPath.replace(/\\/g, '/').split('/').pop() || 'export'

    function updateTask(progress: number, message: string, status: 'processing' | 'completed' | 'failed' = 'processing') {
      taskStore.tasks.set(taskId, {
        taskId,
        taskType: 'audio.midi_export',
        status,
        progress,
        message,
        result: null,
        error: null,
        createdAt: taskStore.tasks.get(taskId)?.createdAt ?? new Date(),
        updatedAt: new Date(),
        label: t('audio.midi.task_label'),
        fileName,
      })
    }

    updateTask(0.05, t('audio.midi.export_loading_samples'))
    toast.show(t('toast.task_submitted', { label: t('audio.midi.task_label') }), {
      type: 'info',
      icon: 'bi-music-note-beamed',
    })

    try {
      // ── 1. Determine total duration ──────────────────────────────────────

      let lastBeat = 0
      for (let ti = 0; ti < tracks.length; ti++) {
        if (!isTrackAudible(tracks, ti)) continue
        const track = tracks[ti]
        for (const note of track.notes) {
          const end = note.start + note.duration
          if (end > lastBeat) lastBeat = end
        }
      }

      if (lastBeat === 0) {
        toast.show(t('toast.save_failed'), { type: 'error', icon: 'bi-x-circle' })
        return
      }

      // Add 2 beats for reverb tail
      const durationSeconds = (lastBeat + 2) * (60 / tempo)

      // ── 2. Fetch soundfonts path ─────────────────────────────────────────

      const soundfontsInfo = await _fetchSoundfontsInfo()
      const soundfontsPath = soundfontsInfo.exists ? soundfontsInfo.path : null

      if (!soundfontsPath && !soundfontsInfo.exists) {
        console.warn('[MidiExport] Soundfonts not available — export may be silent')
      }

      // ── 3. Collect unique instruments needed ─────────────────────────────

      // key → { dirName, trackIndices }
      const instrumentKeys = new Map<
        string,
        { dirName: string; trackIndices: number[] }
      >()

      for (let ti = 0; ti < tracks.length; ti++) {
        if (!isTrackAudible(tracks, ti)) continue
        const track = tracks[ti]
        const key = track.isDrum ? 'drum' : `inst_${track.instrument}`
        const dirName = track.isDrum
          ? GM_DRUM_SOUNDFONT_NAME
          : GM_SOUNDFONT_NAMES[track.instrument]

        if (!dirName) {
          console.warn(`[MidiExport] No soundfont for program ${track.instrument}`)
          continue
        }

        if (!instrumentKeys.has(key)) {
          instrumentKeys.set(key, { dirName, trackIndices: [] })
        }
        instrumentKeys.get(key)!.trackIndices.push(ti)
      }

      // ── 4. Pre-build samples maps (before offline context) ────────────────
      // We need to do this BEFORE entering the offline context because
      // Tone.Offline's callback is synchronous (it uses OfflineAudioContext).

      const samplesMaps = new Map<string, Record<string, string>>()

      await Promise.all(
        Array.from(instrumentKeys.entries()).map(async ([key, { dirName }]) => {
          const map = key === 'drum'
            ? await _buildDrumSamplesMap(soundfontsPath, `${dirName}-mp3`)
            : await _buildSamplesMap(soundfontsPath, `${dirName}-mp3`)
          samplesMaps.set(key, map)
        }),
      )

      // ── 5. Offline render ────────────────────────────────────────────────

      // Track blob URLs we create so we can revoke them after rendering
      const blobUrls: string[] = []
      // Collect blob URLs from samples maps to revoke later
      for (const map of samplesMaps.values()) {
        for (const url of Object.values(map)) {
          if (url.startsWith('blob:')) {
            blobUrls.push(url)
          }
        }
      }

      // ── 5b. Pre-decode samples into AudioBuffers ──────────────────────────
      exportStatus.value = t('audio.midi.export_loading_samples')
      updateTask(0.1, t('audio.midi.export_loading_samples'))

      const audioCtx = Tone.getContext().rawContext as AudioContext

      // Decode all sample blob URLs into AudioBuffers (once, shared across segments)
      const decodedBuffers = new Map<string, { midi: number; buffer: AudioBuffer }[]>()

      for (const [key, samplesMap] of samplesMaps.entries()) {
        const notes: { midi: number; buffer: AudioBuffer }[] = []
        await Promise.all(
          Object.entries(samplesMap).map(async ([noteName, url]) => {
            try {
              const resp = await fetch(url)
              const arrayBuf = await resp.arrayBuffer()
              const audioBuf = await audioCtx.decodeAudioData(arrayBuf.slice(0))
              const midi = Tone.Frequency(noteName).toMidi()
              notes.push({ midi, buffer: audioBuf })
            } catch { /* skip */ }
          })
        )
        notes.sort((a, b) => a.midi - b.midi)
        decodedBuffers.set(key, notes)
      }

      // ── 5c. Chunked Tone.Offline rendering with effects ─────────────────────
      // Render in 10-second segments to keep node count manageable.
      // Uses Tone.Offline so we get Tone.js effects (EQ, Compressor, Delay, Reverb).
      exportStatus.value = t('audio.midi.export_rendering')
      updateTask(0.1, t('audio.midi.export_rendering'))

      const SAMPLE_RATE = 44100
      const SEGMENT_DURATION = 60
      const totalSegments = Math.ceil(durationSeconds / SEGMENT_DURATION)
      const secondsPerBeat = 60 / tempo
      const renderedSegments: Float32Array[][] = []

      for (let seg = 0; seg < totalSegments; seg++) {
        const segStart = seg * SEGMENT_DURATION
        const segEnd = Math.min((seg + 1) * SEGMENT_DURATION, durationSeconds)
        const segLen = segEnd - segStart

        const segBuffer = await Tone.Offline(async ({ transport }) => {
          // Effects chain (Gain/Panner → EQ → Compressor → Delay → Reverb → Destination)
          const reverb = new Tone.Reverb({ decay: effectsState.reverb.decay, wet: effectsState.reverb.wet })
          await reverb.ready
          const delay = new Tone.FeedbackDelay({ delayTime: effectsState.delay.time, feedback: effectsState.delay.feedback, wet: effectsState.delay.wet })
          const compressor = new Tone.Compressor({ threshold: effectsState.compressor.threshold, ratio: effectsState.compressor.ratio })
          const eq = new Tone.EQ3({ low: effectsState.eq.low, mid: effectsState.eq.mid, high: effectsState.eq.high })

          eq.connect(compressor)
          compressor.connect(delay)
          delay.connect(reverb)
          reverb.toDestination()

          // Per-track: Sampler → Panner → Gain → EQ
          for (let ti = 0; ti < tracks.length; ti++) {
            if (!isTrackAudible(tracks, ti)) continue
            const track = tracks[ti]
            const key = track.isDrum ? 'drum' : `inst_${track.instrument}`
            const available = decodedBuffers.get(key)
            if (!available || available.length === 0) continue

            const volDb = midiVolumeToDB(track.volume ?? 100)
            const gain = new Tone.Gain(Math.pow(10, volDb / 20))
            const panner = new Tone.Panner(midiPanToFloat(track.pan ?? 64))
            panner.connect(gain)
            gain.connect(eq)

            // Build Sampler from pre-decoded buffers
            const sampleUrls: Record<string, string> = {}
            for (const { midi, buffer } of available) {
              const noteName = Tone.Frequency(midi, 'midi').toNote()
              // Re-use the blob URL from samplesMaps (still valid)
              const samplesMap = samplesMaps.get(key)
              if (samplesMap && samplesMap[noteName]) {
                sampleUrls[noteName] = samplesMap[noteName]
              }
            }

            if (Object.keys(sampleUrls).length === 0) continue

            const sampler = new Tone.Sampler({ urls: sampleUrls })
            await Tone.loaded()
            sampler.connect(panner)

            // Schedule notes in this segment
            for (const note of track.notes) {
              const noteOnSec = note.start * secondsPerBeat
              const noteOffSec = noteOnSec + note.duration * secondsPerBeat

              if (noteOnSec >= segEnd || noteOffSec <= segStart) continue

              const relStart = Math.max(0, noteOnSec - segStart)
              const relDur = Math.min(segLen, noteOffSec - segStart) - relStart
              const noteName = Tone.Frequency(note.pitch, 'midi').toNote()
              const vel = (note.velocity ?? 100) / 127

              transport.schedule((time) => {
                sampler.triggerAttackRelease(noteName, relDur, time, vel)
              }, relStart)
            }
          }

          transport.start()
        }, segLen, 2, SAMPLE_RATE)

        // Extract channel data
        const raw = segBuffer.get() as AudioBuffer
        const channels: Float32Array[] = []
        for (let c = 0; c < raw.numberOfChannels; c++) {
          channels.push(new Float32Array(raw.getChannelData(c)))
        }
        renderedSegments.push(channels)

        const pct = 0.1 + ((seg + 1) / totalSegments) * 0.8
        updateTask(pct, t('audio.midi.export_rendering') + ` ${Math.round(((seg + 1) / totalSegments) * 100)}%`)
        exportStatus.value = t('audio.midi.export_rendering') + ` ${Math.round(((seg + 1) / totalSegments) * 100)}%`
      }

      // ── 5d. Concatenate segments ──────────────────────────────────────────
      const totalSamples = renderedSegments.reduce((sum, seg) => sum + seg[0].length, 0)
      const finalBuffer: Float32Array[] = [new Float32Array(totalSamples), new Float32Array(totalSamples)]
      let offset = 0
      for (const seg of renderedSegments) {
        for (let c = 0; c < 2; c++) {
          finalBuffer[c].set(seg[c], offset)
        }
        offset += seg[0].length
      }

      const wavBuffer = {
        numberOfChannels: 2,
        sampleRate: SAMPLE_RATE,
        length: totalSamples,
        getChannelData: (c: number) => finalBuffer[c],
      } as AudioBuffer

      const wavBlob = audioBufferToWav(wavBuffer)

      // Revoke blob URLs now that recording is complete
      for (const url of blobUrls) {
        URL.revokeObjectURL(url)
      }

      // ── 6. Save ──────────────────────────────────────────────────────────

      const showInFolder = () => {
        ;(window as any).electron?.showItemInFolder(outputPath)
      }

      exportStatus.value = t('audio.midi.export_saving')
      updateTask(0.92, t('audio.midi.export_saving'))

      if (format === 'wav') {
        // WAV: save directly via Electron IPC
        const arrayBuf = await wavBlob.arrayBuffer()
        await (window as any).electron.writeLocalFile(outputPath, new Uint8Array(arrayBuf))
      } else {
        // Other formats: upload WAV to backend, FFmpeg converts
        const formData = new FormData()
        formData.append('file', wavBlob, 'export.wav')
        formData.append('format', format)
        formData.append('output_path', outputPath.replace(/\\/g, '/'))

        const res = await apiFetch('/audio/midi/convert', {
          method: 'POST',
          body: formData,
        })

        if (!res.ok) {
          const errText = await res.text().catch(() => res.statusText)
          throw new Error(`Conversion failed: ${errText}`)
        }
      }

      updateTask(1.0, t('toast.saved'), 'completed')
      toast.show(t('toast.saved'), {
        type: 'success',
        icon: 'bi-check-circle',
        action: { label: t('toast.open_folder'), callback: showInFolder },
      })
    } catch (err) {
      console.error('[MidiExport] Export failed:', err)
      updateTask(0, String(err), 'failed')
      toast.show(t('toast.save_failed'), { type: 'error', icon: 'bi-x-circle' })
    } finally {
      isExporting.value = false
      exportStatus.value = ''
    }
  }

  return {
    isExporting,
    exportStatus,
    exportMidi,
  }
}

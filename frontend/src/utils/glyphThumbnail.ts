/**
 * Render a glyph (emoji/symbol) centered on a dark square as a PNG data URL.
 *
 * Synchronous (uses canvas.toDataURL) so callers can set a filmstrip thumbnail
 * immediately, with no broken-image flash. Mirrors the per-type icon style used
 * by the workspace thumbnail generators (dark bg + muted glyph).
 *
 * Used for "open result in tool" (adopted) entries that reference a backend file
 * by URL: audio/video/document download URLs are not displayable as <img>, so we
 * render a type glyph instead. Images pass no glyph and use the download URL
 * directly (the image renders fine).
 *
 * Returns '' when a 2D context is unavailable (e.g. jsdom in unit tests) so the
 * caller degrades gracefully rather than throwing.
 */
export function renderGlyphThumbnail(glyph: string): string {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''

  // Dark background
  ctx.fillStyle = '#1e293b'
  ctx.fillRect(0, 0, size, size)

  // Muted centered glyph
  ctx.fillStyle = '#64748b'
  ctx.font = '48px serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(glyph, size / 2, size / 2)

  return canvas.toDataURL('image/png')
}

/** Per-tool glyphs, matching the workspace thumbnail generators. */
export const TOOL_GLYPH = {
  audio: '♫', // ♫ (matches generateAudioThumbnail)
  video: '\u{1F3AC}', // 🎬 (matches generateFallbackThumbnail)
  document: '\u{1F4C4}', // 📄 (matches generateDocumentThumbnail)
} as const

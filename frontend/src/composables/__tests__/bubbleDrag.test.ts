/**
 * Drag-and-snap logic for the ChatBubble — pure helpers tested in
 * isolation, then wired into ChatBubble.vue via useBubbleDrag().
 *
 * User-facing rules (from spec):
 *   - bubble center on left half → snap left, right half → snap right
 *   - exactly at midpoint (centerX === viewportWidth / 2) → snap right
 *   - bubble Y preserved on snap, clamped to viewport
 *   - drag delta < 5px is treated as a click, not a drag (no snap)
 *   - position persisted to localStorage as { side, y }
 */

import { describe, it, expect, beforeEach } from 'vitest'
import {
  snapSide,
  clampY,
  loadBubblePosition,
  saveBubblePosition,
  DEFAULT_BUBBLE_POSITION,
  type BubblePosition,
} from '@/composables/useBubbleDrag'

describe('snapSide', () => {
  const VIEWPORT_W = 1000

  it('snaps left when bubble center is on the left half', () => {
    expect(snapSide(100 + 24, VIEWPORT_W)).toBe('left')   // centerX=124, half=500
    expect(snapSide(0 + 24, VIEWPORT_W)).toBe('left')     // far left edge
  })

  it('snaps right when bubble center is on the right half', () => {
    expect(snapSide(800 + 24, VIEWPORT_W)).toBe('right')  // centerX=824
    expect(snapSide(952, VIEWPORT_W)).toBe('right')       // far right edge
  })

  it('snaps right when bubble center is exactly at the midpoint (user tie-breaker)', () => {
    // Viewport width 1000 → midpoint 500. Bubble x such that center = 500.
    expect(snapSide(476, VIEWPORT_W)).toBe('right')       // 476 + 24 = 500 exactly
  })

  it('snaps right when centerX is just past the midpoint', () => {
    expect(snapSide(477, VIEWPORT_W)).toBe('right')       // centerX=501
  })

  it('snaps left when centerX is just before the midpoint', () => {
    expect(snapSide(475, VIEWPORT_W)).toBe('left')        // centerX=499
  })
})

describe('clampY', () => {
  const VIEWPORT_H = 800
  const BUBBLE_H = 48
  const MARGIN = 24

  it('returns Y unchanged when within bounds', () => {
    expect(clampY(100, VIEWPORT_H)).toBe(100)
    expect(clampY(400, VIEWPORT_H)).toBe(400)
  })

  it('clamps to top margin when bubble would overflow above', () => {
    expect(clampY(-50, VIEWPORT_H)).toBe(MARGIN)
    expect(clampY(0, VIEWPORT_H)).toBe(MARGIN)
    expect(clampY(MARGIN - 1, VIEWPORT_H)).toBe(MARGIN)
  })

  it('clamps to bottom when bubble would overflow below', () => {
    const maxY = VIEWPORT_H - BUBBLE_H - MARGIN  // 800 - 48 - 24 = 728
    expect(clampY(900, VIEWPORT_H)).toBe(maxY)
    expect(clampY(maxY + 1, VIEWPORT_H)).toBe(maxY)
  })

  it('allows the exact max Y without further clamping', () => {
    const maxY = VIEWPORT_H - BUBBLE_H - MARGIN
    expect(clampY(maxY, VIEWPORT_H)).toBe(maxY)
  })
})

describe('loadBubblePosition / saveBubblePosition', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns DEFAULT when localStorage is empty', () => {
    expect(loadBubblePosition()).toEqual(DEFAULT_BUBBLE_POSITION)
  })

  it('returns DEFAULT when stored JSON is malformed', () => {
    localStorage.setItem('chat-bubble-position', '{not json}')
    expect(loadBubblePosition()).toEqual(DEFAULT_BUBBLE_POSITION)
  })

  it('returns DEFAULT when stored side is invalid', () => {
    localStorage.setItem('chat-bubble-position', JSON.stringify({ side: 'middle', y: 100 }))
    expect(loadBubblePosition()).toEqual(DEFAULT_BUBBLE_POSITION)
  })

  it('returns DEFAULT when stored y is not a finite number', () => {
    localStorage.setItem('chat-bubble-position', JSON.stringify({ side: 'left', y: 'abc' }))
    expect(loadBubblePosition()).toEqual(DEFAULT_BUBBLE_POSITION)
    localStorage.setItem('chat-bubble-position', JSON.stringify({ side: 'left', y: NaN }))
    expect(loadBubblePosition()).toEqual(DEFAULT_BUBBLE_POSITION)
  })

  it('round-trips a valid position', () => {
    const pos: BubblePosition = { side: 'left', y: 240 }
    saveBubblePosition(pos)
    expect(loadBubblePosition()).toEqual(pos)
  })

  it('overwrites previously saved position', () => {
    saveBubblePosition({ side: 'left', y: 100 })
    saveBubblePosition({ side: 'right', y: 500 })
    expect(loadBubblePosition()).toEqual({ side: 'right', y: 500 })
  })
})

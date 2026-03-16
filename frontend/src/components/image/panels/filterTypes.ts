export interface FilterPreview {
  brightness: number   // 1.0 = 不變
  contrast:   number
  saturation: number
  hue:        number   // degrees
  sharpness:  number   // 1.0 = 不變（SVG feConvolveMatrix）
  warmth:     number   // -1.0 冷 ~ 1.0 暖（SVG feColorMatrix）
  grayscale:  number   // 0-1
  sepia:      number   // 0-1
  invert:     number   // 0-1
  blur:       number   // px
  vignette:   number   // 0-1
}

/**
 * WebGL2 即時濾鏡預覽 composable
 *
 * 用 GPU shader 渲染 11 個濾鏡效果，與後端 PIL filter_service._apply_all 完全一致：
 * grayscale → brightness → contrast → saturation → hue → warmth →
 * sharpness → sepia → invert → blur → vignette
 *
 * 三 pass pipeline：
 *   Pass 1: 主濾鏡 (9 效果 + sharpness 3×3 convolution)
 *   Pass 2: 水平 Gaussian blur
 *   Pass 3: 垂直 Gaussian blur + vignette
 * 快捷路徑：blur=0 && vignette=0 → single pass 直出螢幕
 */
import { ref, onBeforeUnmount, type Ref } from 'vue'
import type { FilterPreview } from '@/components/image/panels/filterTypes'

// ────────────────────────────── GLSL Shaders ──────────────────────────────

const VERTEX_SRC = /* glsl */ `#version 300 es
precision highp float;
in vec2 a_position;
out vec2 v_uv;
void main() {
  v_uv = a_position * 0.5 + 0.5;
  gl_Position = vec4(a_position, 0.0, 1.0);
}
`

/**
 * Pass 1 — 主濾鏡 fragment shader
 * 順序與後端 _apply_all 一致
 */
const MAIN_FRAG_SRC = /* glsl */ `#version 300 es
precision highp float;

in vec2 v_uv;
out vec4 fragColor;

uniform sampler2D u_image;
uniform vec2 u_texelSize;   // 1.0 / textureSize

// Filter uniforms
uniform float u_grayscale;
uniform float u_brightness;
uniform float u_contrast;
uniform float u_meanLuma;   // 全圖平均亮度 (CPU 預計算)
uniform float u_saturation;
uniform float u_hue;        // degrees
uniform float u_warmth;     // -1 ~ 1
uniform float u_sharpness;  // 0 ~ 3
uniform float u_sepia;
uniform float u_invert;

// ── HSV 轉換 (match PIL / numpy vectorized HSV) ──
vec3 rgb2hsv(vec3 c) {
  float cmax = max(c.r, max(c.g, c.b));
  float cmin = min(c.r, min(c.g, c.b));
  float delta = cmax - cmin;
  float eps = 1e-6;

  float h = 0.0;
  float s = (cmax > eps) ? delta / cmax : 0.0;
  float v = cmax;

  if (delta > eps) {
    if (cmax == c.r)      h = mod((c.g - c.b) / delta, 6.0);
    else if (cmax == c.g) h = (c.b - c.r) / delta + 2.0;
    else                  h = (c.r - c.g) / delta + 4.0;
    h /= 6.0;
  }
  return vec3(h, s, v);
}

vec3 hsv2rgb(vec3 c) {
  float h = c.x * 6.0;
  float s = c.y;
  float v = c.z;
  float i = floor(h);
  float f = h - i;
  float p = v * (1.0 - s);
  float q = v * (1.0 - s * f);
  float t = v * (1.0 - s * (1.0 - f));
  int im = int(mod(i, 6.0));

  if (im == 0) return vec3(v, t, p);
  if (im == 1) return vec3(q, v, p);
  if (im == 2) return vec3(p, v, t);
  if (im == 3) return vec3(p, q, v);
  if (im == 4) return vec3(t, p, v);
  return vec3(v, p, q);
}

void main() {
  vec4 tex = texture(u_image, v_uv);
  vec3 color = tex.rgb;
  float alpha = tex.a;

  // 1. Grayscale (ITU-R 601 weights, same as PIL .convert("L"))
  if (u_grayscale > 0.0) {
    float luma = dot(color, vec3(0.299, 0.587, 0.114));
    color = mix(color, vec3(luma), u_grayscale);
  }

  // 2. Brightness — PIL ImageEnhance.Brightness: blend(black, image, factor)
  if (u_brightness != 1.0) {
    color = color * u_brightness;
  }

  // 3. Contrast — PIL ImageEnhance.Contrast: blend(mean_gray, image, factor)
  if (u_contrast != 1.0) {
    color = mix(vec3(u_meanLuma), color, u_contrast);
  }

  // 4. Saturation — PIL ImageEnhance.Color: blend(L_grayscale, image, factor)
  if (u_saturation != 1.0) {
    float luma = dot(color, vec3(0.299, 0.587, 0.114));
    color = mix(vec3(luma), color, u_saturation);
  }

  // 5. Hue — true HSV rotation (NOT CSS hue-rotate matrix)
  if (u_hue != 0.0) {
    vec3 hsv = rgb2hsv(color);
    hsv.x = fract(hsv.x + u_hue / 360.0);
    color = hsv2rgb(hsv);
  }

  // 6. Warmth — asymmetric R/B channel shift (0-1 space, coefficients /255)
  if (u_warmth != 0.0) {
    if (u_warmth > 0.0) {
      color.r = clamp(color.r + u_warmth * (30.0 / 255.0), 0.0, 1.0);
      color.b = clamp(color.b - u_warmth * (20.0 / 255.0), 0.0, 1.0);
    } else {
      color.r = clamp(color.r + u_warmth * (20.0 / 255.0), 0.0, 1.0);
      color.b = clamp(color.b - u_warmth * (30.0 / 255.0), 0.0, 1.0);
    }
  }

  // 7. Sharpness — 3×3 unsharp mask convolution
  if (u_sharpness != 1.0) {
    // PIL ImageEnhance.Sharpness blends between blurred and sharpened
    // For sharpness > 1: unsharp mask kernel
    // For sharpness < 1: blend toward blurred (smooth kernel)
    float factor = u_sharpness;
    // Smooth kernel (PIL SMOOTH): center=5/13, sides=1/13
    // Sharp kernel: identity + (identity - smooth) * (factor - 1)
    // Simplified: 3x3 kernel with adjustable center weight

    // Sample 3x3 neighborhood
    vec3 tl = texture(u_image, v_uv + vec2(-u_texelSize.x, -u_texelSize.y)).rgb;
    vec3 tc = texture(u_image, v_uv + vec2(0.0,            -u_texelSize.y)).rgb;
    vec3 tr = texture(u_image, v_uv + vec2( u_texelSize.x, -u_texelSize.y)).rgb;
    vec3 ml = texture(u_image, v_uv + vec2(-u_texelSize.x, 0.0)).rgb;
    vec3 mr = texture(u_image, v_uv + vec2( u_texelSize.x, 0.0)).rgb;
    vec3 bl = texture(u_image, v_uv + vec2(-u_texelSize.x,  u_texelSize.y)).rgb;
    vec3 bc = texture(u_image, v_uv + vec2(0.0,             u_texelSize.y)).rgb;
    vec3 br = texture(u_image, v_uv + vec2( u_texelSize.x,  u_texelSize.y)).rgb;

    // PIL SMOOTH kernel: [[1,1,1],[1,5,1],[1,1,1]] / 13
    vec3 smoothed = (tl + tc + tr + ml + color * 5.0 + mr + bl + bc + br) / 13.0;
    // PIL ImageEnhance.Sharpness: blend(smoothed, original, factor)
    // factor=0 → full smooth, factor=1 → original, factor>1 → sharpened
    color = mix(smoothed, color, factor);
  }

  // 8. Sepia — custom matrix + blend
  if (u_sepia > 0.0) {
    vec3 sepia = vec3(
      clamp(color.r * 0.393 + color.g * 0.769 + color.b * 0.189, 0.0, 1.0),
      clamp(color.r * 0.349 + color.g * 0.686 + color.b * 0.168, 0.0, 1.0),
      clamp(color.r * 0.272 + color.g * 0.534 + color.b * 0.131, 0.0, 1.0)
    );
    color = mix(color, sepia, u_sepia);
  }

  // 9. Invert — blend with inverted
  if (u_invert > 0.0) {
    color = mix(color, 1.0 - color, u_invert);
  }

  fragColor = vec4(clamp(color, 0.0, 1.0), alpha);
}
`

/** Pass 2 — 水平 Gaussian blur */
const BLUR_H_FRAG_SRC = /* glsl */ `#version 300 es
precision highp float;

in vec2 v_uv;
out vec4 fragColor;

uniform sampler2D u_image;
uniform sampler2D u_original;  // 原始圖的 alpha
uniform vec2 u_texelSize;
uniform float u_weights[64];
uniform int u_kernelSize;      // half-kernel size (one side)

void main() {
  vec3 sum = vec3(0.0);
  float weightSum = 0.0;

  for (int i = -63; i <= 63; i++) {
    if (i < -u_kernelSize || i > u_kernelSize) continue;
    float w = u_weights[abs(i)];
    vec2 offset = vec2(float(i) * u_texelSize.x, 0.0);
    sum += texture(u_image, v_uv + offset).rgb * w;
    weightSum += w;
  }

  // alpha 不受 blur 影響，取原始圖 alpha
  float alpha = texture(u_original, v_uv).a;
  fragColor = vec4(sum / weightSum, alpha);
}
`

/** Pass 3 — 垂直 Gaussian blur + vignette */
const BLUR_V_VIGNETTE_FRAG_SRC = /* glsl */ `#version 300 es
precision highp float;

in vec2 v_uv;
out vec4 fragColor;

uniform sampler2D u_image;
uniform sampler2D u_original;
uniform vec2 u_texelSize;
uniform vec2 u_resolution;     // canvas size in pixels
uniform float u_weights[64];
uniform int u_kernelSize;
uniform float u_blur;          // 0 = skip blur, just do vignette passthrough
uniform float u_vignette;

void main() {
  vec3 color;

  if (u_blur > 0.0) {
    vec3 sum = vec3(0.0);
    float weightSum = 0.0;
    for (int i = -63; i <= 63; i++) {
      if (i < -u_kernelSize || i > u_kernelSize) continue;
      float w = u_weights[abs(i)];
      vec2 offset = vec2(0.0, float(i) * u_texelSize.y);
      sum += texture(u_image, v_uv + offset).rgb * w;
      weightSum += w;
    }
    color = sum / weightSum;
  } else {
    color = texture(u_image, v_uv).rgb;
  }

  // Vignette — match backend _apply_vignette exactly
  if (u_vignette > 0.0) {
    // dist: normalized distance from center, ellipse scaled to [-1, 1]
    vec2 centered = (v_uv - 0.5) * 2.0;
    float dist = length(centered);
    float spread = max(0.01, 1.0 - u_vignette * 0.6);
    float mask = clamp((dist - spread) / (1.0 - spread + 1e-6), 0.0, 1.0);
    float darken = 1.0 - mask * u_vignette * 0.85;
    color *= darken;
  }

  float alpha = texture(u_original, v_uv).a;
  fragColor = vec4(clamp(color, 0.0, 1.0), alpha);
}
`

// ────────────────────────────── Composable ──────────────────────────────

export function useWebGLFilter(canvasRef: Ref<HTMLCanvasElement | null>) {
  const isReady = ref(false)
  const isSupported = ref(true)

  let gl: WebGL2RenderingContext | null = null
  let mainProg: WebGLProgram | null = null
  let blurHProg: WebGLProgram | null = null
  let blurVProg: WebGLProgram | null = null
  let quadVAO: WebGLVertexArrayObject | null = null
  let srcTexture: WebGLTexture | null = null
  let fboA: WebGLFramebuffer | null = null
  let fboB: WebGLFramebuffer | null = null
  let texA: WebGLTexture | null = null
  let texB: WebGLTexture | null = null
  let texW = 0
  let texH = 0
  let meanLuma = 0.5
  let currentCanvas: HTMLCanvasElement | null = null
  let pendingRender: FilterPreview | null = null
  let rafId = 0

  // ── GL helpers ──

  function compileShader(type: number, src: string): WebGLShader | null {
    if (!gl) return null
    const sh = gl.createShader(type)
    if (!sh) return null
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.error('Shader compile error:', gl.getShaderInfoLog(sh))
      gl.deleteShader(sh)
      return null
    }
    return sh
  }

  function createProgram(vSrc: string, fSrc: string): WebGLProgram | null {
    if (!gl) return null
    const vs = compileShader(gl.VERTEX_SHADER, vSrc)
    const fs = compileShader(gl.FRAGMENT_SHADER, fSrc)
    if (!vs || !fs) return null
    const prog = gl.createProgram()!
    gl.attachShader(prog, vs)
    gl.attachShader(prog, fs)
    gl.linkProgram(prog)
    gl.deleteShader(vs)
    gl.deleteShader(fs)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error('Program link error:', gl.getProgramInfoLog(prog))
      gl.deleteProgram(prog)
      return null
    }
    return prog
  }

  function createFBOTexture(): { fbo: WebGLFramebuffer; tex: WebGLTexture } | null {
    if (!gl) return null
    const tex = gl.createTexture()!
    gl.bindTexture(gl.TEXTURE_2D, tex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, texW, texH, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    const fbo = gl.createFramebuffer()!
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo)
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0)
    gl.bindFramebuffer(gl.FRAMEBUFFER, null)
    return { fbo, tex }
  }

  function resizeFBOs() {
    if (!gl) return
    // Clean up old
    if (fboA) gl.deleteFramebuffer(fboA)
    if (fboB) gl.deleteFramebuffer(fboB)
    if (texA) gl.deleteTexture(texA)
    if (texB) gl.deleteTexture(texB)
    const a = createFBOTexture()
    const b = createFBOTexture()
    if (a && b) {
      fboA = a.fbo; texA = a.tex
      fboB = b.fbo; texB = b.tex
    }
  }

  // ── Init GL context ──

  function disposeGL() {
    if (!gl) return
    if (srcTexture) gl.deleteTexture(srcTexture)
    if (texA) gl.deleteTexture(texA)
    if (texB) gl.deleteTexture(texB)
    if (fboA) gl.deleteFramebuffer(fboA)
    if (fboB) gl.deleteFramebuffer(fboB)
    if (mainProg) gl.deleteProgram(mainProg)
    if (blurHProg) gl.deleteProgram(blurHProg)
    if (blurVProg) gl.deleteProgram(blurVProg)
    srcTexture = null; texA = null; texB = null
    fboA = null; fboB = null
    mainProg = null; blurHProg = null; blurVProg = null
    gl = null
    currentCanvas = null
    isReady.value = false
  }

  function initGL(): boolean {
    const canvas = canvasRef.value
    if (!canvas) return false

    // Canvas element changed (v-if remount) — dispose old context
    if (gl && canvas !== currentCanvas) {
      disposeGL()
    }

    currentCanvas = canvas
    gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: false, preserveDrawingBuffer: false })
    if (!gl) {
      isSupported.value = false
      return false
    }

    // Compile programs
    mainProg = createProgram(VERTEX_SRC, MAIN_FRAG_SRC)
    blurHProg = createProgram(VERTEX_SRC, BLUR_H_FRAG_SRC)
    blurVProg = createProgram(VERTEX_SRC, BLUR_V_VIGNETTE_FRAG_SRC)
    if (!mainProg || !blurHProg || !blurVProg) {
      isSupported.value = false
      return false
    }

    // Full-screen quad VAO
    quadVAO = gl.createVertexArray()!
    gl.bindVertexArray(quadVAO)
    const buf = gl.createBuffer()!
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW)
    // Bind a_position for all programs
    for (const prog of [mainProg, blurHProg, blurVProg]) {
      const loc = gl.getAttribLocation(prog, 'a_position')
      if (loc >= 0) {
        gl.enableVertexAttribArray(loc)
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
      }
    }
    gl.bindVertexArray(null)

    return true
  }

  // ── Compute mean luminance on CPU (for accurate PIL Contrast match) ──

  function computeMeanLuma(img: HTMLImageElement): number {
    const c = document.createElement('canvas')
    // Use a small version for speed
    const maxDim = 256
    const scale = Math.min(1, maxDim / Math.max(img.naturalWidth, img.naturalHeight))
    c.width = Math.round(img.naturalWidth * scale)
    c.height = Math.round(img.naturalHeight * scale)
    const ctx = c.getContext('2d')!
    ctx.drawImage(img, 0, 0, c.width, c.height)
    const data = ctx.getImageData(0, 0, c.width, c.height).data
    let sum = 0
    const count = c.width * c.height
    for (let i = 0; i < data.length; i += 4) {
      sum += data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114
    }
    return (sum / count) / 255.0
  }

  // ── Gaussian kernel weights ──

  function computeGaussianWeights(radius: number): { weights: Float32Array; kernelSize: number } {
    const sigma = radius / 3.0
    const kernelSize = Math.min(Math.ceil(radius * 3), 63)
    const weights = new Float32Array(64)
    let sum = 0
    for (let i = 0; i <= kernelSize; i++) {
      const w = Math.exp(-(i * i) / (2 * sigma * sigma))
      weights[i] = w
      sum += (i === 0) ? w : w * 2
    }
    // Normalize
    for (let i = 0; i <= kernelSize; i++) {
      weights[i] /= sum
    }
    return { weights, kernelSize }
  }

  // ── Load image as texture ──

  async function loadImage(url: string): Promise<void> {
    // Detect canvas element change (v-if remount) and reinit GL
    const canvas = canvasRef.value
    if (!canvas) return
    if (canvas !== currentCanvas || !gl) {
      if (!initGL()) return
    }

    return new Promise<void>((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => {
        if (!gl) { reject(); return }

        // Compute mean luminance for PIL-accurate contrast
        meanLuma = computeMeanLuma(img)

        // Upload texture (flip Y: WebGL origin is bottom-left, HTML image is top-left)
        if (srcTexture) gl.deleteTexture(srcTexture)
        srcTexture = gl.createTexture()!
        gl.bindTexture(gl.TEXTURE_2D, srcTexture)
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, img)
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)

        texW = img.naturalWidth
        texH = img.naturalHeight

        // Resize canvas to match image
        const canvas = canvasRef.value!
        canvas.width = texW
        canvas.height = texH

        // Recreate FBOs at new size
        resizeFBOs()

        isReady.value = true
        resolve()
      }
      img.onerror = () => reject(new Error(`Failed to load image: ${url}`))
      img.src = url
    })
  }

  // ── Render ──

  function setUniformSafe(prog: WebGLProgram, name: string, value: number) {
    if (!gl) return
    const loc = gl.getUniformLocation(prog, name)
    if (loc) gl.uniform1f(loc, value)
  }

  function render(params: FilterPreview) {
    if (!gl || !srcTexture || !mainProg || !blurHProg || !blurVProg || !quadVAO) return

    const needBlur = params.blur > 0
    const needVignette = params.vignette > 0
    const needMultiPass = needBlur || needVignette

    gl.bindVertexArray(quadVAO)

    // ── Pass 1: Main filter ──
    gl.useProgram(mainProg)

    // Bind source texture to unit 0
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, srcTexture)
    gl.uniform1i(gl.getUniformLocation(mainProg, 'u_image')!, 0)
    gl.uniform2f(gl.getUniformLocation(mainProg, 'u_texelSize')!, 1.0 / texW, 1.0 / texH)

    // Set filter uniforms
    setUniformSafe(mainProg, 'u_grayscale', params.grayscale)
    setUniformSafe(mainProg, 'u_brightness', params.brightness)
    setUniformSafe(mainProg, 'u_contrast', params.contrast)
    setUniformSafe(mainProg, 'u_meanLuma', meanLuma)
    setUniformSafe(mainProg, 'u_saturation', params.saturation)
    setUniformSafe(mainProg, 'u_hue', params.hue)
    setUniformSafe(mainProg, 'u_warmth', params.warmth)
    setUniformSafe(mainProg, 'u_sharpness', params.sharpness)
    setUniformSafe(mainProg, 'u_sepia', params.sepia)
    setUniformSafe(mainProg, 'u_invert', params.invert)

    if (needMultiPass) {
      // Render to FBO-A
      gl.bindFramebuffer(gl.FRAMEBUFFER, fboA)
      gl.viewport(0, 0, texW, texH)
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)

      if (needBlur) {
        // ── Pass 2: Horizontal blur → FBO-B ──
        const { weights, kernelSize } = computeGaussianWeights(params.blur)
        gl.useProgram(blurHProg)

        gl.activeTexture(gl.TEXTURE0)
        gl.bindTexture(gl.TEXTURE_2D, texA!)
        gl.uniform1i(gl.getUniformLocation(blurHProg, 'u_image')!, 0)

        gl.activeTexture(gl.TEXTURE1)
        gl.bindTexture(gl.TEXTURE_2D, srcTexture)
        gl.uniform1i(gl.getUniformLocation(blurHProg, 'u_original')!, 1)

        gl.uniform2f(gl.getUniformLocation(blurHProg, 'u_texelSize')!, 1.0 / texW, 1.0 / texH)
        gl.uniform1fv(gl.getUniformLocation(blurHProg, 'u_weights[0]')!, weights)
        gl.uniform1i(gl.getUniformLocation(blurHProg, 'u_kernelSize')!, kernelSize)

        gl.bindFramebuffer(gl.FRAMEBUFFER, fboB)
        gl.viewport(0, 0, texW, texH)
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)

        // ── Pass 3: Vertical blur + vignette → screen ──
        gl.useProgram(blurVProg)

        gl.activeTexture(gl.TEXTURE0)
        gl.bindTexture(gl.TEXTURE_2D, texB!)
        gl.uniform1i(gl.getUniformLocation(blurVProg, 'u_image')!, 0)

        gl.activeTexture(gl.TEXTURE1)
        gl.bindTexture(gl.TEXTURE_2D, srcTexture)
        gl.uniform1i(gl.getUniformLocation(blurVProg, 'u_original')!, 1)

        gl.uniform2f(gl.getUniformLocation(blurVProg, 'u_texelSize')!, 1.0 / texW, 1.0 / texH)
        gl.uniform2f(gl.getUniformLocation(blurVProg, 'u_resolution')!, texW, texH)
        gl.uniform1fv(gl.getUniformLocation(blurVProg, 'u_weights[0]')!, weights)
        gl.uniform1i(gl.getUniformLocation(blurVProg, 'u_kernelSize')!, kernelSize)
        gl.uniform1f(gl.getUniformLocation(blurVProg, 'u_blur')!, params.blur)
        gl.uniform1f(gl.getUniformLocation(blurVProg, 'u_vignette')!, params.vignette)

        gl.bindFramebuffer(gl.FRAMEBUFFER, null)
        gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight)
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)

      } else {
        // Only vignette, no blur — Pass 3 with blur=0
        gl.useProgram(blurVProg)

        gl.activeTexture(gl.TEXTURE0)
        gl.bindTexture(gl.TEXTURE_2D, texA!)
        gl.uniform1i(gl.getUniformLocation(blurVProg, 'u_image')!, 0)

        gl.activeTexture(gl.TEXTURE1)
        gl.bindTexture(gl.TEXTURE_2D, srcTexture)
        gl.uniform1i(gl.getUniformLocation(blurVProg, 'u_original')!, 1)

        gl.uniform2f(gl.getUniformLocation(blurVProg, 'u_texelSize')!, 1.0 / texW, 1.0 / texH)
        gl.uniform2f(gl.getUniformLocation(blurVProg, 'u_resolution')!, texW, texH)
        // Empty weights, kernelSize 0 — blur loop won't execute
        gl.uniform1fv(gl.getUniformLocation(blurVProg, 'u_weights[0]')!, new Float32Array(64))
        gl.uniform1i(gl.getUniformLocation(blurVProg, 'u_kernelSize')!, 0)
        gl.uniform1f(gl.getUniformLocation(blurVProg, 'u_blur')!, 0.0)
        gl.uniform1f(gl.getUniformLocation(blurVProg, 'u_vignette')!, params.vignette)

        gl.bindFramebuffer(gl.FRAMEBUFFER, null)
        gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight)
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
      }
    } else {
      // Single pass — direct to screen
      gl.bindFramebuffer(gl.FRAMEBUFFER, null)
      gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight)
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    }

    gl.bindVertexArray(null)
  }

  // ── Public API ──

  function updateFilters(params: FilterPreview): void {
    pendingRender = params
    if (!rafId) {
      rafId = requestAnimationFrame(() => {
        rafId = 0
        if (pendingRender) {
          render(pendingRender)
          pendingRender = null
        }
      })
    }
  }

  function dispose() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0 }
    disposeGL()
  }

  onBeforeUnmount(dispose)

  return { isReady, isSupported, loadImage, updateFilters, dispose }
}

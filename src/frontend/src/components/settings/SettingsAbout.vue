<script setup lang="ts">
import AppIcon from '@/assets/icon.svg'

function restartApp() {
  ;(window as any).electron?.restart()
}
</script>

<template>
  <div class="about-header">
    <div class="about-logo">
      <img :src="AppIcon" alt="MediaTranX Logo" />
    </div>
    <div class="about-title-group">
      <h4 class="about-name">MediaTranX</h4>
      <p class="about-version">版本 1.0.0 (Production Build)</p>
    </div>
  </div>

  <p class="about-desc">
    本地 AI 驅動的多媒體處理工具，支援影片字幕提取、翻譯、音訊處理、圖片處理等功能。所有 AI 模型均在本機運行，無需上傳資料至雲端，保護您的隱私。
  </p>

  <h6 class="section-title mt">支援與連結</h6>
  <div class="about-links">
    <button class="about-link-btn"><i class="bi bi-github"></i> GitHub</button>
    <button class="about-link-btn"><i class="bi bi-chat-dots"></i> 意見回饋</button>
    <button class="about-link-btn"><i class="bi bi-globe"></i> 官方網站</button>
  </div>

  <h6 class="section-title mt">技術致謝</h6>
  <p class="credits-text">
    MediaTranX 建立在眾多卓越的開源技術之上：<br/>
    Vue 3, Vite, Electron, FFmpeg, OpenAI Whisper, Real-ESRGAN, TranslateGemma, Llama-cpp-python 等。
  </p>

  <div class="about-footer">
    <p>© 2026 MediaTranX Project. All rights reserved.</p>
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.about-header {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-bottom: 1.5rem;
}

.about-logo img {
  width: 64px;
  height: 64px;
  object-fit: contain;
}

.about-title-group {
  display: flex;
  flex-direction: column;
}

.about-name {
  color: var(--text-primary);
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.about-version {
  color: var(--text-muted);
  font-size: 0.875rem;
  margin: 0;
}

.about-desc {
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.6;
  max-width: 560px;
  margin-bottom: 2rem;
}

.about-links {
  display: flex;
  gap: 0.75rem;
}

.about-link-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); border-color: var(--input-border-focus); }
}

.credits-text {
  color: var(--text-muted);
  font-size: 0.8rem;
  line-height: 1.6;
}

.about-footer {
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--panel-border);
  color: var(--text-muted);
  font-size: 0.75rem;
}
</style>

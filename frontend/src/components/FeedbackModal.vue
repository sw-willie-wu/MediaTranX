<template>
  <Teleport to="body">
    <Transition name="feedback-fade">
      <div v-if="fb.modalVisible" class="feedback-modal-backdrop" @click.self="fb.dismiss()">
        <div class="feedback-modal">
          <h5 class="modal-title">{{ t('feedback.title') }}</h5>

          <!-- 類型單選 -->
          <div class="field">
            <label class="field-label">{{ t('feedback.type_label') }}</label>
            <div class="type-options">
              <label v-for="k in TYPES" :key="k" class="type-option">
                <input
                  type="radio" name="fb-type" :value="k"
                  :checked="fb.form.type === k" @change="fb.setType(k)"
                />
                {{ t(`feedback.type.${k}`) }}
              </label>
            </div>
          </div>

          <!-- 描述（必填） -->
          <div class="field">
            <label class="field-label">{{ t('feedback.description_label') }}</label>
            <textarea
              v-model="fb.form.description" rows="5"
              :placeholder="t('feedback.description_placeholder')"
            ></textarea>
          </div>

          <!-- Email（選填） -->
          <div class="field">
            <label class="field-label">{{ t('feedback.email_label') }}</label>
            <input v-model="fb.form.email" type="email" />
          </div>

          <!-- 附診斷 + 預覽 -->
          <div class="field">
            <label class="check-row">
              <input
                type="checkbox" :checked="fb.includeDiagnostics"
                @change="fb.toggleInclude(($event.target as HTMLInputElement).checked)"
              />
              {{ t('feedback.include_diagnostics') }}
            </label>
            <button
              v-if="fb.includeDiagnostics" class="preview-toggle link-btn"
              type="button" @click="previewOpen = !previewOpen"
            >
              {{ t('feedback.preview_toggle') }}
            </button>
            <div v-if="fb.includeDiagnostics && previewOpen" class="preview">
              <div v-if="fb.snapshotError" class="preview-error">{{ t('feedback.diag_fetch_failed') }}</div>
              <template v-else-if="fb.snapshot">
                <section v-for="key in SECTION_KEYS" :key="key" class="preview-section">
                  <h6>{{ t(`feedback.section.${key}`) }}</h6>
                  <pre>{{ fb.snapshot[key] }}</pre>
                </section>
              </template>
            </div>
          </div>

          <!-- 動作列 -->
          <div class="feedback-actions">
            <button class="feedback-btn cancel" :disabled="fb.submitting" @click="fb.dismiss()">
              {{ t('feedback.cancel') }}
            </button>
            <button
              class="feedback-btn primary submit-btn"
              :disabled="fb.submitting || !fb.form.description.trim()"
              @click="fb.submit()"
            >
              {{ fb.submitting ? t('feedback.sending') : t('feedback.submit') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFeedbackStore } from '@/stores/feedback'

const { t } = useI18n()
const fb = useFeedbackStore()
const previewOpen = ref(false)
const TYPES = ['bug', 'feature', 'other'] as const
const SECTION_KEYS = ['app_version', 'env_summary', 'task_context', 'log_tail'] as const
</script>

<style scoped lang="scss">
.feedback-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 20000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(15px);
  -webkit-backdrop-filter: blur(15px);
}

.feedback-modal {
  background: rgba(30, 30, 50, 0.35);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 1.5rem 2rem;
  min-width: 380px;
  max-width: 520px;
  width: 100%;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);

  .modal-title {
    color: var(--text-primary);
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 1.25rem;
  }
}

.field {
  margin-bottom: 1rem;

  .field-label {
    display: block;
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 0.4rem;
  }

  textarea,
  input[type="email"] {
    width: 100%;
    background: var(--input-bg);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    font-family: inherit;
    color: var(--text-primary);
    resize: vertical;
    box-sizing: border-box;

    &:focus {
      outline: none;
      border-color: var(--color-primary);
    }
  }
}

.type-options {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.type-option {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.875rem;
  color: var(--text-primary);
  cursor: pointer;
}

.check-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.875rem;
  color: var(--text-primary);
  cursor: pointer;
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-primary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.2rem 0;
  display: block;
  margin-top: 0.3rem;

  &:hover {
    text-decoration: underline;
  }
}

.preview {
  margin-top: 0.5rem;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  padding: 0.75rem;
  background: var(--input-bg);

  pre {
    max-height: 240px;
    overflow: auto;
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
  }
}

.preview-section {
  h6 {
    margin: 8px 0 4px;
    font-size: 0.78rem;
    color: var(--text-muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  &:first-child h6 {
    margin-top: 0;
  }
}

.preview-error {
  font-size: 0.85rem;
  color: var(--color-danger);
}

.feedback-actions {
  display: flex;
  gap: 0.6rem;
  justify-content: flex-end;
  flex-wrap: wrap;
  margin-top: 1.25rem;
}

.feedback-btn {
  padding: 0.5rem 1.1rem;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;

  &.cancel {
    background: var(--input-bg);
    color: var(--text-secondary);
    border: 1px solid var(--panel-border);

    &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
  }

  &.primary {
    background: var(--color-primary);
    color: white;

    &:hover { background: var(--color-primary-hover); }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }
}

.feedback-fade-enter-active,
.feedback-fade-leave-active {
  transition: opacity 0.15s ease;
}

.feedback-fade-enter-from,
.feedback-fade-leave-to {
  opacity: 0;
}
</style>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

export interface SelectOption {
  value: any
  label: string
  desc?: string
  badge?: 'ok' | 'err' | null
}

export interface SelectGroup {
  group: string
  options: SelectOption[]
}

export type SelectItem = SelectOption | SelectGroup

function isGroup(item: SelectItem): item is SelectGroup {
  return 'group' in item && 'options' in item
}

const { t } = useI18n()

const props = withDefaults(defineProps<{
  modelValue: any
  options: SelectItem[]
  size?: 'default' | 'sm'
  placeholder?: string
  disabled?: boolean
}>(), {
  size: 'default',
  disabled: false,
})

/** 展平所有 options（用於查找 selectedLabel） */
const flatOptions = computed(() => {
  const result: SelectOption[] = []
  for (const item of props.options) {
    if (isGroup(item)) {
      result.push(...item.options)
    } else {
      result.push(item)
    }
  }
  return result
})

/** 只有一個 group 時不顯示 group header，直接平鋪 */
const singleGroup = computed(() => {
  const groups = props.options.filter(isGroup)
  const flats = props.options.filter(i => !isGroup(i))
  return groups.length === 1 && flats.length === 0
})

/** 實際渲染的 options：單 group 時展平 */
const renderOptions = computed<SelectItem[]>(() => {
  if (singleGroup.value) {
    return (props.options[0] as SelectGroup).options
  }
  return props.options
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: any): void
}>()

const isOpen = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})

const selectedLabel = computed(() => {
  const found = flatOptions.value.find(o => o.value === props.modelValue)
  return found ? found.label : (props.placeholder ?? t('common.select'))
})

function toggle() {
  if (props.disabled) return
  isOpen.value ? close() : open()
}

function open() {
  isOpen.value = true
  nextTick(updatePosition)
}

function close() {
  isOpen.value = false
}

function select(opt: SelectOption) {
  emit('update:modelValue', opt.value)
  close()
}

function updatePosition() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const dropH = dropdownRef.value?.offsetHeight || 200
  const vh = window.innerHeight
  const spaceBelow = vh - rect.bottom
  const openUp = spaceBelow < dropH && rect.top > spaceBelow

  const s: Record<string, string> = {
    position: 'fixed',
    left: `${rect.left}px`,
    width: `${rect.width}px`,
  }

  if (openUp) {
    s.bottom = `${vh - rect.top + 4}px`
  } else {
    s.top = `${rect.bottom + 4}px`
  }

  dropdownStyle.value = s
}

function onClickOutside(e: MouseEvent) {
  if (!isOpen.value) return
  const t = e.target as Node
  if (triggerRef.value?.contains(t) || dropdownRef.value?.contains(t)) return
  close()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isOpen.value) close()
}

function onScroll(e: Event) {
  if (!isOpen.value) return
  // 不要因為 dropdown 內部滾動而關閉
  if (dropdownRef.value?.contains(e.target as Node)) return
  close()
}

onMounted(() => {
  document.addEventListener('mousedown', onClickOutside, true)
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('scroll', onScroll, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onClickOutside, true)
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('scroll', onScroll, true)
})
</script>

<template>
  <button
    ref="triggerRef"
    type="button"
    class="app-select-trigger"
    :class="[
      size === 'sm' ? 'app-select-sm' : '',
      { 'app-select-open': isOpen, 'app-select-disabled': disabled }
    ]"
    :disabled="disabled"
    @click="toggle"
  >
    <span class="app-select-value">{{ selectedLabel }}</span>
    <i class="bi bi-chevron-down app-select-chevron"></i>
  </button>

  <Teleport to="body">
    <Transition name="app-select-dd">
      <div
        v-if="isOpen"
        ref="dropdownRef"
        class="app-select-dropdown"
        :class="[size === 'sm' ? 'app-select-dropdown-sm' : '']"
        :style="dropdownStyle"
      >
        <template v-for="(item, idx) in renderOptions" :key="idx">
          <!-- Group header -->
          <template v-if="'group' in item && 'options' in item">
            <div class="app-select-group-label">{{ (item as SelectGroup).group }}</div>
            <div
              v-for="opt in (item as SelectGroup).options"
              :key="String(opt.value)"
              class="app-select-option"
              :class="{ 'app-select-option-active': opt.value === modelValue }"
              @click="select(opt)"
            >
              <div class="app-select-option-main">
                <div class="app-select-option-text">
                  <span class="app-select-option-label">{{ opt.label }}</span>
                  <small v-if="opt.desc" class="app-select-option-desc">{{ opt.desc }}</small>
                </div>
                <i
                  v-if="opt.badge != null"
                  class="bi app-select-badge"
                  :class="opt.badge === 'ok' ? 'bi-check-circle-fill badge-ok' : 'bi-x-circle-fill badge-err'"
                ></i>
              </div>
            </div>
          </template>
          <!-- Flat option -->
          <div
            v-else
            class="app-select-option"
            :class="{ 'app-select-option-active': (item as SelectOption).value === modelValue }"
            @click="select(item as SelectOption)"
          >
            <div class="app-select-option-main">
              <div class="app-select-option-text">
                <span class="app-select-option-label">{{ (item as SelectOption).label }}</span>
                <small v-if="(item as SelectOption).desc" class="app-select-option-desc">{{ (item as SelectOption).desc }}</small>
              </div>
              <i
                v-if="(item as SelectOption).badge != null"
                class="bi app-select-badge"
                :class="(item as SelectOption).badge === 'ok' ? 'bi-check-circle-fill badge-ok' : 'bi-x-circle-fill badge-err'"
              ></i>
            </div>
          </div>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.app-select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0.5rem 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: inherit;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  gap: 0.5rem;
  outline: none;
}

.app-select-trigger:hover:not(:disabled) {
  background: var(--input-bg-focus);
  border-color: var(--input-border-focus);
}

.app-select-open {
  background: var(--input-bg-focus);
  border-color: var(--input-border-focus);
}

.app-select-sm {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
}

.app-select-trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.app-select-value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-select-chevron {
  font-size: 0.65rem;
  opacity: 0.5;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.app-select-open .app-select-chevron {
  transform: rotate(180deg);
}
</style>

<!-- Dropdown styles (non-scoped because Teleport renders outside component root) -->
<style>
.app-select-dropdown {
  position: fixed;
  z-index: 9999;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  padding: 4px;
  max-height: 280px;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

[data-theme="light"] .app-select-dropdown {
  background: rgba(245, 245, 245, 0.88);
  border-color: rgba(0, 0, 0, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.app-select-dropdown::-webkit-scrollbar {
  width: 6px;
}

.app-select-dropdown::-webkit-scrollbar-track {
  background: transparent;
}

.app-select-dropdown::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}

[data-theme="light"] .app-select-dropdown::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
}

.app-select-group-label {
  padding: 0.35rem 0.75rem 0.2rem;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(255, 255, 255, 0.4);
  pointer-events: none;
  user-select: none;
}

.app-select-group-label:not(:first-child) {
  margin-top: 0.25rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 0.5rem;
}

[data-theme="light"] .app-select-group-label {
  color: rgba(26, 26, 46, 0.45);
}

[data-theme="light"] .app-select-group-label:not(:first-child) {
  border-top-color: rgba(0, 0, 0, 0.08);
}

.app-select-option {
  display: flex;
  flex-direction: column;
  padding: 0.4rem 0.75rem;
  border-radius: 5px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.85);
  transition: background 0.1s ease;
}

.app-select-option-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.app-select-option-text {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.app-select-badge {
  font-size: 0.7rem;
  flex-shrink: 0;
  line-height: 1;
  display: flex;
  align-items: center;
}

.badge-ok { color: #10b981; }
.badge-err { color: #9ca3af; }

[data-theme="light"] .badge-err { color: #6b7280; }

.app-select-option:hover {
  background: rgba(255, 255, 255, 0.1);
}

.app-select-option-active {
  background: rgba(31, 28, 44, 0.6);
  color: #b8b4d0;
}

.app-select-option-active:hover {
  background: rgba(31, 28, 44, 0.7);
}

.app-select-option-label {
  line-height: 1.4;
}

.app-select-option-desc {
  color: rgba(255, 255, 255, 0.4);
  font-size: 0.75rem;
  line-height: 1.3;
}

.app-select-dropdown-sm .app-select-option {
  padding: 0.3rem 0.6rem;
  font-size: 0.85rem;
}

/* Light theme option overrides */
[data-theme="light"] .app-select-option {
  color: rgba(26, 26, 46, 0.85);
}

[data-theme="light"] .app-select-option:hover {
  background: rgba(0, 0, 0, 0.06);
}

[data-theme="light"] .app-select-option-active {
  background: rgba(140, 130, 180, 0.18);
  color: #6b5fa0;
}

[data-theme="light"] .app-select-option-active:hover {
  background: rgba(140, 130, 180, 0.25);
}

[data-theme="light"] .app-select-option-desc {
  color: rgba(26, 26, 46, 0.45);
}

/* Transition */
.app-select-dd-enter-active,
.app-select-dd-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.app-select-dd-enter-from,
.app-select-dd-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>

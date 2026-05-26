<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppSelect, { type SelectOption } from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'


const props = defineProps<{
  fileId: string | null
  currentFileName: string
  isMultiSelect?: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const selectedModelId = usePersistedModel('upscale_model')
const selectedFaceModelId = usePersistedModel('upscale_face_model')
const upscaleScale = ref(4)
const sharpen = ref(false)
const faceRestore = ref(false)
const faceRestoreUpscale = ref(2)

const upscaleModels = computed(() => modelStore.forPanel(modelStore.byCategory('upscale')))
const faceRestoreModels = computed(() => modelStore.forPanel(modelStore.byCategory('face_restore')))

const selectedUpscaleModel = computed(() => upscaleModels.value.find(m => m.id === selectedModelId.value))
const maxScale = computed(() => selectedUpscaleModel.value?.max_scale ?? 4)
const scaleTicks = computed(() => Array.from({ length: maxScale.value - 1 }, (_, i) => i + 2))

watch(maxScale, (max) => {
  if (upscaleScale.value > max) upscaleScale.value = max
})

const selectedFaceFamily = computed(() => {
  if (selectedFaceModelId.value.startsWith('gfpgan')) return 'gfpgan'
  return ''
})

const upscaleOptions = computed<SelectOption[]>(() =>
  upscaleModels.value.map(m => ({
    value: m.id,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
)

const faceOptions = computed<SelectOption[]>(() =>
  faceRestoreModels.value.map(m => ({
    value: m.id,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
)

function selectUpscaleModel(id: string) {
  selectedModelId.value = id
}

function selectFaceModel(id: string) {
  selectedFaceModelId.value = id
}

// 當模型列表載入完成後自動選取第一個已下載的模型
watch(upscaleModels, (models) => {
  if (!selectedModelId.value) {
    const first = models.find(m => m.downloaded)
    if (first) selectedModelId.value = first.id
  }
}, { immediate: true })

watch(faceRestoreModels, (models) => {
  if (!selectedFaceModelId.value) {
    const first = models.find(m => m.downloaded)
    if (first) selectedFaceModelId.value = first.id
  }
}, { immediate: true })

onMounted(() => modelStore.ensureLoaded())

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

function getParams(): Record<string, unknown> {
  return {
    model_id: selectedModelId.value,
    scale: upscaleScale.value,
    sharpen: sharpen.value,
    face_fix: faceRestore.value,
    face_restore_model_id: faceRestore.value && selectedFaceModelId.value
      ? selectedFaceModelId.value
      : null,
    face_restore_upscale: faceRestoreUpscale.value,
  }
}

async function execute() {
  if (!await guardModelReady(selectedUpscaleModel.value?.downloaded === true, 'image')) return
  if (!props.fileId || !selectedModelId.value) return

  const taskId = await submitTask(
    '/image/upscale',
    {
      file_id: props.fileId,
      ...getParams(),
    },
    t('image.upscale.task_label'),
    'image.upscale',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

// ── Agent panel registration ──────────────────────────────────────────────────
const agentSchema = {
  panelId: 'image.upscale',
  fields: [
    { name: 'upscale_model', type: 'enum' as const,
      options: () => upscaleOptions.value.map(o => o.value) },
    { name: 'upscale_scale', type: 'number' as const,
      min: 2, max: () => maxScale.value, step: 1 },
    { name: 'sharpen', type: 'bool' as const },
    { name: 'face_restore', type: 'bool' as const },
    { name: 'face_restore_model', type: 'enum' as const,
      options: () => faceOptions.value.map(o => o.value),
      visibleWhen: () => faceRestore.value },
    { name: 'face_restore_upscale', type: 'number' as const,
      min: 1, max: 4, step: 1,
      visibleWhen: () => faceRestore.value },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.upscale.execute' },
}

useAgentPanelHost('image.upscale', {
  agentSchema,
  isMultiSelect: () => props.isMultiSelect ?? false,
  getCurrentValues: () => ({
    upscale_model: selectedModelId.value,
    upscale_scale: upscaleScale.value,
    sharpen: sharpen.value,
    face_restore: faceRestore.value,
    face_restore_model: selectedFaceModelId.value,
    face_restore_upscale: faceRestoreUpscale.value,
  }),
  setField: (field, value) => {
    switch (field) {
      case 'upscale_model':
        selectedModelId.value = value as string
        return value
      case 'upscale_scale': {
        const clamped = Math.min(Math.max(Number(value), 2), maxScale.value)
        upscaleScale.value = clamped
        return clamped
      }
      case 'sharpen':
        sharpen.value = !!value
        return sharpen.value
      case 'face_restore':
        faceRestore.value = !!value
        return faceRestore.value
      case 'face_restore_model':
        selectedFaceModelId.value = value as string
        return value
      case 'face_restore_upscale': {
        const clamped = Math.min(Math.max(Number(value), 1), 4)
        faceRestoreUpscale.value = clamped
        return clamped
      }
      default:
        throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {
    // no-op — programmatic open_dropdown is educational only
  },
  execute: async () => {
    await execute()
    return {}
  },
})

defineExpose({ execute, isDisabled, isLoading, upscaleScale, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrows-angle-expand me-2"></i>{{ $t('image.upscale.title') }}</h6>
    <p class="form-hint">{{ $t('image.upscale.description') }}</p>

    <!-- model selection -->
    <div class="form-group">
      <label>{{ $t('image.upscale.model') }}</label>
      <AppSelect
        :model-value="selectedModelId"
        :options="upscaleOptions"
        :disabled="modelStore.loading"
        :placeholder="$t('common.loading_info')"
        @update:model-value="selectUpscaleModel"
      />
    </div>

    <!-- scale factor -->
    <div class="form-group">
      <label>
        {{ $t('image.upscale.scale') }}
        <span class="param-value">{{ upscaleScale }}x</span>
      </label>
      <AppRange v-model="upscaleScale" :min="2" :max="maxScale" :step="1" :disabled="maxScale <= 2" />
      <div class="range-ticks">
        <span v-for="tick in scaleTicks" :key="tick">{{ tick }}x</span>
      </div>
    </div>

    <!-- sharpen -->
    <div class="form-group">
      <AppToggle v-model="sharpen">{{ $t('image.upscale.sharpen') }}</AppToggle>
      <small class="form-hint">{{ $t('image.upscale.sharpen_hint') }}</small>
    </div>

    <!-- face restore -->
    <div class="form-group">
      <AppToggle v-model="faceRestore">{{ $t('image.upscale.face_restore') }}</AppToggle>
      <small class="form-hint">{{ $t('image.upscale.face_restore_hint') }}</small>

      <div v-if="faceRestore" class="sub-params">
        <AppSelect
          :model-value="selectedFaceModelId"
          :options="faceOptions"
          size="sm"
          :placeholder="$t('common.select_function')"
          @update:model-value="selectFaceModel"
        />

        <!-- GFPGAN: upscale -->
        <template v-if="selectedFaceFamily === 'gfpgan'">
          <label class="sub-label">
            {{ $t('image.upscale.face_scale') }}
            <span class="param-value">{{ faceRestoreUpscale }}x</span>
          </label>
          <AppRange v-model="faceRestoreUpscale" :min="1" :max="4" :step="1" />
          <div class="range-ticks"><span>1x</span><span>4x</span></div>
        </template>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

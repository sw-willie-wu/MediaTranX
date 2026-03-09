<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppSelect, { type SelectOption } from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { apiFetch } from '@/composables/useApi'

interface ModelItem {
  id: string
  label: string
  description: string
  downloaded: boolean
  category: string
  max_scale?: number
}

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  aiEnvReady: boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const upscaleModels = ref<ModelItem[]>([])
const faceRestoreModels = ref<ModelItem[]>([])
const selectedModelId = ref('')
const selectedFaceModelId = ref('')
const upscaleScale = ref(4)
const sharpen = ref(false)
const faceRestore = ref(false)
const faceRestoreFidelity = ref(0.7)
const faceRestoreUpscale = ref(2)
const isLoadingModels = ref(false)

// 所選模型的最大 scale（預設 4）
const selectedUpscaleModel = computed(() => upscaleModels.value.find(m => m.id === selectedModelId.value))
const maxScale = computed(() => selectedUpscaleModel.value?.max_scale ?? 4)
const scaleTicks = computed(() => Array.from({ length: maxScale.value - 1 }, (_, i) => i + 2))

// 切換模型時，若當前 scale 超出新模型上限就自動截斷
watch(maxScale, (max) => {
  if (upscaleScale.value > max) upscaleScale.value = max
})

const selectedFaceFamily = computed(() => {
  if (selectedFaceModelId.value.startsWith('codeformer')) return 'codeformer'
  if (selectedFaceModelId.value.startsWith('gfpgan')) return 'gfpgan'
  return ''
})

const upscaleOptions = computed<SelectOption[]>(() =>
  upscaleModels.value.map(m => ({
    value: m.id,
    label: m.label,
    desc: m.description,
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
  const model = upscaleModels.value.find(m => m.id === id)
  if (model?.downloaded) selectedModelId.value = id
}

function selectFaceModel(id: string) {
  const model = faceRestoreModels.value.find(m => m.id === id)
  if (model?.downloaded) selectedFaceModelId.value = id
}

onMounted(async () => {
  isLoadingModels.value = true
  try {
    const res = await apiFetch('/setup/models')
    if (!res.ok) return
    const data = await res.json()
    upscaleModels.value = (data.models as ModelItem[]).filter(m => m.category === 'upscale')
    faceRestoreModels.value = (data.models as ModelItem[]).filter(m => m.category === 'face_restore')
    const firstDownloaded = upscaleModels.value.find(m => m.downloaded)
    if (firstDownloaded) selectedModelId.value = firstDownloaded.id
    const firstFace = faceRestoreModels.value.find(m => m.downloaded)
    if (firstFace) selectedFaceModelId.value = firstFace.id
  } finally {
    isLoadingModels.value = false
  }
})

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId || !selectedModelId.value) return

  const taskId = await submitTask(
    '/image/upscale',
    {
      file_id: props.fileId,
      model_id: selectedModelId.value,
      scale: upscaleScale.value,
      sharpen: sharpen.value,
      face_fix: faceRestore.value,
      face_restore_model_id: faceRestore.value && selectedFaceModelId.value
        ? selectedFaceModelId.value
        : null,
      face_restore_fidelity: faceRestoreFidelity.value,
      face_restore_upscale: faceRestoreUpscale.value,
    },
    `超解析 ${upscaleScale.value}x`,
    'image.upscale',
    props.currentFileName,
  )

  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, upscaleScale })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrows-angle-expand me-2"></i>超解析</h6>

    <!-- 模型選擇 -->
    <div class="form-group">
      <label>超解析模型</label>
      <AppSelect
        :model-value="selectedModelId"
        :options="upscaleOptions"
        :disabled="isLoadingModels"
        placeholder="載入中..."
        @update:model-value="selectUpscaleModel"
      />
      <small v-if="!selectedModelId && !isLoadingModels" class="form-hint form-hint-warn">
        <i class="bi bi-exclamation-circle"></i> 無已下載模型，請至設定下載
      </small>
    </div>

    <!-- 放大倍率 -->
    <div class="form-group">
      <label>
        放大倍率
        <span class="scale-value">{{ upscaleScale }}x</span>
      </label>
      <AppRange v-model="upscaleScale" :min="2" :max="maxScale" :step="1" :disabled="maxScale <= 2" />
      <div class="scale-ticks">
        <span v-for="t in scaleTicks" :key="t">{{ t }}x</span>
      </div>
    </div>

    <!-- 銳化 -->
    <div class="form-group">
      <AppToggle v-model="sharpen">銳化後處理</AppToggle>
      <small class="form-hint">補強邊緣銳利度，可改善油畫感</small>
    </div>

    <!-- 人臉修復 -->
    <div class="form-group">
      <AppToggle v-model="faceRestore">人臉修復</AppToggle>
      <small class="form-hint">超解析後對人臉進行修復增強</small>

      <div v-if="faceRestore" class="face-params">
        <AppSelect
          :model-value="selectedFaceModelId"
          :options="faceOptions"
          size="sm"
          placeholder="選擇人臉修復模型"
          @update:model-value="selectFaceModel"
        />

        <!-- CodeFormer: fidelity -->
        <template v-if="selectedFaceFamily === 'codeformer'">
          <label class="sub-label">
            自然度
            <span class="scale-value">{{ faceRestoreFidelity.toFixed(1) }}</span>
          </label>
          <AppRange v-model="faceRestoreFidelity" :min="0" :max="1" :step="0.1" />
          <div class="scale-ticks"><span>強修復</span><span>保留原貌</span></div>
        </template>

        <!-- GFPGAN: upscale -->
        <template v-if="selectedFaceFamily === 'gfpgan'">
          <label class="sub-label">修復放大倍率</label>
          <div class="upscale-btns">
            <button
              v-for="v in [1, 2, 4]"
              :key="v"
              class="upscale-btn"
              :class="{ active: faceRestoreUpscale === v }"
              @click="faceRestoreUpscale = v"
            >{{ v }}x</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.face-params {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.sub-label {
  font-size: 0.8rem;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
}

.upscale-btns {
  display: flex;
  gap: 6px;
}

.upscale-btn {
  flex: 1;
  padding: 0.35rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.82rem;
  transition: all 0.15s ease;

  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
  &.active {
    background: rgba(96, 165, 250, 0.15);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
}

.form-hint-warn {
  color: #fbbf24;
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.scale-value {
  font-weight: 600;
  color: var(--color-primary);
  margin-left: 6px;
}

.scale-ticks {
  display: flex;
  justify-content: space-between;
  font-size: 0.72rem;
  color: var(--text-muted);
  padding: 0 2px;
  margin-top: 2px;
}
</style>

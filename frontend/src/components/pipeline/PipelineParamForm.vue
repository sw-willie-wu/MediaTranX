<script setup lang="ts">
/**
 * Schema 生成的節點參數表單（spec B3 主軌）— registry paramSchema 直出,
 * 排版沿 SettingsCollapsible 準則（advanced 收摺）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectItem } from '@/components/common/AppSelect.vue'
import { TOOL_REGISTRY } from '@/pipeline/registry'
import type { ParamField, RecipeNode } from '@/pipeline/types'

const { t } = useI18n()

const props = defineProps<{
  node: RecipeNode
  /** 節點盤預覽模式:調的是草稿參數(按「+」加入時帶進節點),不顯示 keep-output/刪除 */
  preview?: boolean
}>()

const emit = defineEmits<{
  (e: 'update-params', params: Record<string, unknown>): void
  (e: 'update-keep-output', keep: boolean): void
  (e: 'remove'): void
}>()

const spec = computed(() => (props.node.toolKey ? TOOL_REGISTRY[props.node.toolKey] : undefined))
const basicFields = computed(() => spec.value?.paramSchema.filter(f => !f.advanced && visible(f)) ?? [])
const advancedFields = computed(() => spec.value?.paramSchema.filter(f => f.advanced && visible(f)) ?? [])
const isLeafCandidate = computed(() => props.node.kind === 'tool' || props.node.kind === 'source')

function visible(f: ParamField): boolean {
  return f.visibleWhen ? f.visibleWhen(props.node.params) : true
}

function valueOf(f: ParamField): unknown {
  return props.node.params[f.name] ?? f.default ?? (f.type === 'boolean' ? false : '')
}

function setValue(f: ParamField, raw: unknown) {
  const params = { ...props.node.params }
  if (f.type === 'number') {
    // 清空欄位回到未設定（交後端 default）,不要變成 0
    if (raw === '' || raw === null || raw === undefined) {
      delete params[f.name]
    } else {
      const n = Number(raw)
      if (Number.isFinite(n)) params[f.name] = n
      else delete params[f.name]
    }
  } else if (f.type === 'boolean') {
    params[f.name] = Boolean(raw)
  } else {
    params[f.name] = raw
  }
  // 剪除因 visibleWhen 而隱藏的欄位殘值（避免 stale 參數送後端）
  for (const field of spec.value?.paramSchema ?? []) {
    if (field.visibleWhen && !field.visibleWhen(params) && field.name in params) {
      delete params[field.name]
    }
  }
  emit('update-params', params)
}

function enumItems(f: ParamField): SelectItem[] {
  return (f.options ?? []).map(o => ({ value: o, label: o === '' ? t('pipeline.param_default') : o }))
}

function fieldLabel(f: ParamField): string {
  // registry 欄位名即後端參數名;顯示用 i18n key 存在就用、否則原名
  const key = `pipeline.param.${f.name}`
  const label = t(key)
  return label === key ? f.name : label
}
</script>

<template>
  <div v-if="node.kind === 'input'" class="param-form function-settings">
    <p class="form-hint">{{ t('pipeline.input_node_hint') }}</p>
  </div>
  <div v-else-if="spec" class="param-form function-settings">
    <h6 class="settings-title">{{ t(spec.labelKey) }}</h6>
    <p v-if="preview" class="form-hint">{{ t('pipeline.preview_hint') }}</p>

    <div v-for="f in basicFields" :key="f.name" class="form-group">
      <label>{{ fieldLabel(f) }}</label>
      <AppSelect
        v-if="f.type === 'enum'"
        :model-value="String(valueOf(f))"
        :options="enumItems(f)"
        @update:model-value="(v) => setValue(f, v)"
      />
      <input
        v-else-if="f.type === 'number'"
        type="number" class="form-input"
        :min="f.min" :max="f.max" :step="f.step ?? 1"
        :value="valueOf(f) as number"
        @change="setValue(f, ($event.target as HTMLInputElement).value)"
      />
      <label v-else-if="f.type === 'boolean'" class="checkbox-label">
        <input
          type="checkbox"
          :checked="Boolean(valueOf(f))"
          @change="setValue(f, ($event.target as HTMLInputElement).checked)"
        />
        <span>{{ t('pipeline.param_enabled') }}</span>
      </label>
      <input
        v-else
        type="text" class="form-input"
        :value="String(valueOf(f))"
        @change="setValue(f, ($event.target as HTMLInputElement).value)"
      />
    </div>

    <SettingsCollapsible v-if="advancedFields.length > 0" storage-key="pipeline_param_advanced">
      <div v-for="f in advancedFields" :key="f.name" class="form-group">
        <label>{{ fieldLabel(f) }}</label>
        <AppSelect
          v-if="f.type === 'enum'"
          :model-value="String(valueOf(f))"
          :options="enumItems(f)"
          @update:model-value="(v) => setValue(f, v)"
        />
        <input
          v-else-if="f.type === 'number'"
          type="number" class="form-input"
          :min="f.min" :max="f.max" :step="f.step ?? 1"
          :value="valueOf(f) as number"
          @change="setValue(f, ($event.target as HTMLInputElement).value)"
        />
        <label v-else-if="f.type === 'boolean'" class="checkbox-label">
          <input
            type="checkbox"
            :checked="Boolean(valueOf(f))"
            @change="setValue(f, ($event.target as HTMLInputElement).checked)"
          />
          <span>{{ t('pipeline.param_enabled') }}</span>
        </label>
        <input
          v-else
          type="text" class="form-input"
          :value="String(valueOf(f))"
          @change="setValue(f, ($event.target as HTMLInputElement).value)"
        />
      </div>
    </SettingsCollapsible>

    <div v-if="isLeafCandidate && !preview" class="form-group keep-output">
      <label class="checkbox-label">
        <input
          type="checkbox"
          :checked="node.keepOutput === true"
          @change="emit('update-keep-output', ($event.target as HTMLInputElement).checked)"
        />
        <span>{{ t('pipeline.keep_output') }}</span>
      </label>
      <p class="form-hint">{{ t('pipeline.keep_output_hint') }}</p>
    </div>

    <button v-if="!preview" class="remove-btn" @click="emit('remove')">
      <i class="bi bi-trash me-1"></i>{{ t('pipeline.remove_node') }}
    </button>
  </div>
</template>

<style lang="scss" scoped>
// 表單樣式走 tool panel 設計系統(form-group/form-input/checkbox-label/settings-title),
// 與一般工具頁右欄同款;此處只留 pipeline 專屬樣式
@use '@/styles/tool-panels-shared';

.form-hint { margin: 0; }
.keep-output { border-top: 1px solid var(--panel-border); padding-top: 0.75rem; }
.remove-btn {
  margin-top: 0.5rem; padding: 0.4rem;
  background: transparent; border: 1px solid var(--panel-border);
  border-radius: 6px; color: var(--color-danger, #dc3545);
  font-size: 0.8rem; cursor: pointer; font-family: inherit;
  &:hover { border-color: var(--color-danger, #dc3545); }
}
</style>

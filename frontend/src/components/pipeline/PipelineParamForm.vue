<script setup lang="ts">
/**
 * Schema 生成的節點參數表單（spec B3 主軌）— registry paramSchema 直出,
 * 排版沿 SettingsCollapsible 準則（advanced 收摺）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { TOOL_REGISTRY } from '@/pipeline/registry'
import type { ParamField, RecipeNode } from '@/pipeline/types'

const { t } = useI18n()

const props = defineProps<{
  node: RecipeNode
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

function fieldLabel(f: ParamField): string {
  // registry 欄位名即後端參數名;顯示用 i18n key 存在就用、否則原名
  const key = `pipeline.param.${f.name}`
  const label = t(key)
  return label === key ? f.name : label
}
</script>

<template>
  <div v-if="node.kind === 'input'" class="param-form">
    <p class="form-hint">{{ t('pipeline.input_node_hint') }}</p>
  </div>
  <div v-else-if="spec" class="param-form">
    <h6 class="form-title">{{ t(spec.labelKey) }}</h6>

    <div v-for="f in basicFields" :key="f.name" class="form-group">
      <label>{{ fieldLabel(f) }}</label>
      <select
        v-if="f.type === 'enum'"
        class="form-input"
        :value="String(valueOf(f))"
        @change="setValue(f, ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="o in f.options" :key="o" :value="o">{{ o === '' ? t('pipeline.param_default') : o }}</option>
      </select>
      <input
        v-else-if="f.type === 'number'"
        type="number" class="form-input"
        :min="f.min" :max="f.max" :step="f.step ?? 1"
        :value="valueOf(f) as number"
        @change="setValue(f, ($event.target as HTMLInputElement).value)"
      />
      <label v-else-if="f.type === 'boolean'" class="check-row">
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
        <select
          v-if="f.type === 'enum'"
          class="form-input"
          :value="String(valueOf(f))"
          @change="setValue(f, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="o in f.options" :key="o" :value="o">{{ o === '' ? t('pipeline.param_default') : o }}</option>
        </select>
        <input
          v-else-if="f.type === 'number'"
          type="number" class="form-input"
          :min="f.min" :max="f.max" :step="f.step ?? 1"
          :value="valueOf(f) as number"
          @change="setValue(f, ($event.target as HTMLInputElement).value)"
        />
        <label v-else-if="f.type === 'boolean'" class="check-row">
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

    <div v-if="isLeafCandidate" class="form-group keep-output">
      <label class="check-row">
        <input
          type="checkbox"
          :checked="node.keepOutput === true"
          @change="emit('update-keep-output', ($event.target as HTMLInputElement).checked)"
        />
        <span>{{ t('pipeline.keep_output') }}</span>
      </label>
      <p class="form-hint">{{ t('pipeline.keep_output_hint') }}</p>
    </div>

    <button class="remove-btn" @click="emit('remove')">
      <i class="bi bi-trash me-1"></i>{{ t('pipeline.remove_node') }}
    </button>
  </div>
</template>

<style lang="scss" scoped>
.param-form { display: flex; flex-direction: column; gap: 0.75rem; }
.form-title { font-size: 0.9rem; color: var(--text-primary); margin: 0; }
.form-group {
  display: flex; flex-direction: column; gap: 0.3rem;
  label { font-size: 0.8rem; color: var(--text-muted); }
}
.form-input {
  padding: 0.35rem 0.5rem;
  background: var(--input-bg);
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: inherit;
}
.check-row {
  display: flex; align-items: center; gap: 0.5rem;
  color: var(--text-primary) !important;
  input { accent-color: var(--color-primary); }
}
.form-hint { font-size: 0.75rem; color: var(--text-muted); margin: 0; }
.keep-output { border-top: 1px solid var(--panel-border); padding-top: 0.75rem; }
.remove-btn {
  margin-top: 0.5rem; padding: 0.4rem;
  background: transparent; border: 1px solid var(--panel-border);
  border-radius: 6px; color: var(--color-danger, #dc3545);
  font-size: 0.8rem; cursor: pointer; font-family: inherit;
  &:hover { border-color: var(--color-danger, #dc3545); }
}
</style>

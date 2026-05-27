<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAgentSettingsStore } from '@/stores/agentSettings'
import { useModelStore } from '@/stores/models'
import { useModelOptions } from '@/composables/useModelOptions'
import { useAgent } from '@/composables/useAgent'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectOption, SelectItem } from '@/components/common/AppSelect.vue'
import type { AgentPolicy } from '@/stores/agentSettings'

const { t } = useI18n()
const settings = useAgentSettingsStore()
const modelStore = useModelStore()
const agent = useAgent()

// Ensure model registry is loaded so the tool-capable model picker can populate
// (registry is otherwise lazy-loaded by AI 模型管理 tab only).
onMounted(() => { void modelStore.ensureLoaded() })

// Local tool-capable model options. The agent service expects the colon form
// "family:size[:quant]" (spec §5.2 n8) — registry `m.id` is dash-separated
// (e.g. "qwen3-8b-Q4_K_M") and cannot be reused as-is, so build the value
// from `family` + `variant` (variant already has the "size:quant" shape).
const localToolModels = computed<SelectOption[]>(() =>
  modelStore.byCategory('llm')
    .filter(m => m.capabilities?.includes('tools'))
    .map(m => ({ value: `${m.family}:${m.variant}`, label: m.label }))
)

const { mergedOptions } = useModelOptions('tools', localToolModels)

const POLICY_OPTIONS = computed(() => [
  { value: 'auto',     label: t('settings.agent.policy.auto') },
  { value: 'ask_all',  label: t('settings.agent.policy.ask_all') },
  { value: 'custom',   label: t('settings.agent.policy.custom') },
] as const)

// All 9 tools for per-tool policy
interface ToolEntry {
  name: string
  descKey: string
}

const TOOLS: ToolEntry[] = [
  { name: 'navigate_to',        descKey: 'agent.tool.navigate_to' },
  { name: 'select_subfunction', descKey: 'agent.tool.select_subfunction' },
  { name: 'load_file',          descKey: 'agent.tool.load_file' },
  { name: 'open_dropdown',      descKey: 'agent.tool.open_dropdown' },
  { name: 'set_field',          descKey: 'agent.tool.set_field' },
  { name: 'list_files',         descKey: 'agent.tool.list_files' },
  { name: 'get_task_status',    descKey: 'agent.tool.get_task_status' },
  { name: 'click_execute',      descKey: 'agent.tool.click_execute' },
  { name: 'click_action',       descKey: 'agent.tool.click_action' },
]

type ToolState = 'auto' | 'ask' | 'deny'

function getToolState(toolName: string): ToolState {
  if (settings.autoWhitelist.has(toolName)) return 'auto'
  if (settings.alwaysAsk.has(toolName)) return 'ask'
  return 'deny'
}

function setToolState(toolName: string, state: ToolState) {
  if (state === 'auto') {
    settings.addToWhitelist(toolName)
    settings.removeFromAlwaysAsk(toolName)
  } else if (state === 'ask') {
    settings.removeFromWhitelist(toolName)
    settings.addToAlwaysAsk(toolName)
  } else {
    // deny: remove from both
    settings.removeFromWhitelist(toolName)
    settings.removeFromAlwaysAsk(toolName)
  }
}

function setPolicy(val: AgentPolicy) {
  settings.setPolicy(val)
}

function setModel(val: string) {
  settings.setModelChoice(val)
}

function clearHistory() {
  if (window.confirm(t('settings.agent.clear_history.confirm'))) {
    agent.clearHistory()
  }
}

// ── Agent panel host (settings.agent) ────────────────────────────────────────

const POLICY_VALUES = ['auto', 'ask_all', 'custom'] as const

useAgentPanelHost('settings.agent', {
  agentSchema: {
    panelId: 'settings.agent',
    fields: [
      {
        name: 'model',
        type: 'enum',
        options: () => mergedOptions.value
          .filter((o): o is SelectOption => 'value' in o)
          .map(o => o.value),
      },
      {
        name: 'policy',
        type: 'enum',
        options: () => [...POLICY_VALUES],
      },
    ],
    actions: [
      { name: 'clear_history', label: 'Clear History' },
    ],
    execute: null,
  },
  getCurrentValues: () => ({
    model: settings.modelChoice,
    policy: settings.policy,
  }),
  setField: (field: string, value: unknown) => {
    if (field === 'model') {
      setModel(value as string)
      return settings.modelChoice
    }
    if (field === 'policy') {
      setPolicy(value as AgentPolicy)
      return settings.policy
    }
    throw new Error(`Unknown field: ${field}`)
  },
  openField: (_field: string) => {},
  execute: () => { throw new Error('agent.error.no_execute_on_settings') },
  invokeAction: (name: string) => {
    if (name === 'clear_history') {
      agent.clearHistory()
      return { ok: true }
    }
    throw new Error(`Unknown action: ${name}`)
  },
  isMultiSelect: () => false,
})
</script>

<template>
  <!-- Model selection -->
  <h6 class="section-title">{{ $t('settings.agent.title') }}</h6>

  <div class="setting-item">
    <label class="section-subtitle">{{ $t('settings.agent.model.label') }}</label>
    <AppSelect
      :model-value="settings.modelChoice"
      :options="mergedOptions"
      :placeholder="$t('settings.agent.model.placeholder')"
      size="sm"
      @update:model-value="setModel"
    />
  </div>

  <!-- Confirmation policy -->
  <h6 class="section-title mt">{{ $t('settings.agent.policy.label') }}</h6>

  <div class="setting-item policy-radio-group">
    <label
      v-for="opt in POLICY_OPTIONS"
      :key="opt.value"
      class="policy-radio-label"
    >
      <input
        type="radio"
        :value="opt.value"
        :checked="settings.policy === opt.value"
        @change="setPolicy(opt.value as AgentPolicy)"
      />
      <span>{{ opt.label }}</span>
    </label>
  </div>

  <!-- Per-tool policy (custom only) -->
  <template v-if="settings.policy === 'custom'">
    <h6 class="section-title mt">{{ $t('settings.agent.whitelist.label') }}</h6>

    <div class="tool-policy-table">
      <div v-for="tool in TOOLS" :key="tool.name" class="tool-policy-row">
        <div class="tool-policy-info">
          <span class="tool-policy-name">{{ tool.name }}</span>
          <span class="tool-policy-desc">
            {{ $te(tool.descKey) ? $t(tool.descKey) : tool.name }}
          </span>
        </div>
        <div class="tool-policy-controls">
          <label class="tool-state-label" :class="{ active: getToolState(tool.name) === 'auto' }">
            <input
              type="radio"
              :name="`tool-${tool.name}`"
              value="auto"
              :checked="getToolState(tool.name) === 'auto'"
              @change="setToolState(tool.name, 'auto')"
            />
            <span>{{ $t('settings.agent.whitelist.state_auto') }}</span>
          </label>
          <label class="tool-state-label" :class="{ active: getToolState(tool.name) === 'ask' }">
            <input
              type="radio"
              :name="`tool-${tool.name}`"
              value="ask"
              :checked="getToolState(tool.name) === 'ask'"
              @change="setToolState(tool.name, 'ask')"
            />
            <span>{{ $t('settings.agent.whitelist.state_ask') }}</span>
          </label>
          <label class="tool-state-label" :class="{ active: getToolState(tool.name) === 'deny' }">
            <input
              type="radio"
              :name="`tool-${tool.name}`"
              value="deny"
              :checked="getToolState(tool.name) === 'deny'"
              @change="setToolState(tool.name, 'deny')"
            />
            <span>{{ $t('settings.agent.whitelist.state_deny') }}</span>
          </label>
        </div>
      </div>
    </div>
  </template>

  <!-- Clear history -->
  <h6 class="section-title mt">{{ $t('settings.agent.clear_history.label') }}</h6>

  <div class="setting-item">
    <button class="btn-secondary" @click="clearHistory">
      <i class="bi bi-trash3"></i>
      {{ $t('settings.agent.clear_history.label') }}
    </button>
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.policy-radio-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.policy-radio-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text-secondary);

  input[type="radio"] {
    accent-color: var(--color-primary);
  }
}

.tool-policy-table {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.tool-policy-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  background: var(--input-bg);
  gap: 0.5rem;

  &:hover { background: var(--panel-bg-hover); }
}

.tool-policy-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.tool-policy-name {
  font-size: 0.78rem;
  font-family: monospace;
  color: var(--text-primary);
  font-weight: 500;
}

.tool-policy-desc {
  font-size: 0.7rem;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-policy-controls {
  display: flex;
  gap: 0.4rem;
  flex-shrink: 0;
}

.tool-state-label {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  cursor: pointer;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  font-size: 0.7rem;
  color: var(--text-muted);
  border: 1px solid transparent;
  transition: all 0.15s;

  input[type="radio"] {
    display: none;
  }

  &.active {
    color: var(--color-primary);
    border-color: rgba(124, 111, 173, 0.4);
    background: rgba(124, 111, 173, 0.1);
  }

  &:hover:not(.active) {
    background: var(--panel-bg-hover);
    color: var(--text-secondary);
  }
}
</style>

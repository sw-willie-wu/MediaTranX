/**
 * Tests for the per-remote chunk_ctx_budget slider (ollama-only, rightmost=auto).
 *
 * Strategy:
 *  - Mount ModelDownloadManager with vi.mock for all stores.
 *  - Navigate to the "remote" tab (set via activeTab).
 *  - Assert: slider renders for ollama, not for openai.
 *  - Assert: auto (rightmost) position → payload.chunk_ctx_budget === null.
 *  - Assert: numeric position → integer payload.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'

// ── stub child components ────────────────────────────────────────────────
vi.mock('@/components/common/AppModelGroupList.vue', () => ({
  default: { template: '<div class="stub-model-group-list" />' },
}))
vi.mock('@/components/common/AppSelect.vue', () => ({
  default: {
    props: ['modelValue', 'options'],
    emits: ['update:modelValue'],
    template: `<select @change="$emit('update:modelValue', $event.target.value)">
      <option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>`,
  },
}))
vi.mock('@/components/common/AppToggle.vue', () => ({
  default: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
  },
}))

// ── stub composables ─────────────────────────────────────────────────────
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: vi.fn() }) }))
vi.mock('@/composables/useApi', () => ({ apiFetch: vi.fn(async () => ({ ok: true, json: async () => ({}) })) }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

// ── mock stores ──────────────────────────────────────────────────────────
const mockAddConnection = vi.fn()
const mockUpdateConnection = vi.fn()
const mockRevealKey = vi.fn()
const mockToggleConnection = vi.fn()
const mockDeleteConnection = vi.fn()
const mockFetchConnModels = vi.fn()
const mockClearConnCache = vi.fn()
const mockToggleEnabled = vi.fn()

// Mutable reactive state for the remote store (reset between tests)
let mockConnections = ref<any[]>([])
let mockConnModels = ref<Record<number, any[]>>({})
let mockConnLoading = ref<Record<number, boolean>>({})
let mockConnError = ref<Record<number, boolean>>({})
let mockEnabledIds = ref<Set<string>>(new Set())

vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({
    connections: mockConnections,
    connModels: mockConnModels,
    connLoading: mockConnLoading,
    connError: mockConnError,
    enabledIds: mockEnabledIds,
    addConnection: mockAddConnection,
    updateConnection: mockUpdateConnection,
    deleteConnection: mockDeleteConnection,
    toggleConnection: mockToggleConnection,
    fetchConnModels: mockFetchConnModels,
    clearConnCache: mockClearConnCache,
    toggleEnabled: mockToggleEnabled,
    revealKey: mockRevealKey,
    ensureLoaded: vi.fn(),
    fetchAll: vi.fn(),
  }),
}))

vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    loading: false,
    loaded: true,
    categories: [],
    byCategory: () => [],
    fetchModels: vi.fn(),
    setDownloaded: vi.fn(),
  }),
}))

vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    showAllModels: false,
    setShowAllModels: vi.fn(),
  }),
}))

vi.mock('@/stores/tasks', () => ({
  useTaskStore: () => ({
    tasks: new Map(),
    addTask: vi.fn(),
  }),
}))

// ── minimal i18n ─────────────────────────────────────────────────────────
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      settings: {
        models: {
          display_title: 'Display',
          show_all_models: 'Show all',
          show_all_models_hint: '',
          title: 'Models',
          hint: '',
          loading: 'Loading…',
          category_local: 'Local',
          refresh: 'Refresh',
          reveal_failed: '',
          key_copied: '',
          copy_failed: '',
          download_success: '',
          download_failed: '',
        },
        remote: {
          title: 'Cloud Models',
          hint: '',
          no_connections: 'No connections',
          add: 'Add Connection',
          provider: 'Provider',
          name: 'Name',
          name_placeholder: 'e.g. Local Ollama',
          endpoint: 'Endpoint',
          test: 'Test',
          save: 'Save',
          connected: 'Connected',
          models_available: 'models available',
          connection_failed: 'Connection failed',
          no_models: 'No models',
          fetch_failed: 'Fetch failed',
          edit: 'Edit',
          refresh: 'Refresh',
          delete: 'Delete',
          copy_key: 'Copy key',
          chunkCtxBudget: 'Batch context budget',
          chunkCtxBudgetAuto: 'auto',
          chunkCtxBudgetHint: 'auto = derive from the model automatically.',
        },
      },
      common: {
        cancel: 'Cancel',
        save: 'Save',
        optional: 'optional',
      },
    },
  },
})

// ────────────────────────────────────────────────────────────────────────────
import ModelDownloadManager from '../ModelDownloadManager.vue'

function makeWrapper() {
  return mount(ModelDownloadManager, {
    global: { plugins: [i18n] },
  })
}

async function openRemoteTab(wrapper: ReturnType<typeof makeWrapper>) {
  const tabBtns = wrapper.findAll('button.category-tab')
  const remoteBtn = tabBtns.find(b => b.text().includes('Cloud Models'))
  if (!remoteBtn) throw new Error('Remote tab button not found')
  await remoteBtn.trigger('click')
  await flushPromises()
}

async function openAddForm(wrapper: ReturnType<typeof makeWrapper>) {
  const allBtns = wrapper.findAll('button')
  const addConnBtn = allBtns.find(b => b.text().includes('Add Connection'))
  if (!addConnBtn) throw new Error('"Add Connection" button not found')
  await addConnBtn.trigger('click')
  await flushPromises()
}

// ────────────────────────────────────────────────────────────────────────────
describe('chunk_ctx_budget slider — ADD form', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockConnections.value = []
    mockConnModels.value = {}
    mockConnLoading.value = {}
    mockConnError.value = {}
  })

  it('(a) renders the budget control when provider is ollama', async () => {
    const wrapper = makeWrapper()
    await openRemoteTab(wrapper)
    await openAddForm(wrapper)

    const slider = wrapper.find('[data-testid="budget-slider"]')
    expect(slider.exists()).toBe(true)
  })

  it('(d) does NOT render the budget control for a non-ollama provider', async () => {
    const wrapper = makeWrapper()
    await openRemoteTab(wrapper)
    await openAddForm(wrapper)

    // Switch provider to 'openai'
    const select = wrapper.find('select')
    await select.setValue('openai')
    await flushPromises()

    const slider = wrapper.find('[data-testid="budget-slider"]')
    expect(slider.exists()).toBe(false)
  })

  it('(b) rightmost stop (auto) → addConnection called with chunk_ctx_budget === null', async () => {
    mockAddConnection.mockResolvedValue(true)
    const wrapper = makeWrapper()
    await openRemoteTab(wrapper)
    await openAddForm(wrapper)

    // Fill required name field
    const inputs = wrapper.findAll('input.form-input')
    const nameInput = inputs[0]
    await nameInput.setValue('My Ollama')

    // Slider defaults to auto (rightmost) — verify the label
    const label = wrapper.find('[data-testid="budget-label"]')
    expect(label.text()).toBe('auto')

    // Submit
    const saveBtn = wrapper.findAll('button').find(b => b.text().includes('Save'))
    if (!saveBtn) throw new Error('Save button not found')
    await saveBtn.trigger('click')
    await flushPromises()

    expect(mockAddConnection).toHaveBeenCalledTimes(1)
    const payload = mockAddConnection.mock.calls[0][0]
    expect(payload.chunk_ctx_budget).toBeNull()
  })

  it('(c) numeric stop → addConnection called with an integer chunk_ctx_budget', async () => {
    mockAddConnection.mockResolvedValue(true)
    const wrapper = makeWrapper()
    await openRemoteTab(wrapper)
    await openAddForm(wrapper)

    // Fill required name field
    const inputs = wrapper.findAll('input.form-input')
    const nameInput = inputs[0]
    await nameInput.setValue('My Ollama')

    // Move slider to index 0 (= 2048)
    const slider = wrapper.find('[data-testid="budget-slider"]')
    await slider.setValue('0')
    await flushPromises()

    // Label should show an integer
    const label = wrapper.find('[data-testid="budget-label"]')
    expect(Number.isInteger(Number(label.text()))).toBe(true)

    // Submit
    const saveBtn = wrapper.findAll('button').find(b => b.text().includes('Save'))
    if (!saveBtn) throw new Error('Save button not found')
    await saveBtn.trigger('click')
    await flushPromises()

    expect(mockAddConnection).toHaveBeenCalledTimes(1)
    const payload = mockAddConnection.mock.calls[0][0]
    expect(typeof payload.chunk_ctx_budget).toBe('number')
    expect(Number.isInteger(payload.chunk_ctx_budget)).toBe(true)
    expect(payload.chunk_ctx_budget).toBeGreaterThan(0)
  })
})

// ────────────────────────────────────────────────────────────────────────────
describe('chunk_ctx_budget slider — EDIT form', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockConnections.value = []
    mockConnModels.value = {}
    mockConnLoading.value = {}
    mockConnError.value = {}
  })

  it('renders the budget control for an ollama connection being edited', async () => {
    mockConnections.value = [
      { id: 1, provider: 'ollama', name: 'Local Ollama', endpoint: 'http://localhost:11434', enabled: true, chunk_ctx_budget: null },
    ]

    const wrapper = makeWrapper()
    await openRemoteTab(wrapper)
    await flushPromises()

    const editBtn = wrapper.find('button[title="Edit"]')
    if (!editBtn.exists()) throw new Error('Edit button not found')
    await editBtn.trigger('click')
    await flushPromises()

    const slider = wrapper.find('[data-testid="budget-slider"]')
    expect(slider.exists()).toBe(true)
  })

  it('does NOT render the budget control when editing a non-ollama connection', async () => {
    mockConnections.value = [
      { id: 2, provider: 'openai', name: 'OpenAI', endpoint: 'https://api.openai.com', enabled: true },
    ]

    const wrapper = makeWrapper()
    await openRemoteTab(wrapper)
    await flushPromises()

    const editBtn = wrapper.find('button[title="Edit"]')
    if (!editBtn.exists()) throw new Error('Edit button not found')
    await editBtn.trigger('click')
    await flushPromises()

    const slider = wrapper.find('[data-testid="budget-slider"]')
    expect(slider.exists()).toBe(false)
  })

  it('seeds the slider from conn.chunk_ctx_budget and sends it on save', async () => {
    mockUpdateConnection.mockResolvedValue(true)
    mockConnections.value = [
      { id: 1, provider: 'ollama', name: 'Local Ollama', endpoint: 'http://localhost:11434', enabled: true, chunk_ctx_budget: 8192 },
    ]

    const wrapper = makeWrapper()
    await openRemoteTab(wrapper)
    await flushPromises()

    const editBtn = wrapper.find('button[title="Edit"]')
    await editBtn.trigger('click')
    await flushPromises()

    // Label should show 8192
    const label = wrapper.find('[data-testid="budget-label"]')
    expect(label.exists()).toBe(true)
    expect(label.text()).toBe('8192')

    // Save
    const saveBtn = wrapper.findAll('button').find(b => b.text() === 'Save')
    if (!saveBtn) throw new Error('Save button not found')
    await saveBtn.trigger('click')
    await flushPromises()

    expect(mockUpdateConnection).toHaveBeenCalledTimes(1)
    const [, payload] = mockUpdateConnection.mock.calls[0]
    expect(payload.chunk_ctx_budget).toBe(8192)
  })
})

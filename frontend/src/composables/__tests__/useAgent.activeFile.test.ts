/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * @vitest-environment jsdom
 *
 * v1.7.1 C — 跨 domain 檔案上下文污染。
 * 鎖住 snapshot.active_file 的來源＝當前 view handle 的 activeFile，而非全域
 * filesStore.currentFile（切 domain 從不重置、會殘留他 domain 檔）。
 * 用 useAgent.wiring.test.ts 的 fake-agent harness：useAgent 於 runAgent 前把 snapshot
 * 寫進 agent.state，測試跑一輪後直接讀 fake.agent.state.snapshot.active_file。
 */
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { viewRegistry } from '@/stores/viewRegistry'
import { useFilesStore } from '@/stores/files'
import { useAgent, _resetAgent } from '@/composables/useAgent'
import { makeFakeAgent } from './_fakeAgent'

describe('snapshot.active_file 來源 = 當前 view handle（非全域 currentFile）', () => {
  let router: ReturnType<typeof createRouter>

  beforeEach(() => {
    setActivePinia(createPinia())
    _resetAgent()
    viewRegistry._clearAll()
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/document', component: { template: '<div/>' } },
        { path: '/', component: { template: '<div/>' } },
      ],
    })
  })

  async function runOneRound() {
    const fake = makeFakeAgent(() => ({ textDeltas: ['ok'] }))
    const host = defineComponent({
      setup() {
        const agent = useAgent({ agentFactory: fake.factory })
        return { agent }
      },
      template: '<div/>',
    })
    const w = mount(host, { global: { plugins: [router] } })
    await w.vm.agent.sendUserText('hi')
    return fake
  }

  it('view.activeFile=null → snapshot.active_file 為 null，即使全域 currentFile 有他 domain 檔', async () => {
    // 全域 currentFile 故意塞 video 的 testB.mp4（模擬先在 video 上傳過）
    const files = useFilesStore()
    ;(files as any).currentFile = { id: 'v1', name: 'testB.mp4', originalName: 'testB.mp4', type: 'video' }

    // 當前 domain = document，且 document 無檔（activeFile=null）
    viewRegistry.register('document', {
      currentFunction: ref('translate'),
      setCurrentFunction: () => {},
      activeFile: ref(null),
    })
    await router.push('/document')
    await router.isReady()

    const fake = await runOneRound()
    expect((fake.agent.state as any).snapshot.active_file).toBeNull()
  })

  it('view.activeFile 有值 → snapshot.active_file 用 handle 的值', async () => {
    const files = useFilesStore()
    ;(files as any).currentFile = { id: 'v1', name: 'testB.mp4', originalName: 'testB.mp4', type: 'video' }

    viewRegistry.register('document', {
      currentFunction: ref('translate'),
      setCurrentFunction: () => {},
      activeFile: ref({ id: 'd1', name: 'docA.pdf', kind: 'document' }),
    })
    await router.push('/document')
    await router.isReady()

    const fake = await runOneRound()
    const af = (fake.agent.state as any).snapshot.active_file
    expect(af).toEqual({ id: 'd1', name: 'docA.pdf', kind: 'document' })
  })
})

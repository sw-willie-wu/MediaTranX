<script setup>
import IconMinimize from './icons/IconMinimize.vue'
import IconMaximize from './icons/IconMaximize.vue'
import IconRestore from './icons/IconRestore.vue'
import IconClose from './icons/IconClose.vue'
import { ref, onMounted } from 'vue'

const isMaximized = ref(false)

function minimize() {
  window.electron?.minimize()
}

function toggleFullScreen() {
  window.electron?.maximize()
}

function close() {
  window.electron?.close()
}

onMounted(async () => {
  if (window.electron) {
    isMaximized.value = await window.electron.isMaximized()
    window.electron.onMaximizeChange((val) => {
      isMaximized.value = val
    })
  }
})
</script>

<template>
  <div class="titlebar fixed-top pywebview-drag-region d-flex justify-content-end">
    <button class="window-btn" @click="minimize"><IconMinimize /></button>
    <button class="window-btn" @click="toggleFullScreen"><IconMaximize v-if="!isMaximized" /><IconRestore v-else /></button>
    <button class="window-btn close" @click="close"><IconClose /></button>
  </div>
</template>

<style lang="scss" scoped>
.titlebar {
  width: 100vw;
  height: 30px;
  background-color: transparent;
  z-index: 100;
  user-select: none;
  -webkit-user-select: none;
  -webkit-app-region: drag;
}

.window-btn {
  width:50px;
  height: 35px;
  padding: 0 0 5px 0;
  border: 0;
  background-color: transparent;
  color: white;
  -webkit-app-region: no-drag;
  svg {
    width: 20px;
    height: 20px;
  }
  &:hover {
    background-color: rgb(65, 65, 65);
  }
  &:active {
    background-color: rgb(80, 80, 80);
  }
  &.close {
    &:hover {
      background-color: rgb(232, 17, 35);
    }
    &:active {
      background-color: red;
    }
    padding-right: 4px;
  }
}
</style>
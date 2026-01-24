<script setup>
import FilePreview from '@/components/FilePreview.vue'
</script>

<template>
  <div class="d-flex work-panel">
    <div class="preview-panel d-flex justify-content-center align-items-center">
      <FilePreview />
    </div>
    <div class="tool-panel">
      <div class="row">
        <div class="col-12">
          畫質提高
        </div>
        <div class="col-12">
          影像去背
        </div>
        <div class="col-12">
          文字辨識
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
</style>
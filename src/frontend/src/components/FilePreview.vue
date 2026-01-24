<template>
    <div class="panel">
        <div v-if="!fileURL" class="drop-area d-flex justify-content-center align-items-center"
            @click="openFileDialog" @dragover.prevent="dragOver = true" @dragleave="dragOver = false"
            @drop.prevent="handleDrop">
            <button class="btn btn-outline-light">點擊 / 拖曳檔案至此</button>
            <input type="file" ref="fileInput" class="d-none" @change="handleFileInput" />
        </div>

        <div v-if="fileURL" class="preview d-flex justify-content-center align-items-center">
            <img v-if="fileURL && fileType.startsWith('image/')" :src="fileURL" class="img-fluid rounded" />
            <audio v-else-if="fileURL && fileType.startsWith('audio/')" :src="fileURL" controls class="w-100 mt-2" />
            <video v-else-if="fileURL && fileType.startsWith('video/')" :src="fileURL" controls class="w-100 rounded" />
            <pre v-else-if="textContent" class="bg-dark text-success p-3 rounded">{{ textContent }}</pre>
        </div>
    </div>
</template>

<script setup>
import { ref } from 'vue'

const fileInput = ref(null)
const dragOver = ref(false)
const fileURL = ref('')
const fileType = ref('')
const textContent = ref('')

const openFileDialog = () => {
    fileInput.value?.click()
}

const handleFile = (file) => {
    fileType.value = file.type
    textContent.value = ''
    fileURL.value = ''

    if (fileType.value.startsWith('image/') || fileType.value.startsWith('audio/') || fileType.value.startsWith('video/')) {
        fileURL.value = URL.createObjectURL(file)
    } else {
        const reader = new FileReader()
        reader.onload = (e) => {
            textContent.value = e.target.result
        }
        reader.readAsText(file)
    }
}

const handleFileInput = (e) => {
    const file = e.target.files[0]
    if (file) handleFile(file)
}

const handleDrop = (e) => {
    dragOver.value = false
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
}
</script>

<style scoped>
.panel {
    width: 100%;
    height: 100%;
}

.drop-area {
    cursor: pointer;
    transition: background 0.3s ease;
    height: 100%;
    font-size: 1rem;
}

.preview {
    height: 100%;
    img {
        max-height: 65vh;
    }
}

/* .preview img,
.preview video {
    max-height: 400px;
} */
</style>
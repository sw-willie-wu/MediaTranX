<script setup lang="ts">
defineProps<{
  content: string
}>()
</script>

<template>
  <div class="user-message">
    <p class="user-message-text">{{ content }}</p>
  </div>
</template>

<style lang="scss" scoped>
.user-message {
  align-self: flex-end;
  max-width: 80%;
}

.user-message-text {
  background: var(--color-primary);
  color: white;
  padding: 0.5rem 0.75rem;
  border-radius: 12px 12px 2px 12px;
  font-size: 0.85rem;
  line-height: 1.5;
  margin: 0;
  word-break: break-word;
}
</style>

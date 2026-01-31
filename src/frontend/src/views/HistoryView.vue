<template>
  <div class="placeholder-page">
    <i class="bi bi-clock-history"></i>
    <h2>歷史紀錄</h2>
    <p>此功能即將推出</p>
  </div>
</template>

<style lang="scss" scoped>
.placeholder-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 40px);
  color: var(--text-muted);

  i {
    font-size: 4rem;
    margin-bottom: 1rem;
  }

  h2 {
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
  }

  p {
    font-size: 0.95rem;
  }
}
</style>

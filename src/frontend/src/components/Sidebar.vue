<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const refs = {}
const indicatorTop = ref(0)
const menus = ['image', 'video', 'audio', 'convert', 'settings']

function updateIndicator() {
  const activeEl = refs[String(route.path).split('/').filter(elem => menus.includes(elem))?.at(0)]
  if (activeEl) {
    indicatorTop.value = activeEl.offsetTop
  }
}

onMounted(updateIndicator)
watch(() => route.path, updateIndicator)

</script>

<template>
  <div class="sidebar" data-bs-theme="dark">
    <div class="indicator"
      :style="{ top: `calc(${indicatorTop}px + .63rem)`, display: indicatorTop < 50 ? 'none' : 'block' }"></div>
    <div class="brand">
      MediaTranX
    </div>
    <!-- 上方功能選單 -->
    <ul class="sidebar-menu">
      <li class="sidebar-menu-items" :ref="el => refs['image'] = el">
        <router-link to="/image" class="d-flex align-items-center">
          <i class="bi bi-image-fill me-2"></i>
          <span>相片處理</span>
        </router-link>
      </li>
      <li class="sidebar-menu-items" :ref="el => refs['video'] = el">
        <router-link to="/video" class="d-flex align-items-center">
          <i class="bi bi-film me-2"></i>
          <span>影片處理</span>
        </router-link>
      </li>
      <li class="sidebar-menu-items" :ref="el => refs['audio'] = el">
        <router-link to="/audio" class="d-flex align-items-center">
          <i class="bi bi-music-note-beamed me-2"></i>
          <span>音訊處理</span>
        </router-link>
      </li>
      <li class="sidebar-menu-items" :ref="el => refs['convert'] = el">
        <router-link to="/convert" class="d-flex align-items-center">
          <i class="bi bi-arrow-repeat me-2"></i>
          <span>格式轉換</span>
        </router-link>
      </li>
    </ul>

    <!-- 下方設定 -->
    <ul class="sidebar-menu mt-auto">
      <li class="sidebar-menu-items" :ref="el => refs['settings'] = el">
        <router-link to="/settings" class="d-flex align-items-center">
          <i class="bi bi-gear-fill me-2"></i>
          <span>設定</span>
        </router-link>
      </li>
    </ul>
    <span class="footer">© 2025 MediaTranX</span>
  </div>
</template>

<style scoped>
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  height: 100%;
  width: 230px;
  padding: 1rem 0.5rem;
  display: flex;
  flex-direction: column;
}

.indicator {
  position: absolute;
  left: .7rem;
  width: 3px;
  height: 1.2rem;
  background-color: white;
  border-radius: 2px;
  transition: top 0.15s ease-in-out;
  z-index: 1;
}

.brand {
  color: white;
  padding: 1rem;
  font-size: 1.5rem;
  font-weight: 700;
  font-style: italic;
}

.sidebar-menu {
  list-style: none;
  padding: 0;
  margin: 0;
}

.sidebar-menu-items {
  font-size: 1rem;
  margin: .5rem 0;
  position: relative;

  a {
    color: #ffffffcc;
    text-decoration: none;
    padding: 0.4rem 1rem;
    border-radius: 8px;
    transition: 0.1s ease;

    &:hover {
      color: #fff;
      background: rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(15px) saturate(120%);
      -webkit-backdrop-filter: blur(15px) saturate(120%);
      box-shadow: 0 0 20px rgba(0, 0, 0, 0.25);
    }

    &:active {
      background: rgba(255, 255, 255, 0.25);
    }
  }
}

.footer {
  padding-left: 1rem;
}


/* .sidebar-menu a {
  color: #ffffffcc;
  text-decoration: none;
  padding: 0.4rem 0.75rem;
  border-radius: 0.5rem;
  transition: background-color 0.2s ease;
} */

/* .sidebar-menu a:hover {
  background-color: #16796f55;
  color: #fff;
} */
</style>

<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import Titlebar from './components/Titlebar.vue'
import Sidebar from './components/Sidebar.vue'
// import HelloWorld from './components/HelloWorld.vue'
</script>

<template>
  <div class="wrapper">
    <Titlebar />
    <Sidebar />
    <div class="workspace">
      <RouterView />
    </div>
  </div>
</template>

<style lang="scss">
.wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.workspace {
  /* background-color: #dbd2e3; */
  /* background: rgba(255, 255, 255, 0.5); */
  /* backdrop-filter: blur(15px) saturate(120%); */
  /* -webkit-backdrop-filter: blur(15px) saturate(120%); */
  /* border-right: 1px solid rgba(255, 255, 255, 0.15); */
  /* box-shadow: 2px 0 20px rgba(0, 0, 0, 0.25); */
  margin-top: 3rem;
  margin-left: 250px;
  /* height: calc(100vh - 5rem); */
  /* width: calc(100vw - 250px); */
  /* border-radius: 15px; */
  /* width: calc(100vw - 300px);
  position: relative;
  left: 0;
  top: 5rem; */
}

.preview-panel {
  color: white;
  min-height: calc(100vh - 4.5rem);
  padding: 1rem;
  width: calc(100vw - 250px - 400px - 3rem);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(15px) saturate(150%);
  -webkit-backdrop-filter: blur(15px) saturate(150%);
  border-right: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 2px 0 20px rgba(0, 0, 0, 0.25);
}

.tool-panel {
  position: absolute;
  right: 1.5rem;
  padding: 1rem;
  min-height: calc(100vh - 4.5rem);
  width: 400px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(15px) saturate(150%);
  -webkit-backdrop-filter: blur(15px) saturate(150%);
  border-right: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 2px 0 20px rgba(0, 0, 0, 0.25);
}

/* header {
  line-height: 1.5;
  max-height: 100vh;
}

.logo {
  display: block;
  margin: 0 auto 2rem;
}

nav {
  width: 100%;
  font-size: 12px;
  text-align: center;
  margin-top: 2rem;
}

nav a.router-link-exact-active {
  color: var(--color-text);
}

nav a.router-link-exact-active:hover {
  background-color: transparent;
}

nav a {
  display: inline-block;
  padding: 0 1rem;
  border-left: 1px solid var(--color-border);
}

nav a:first-of-type {
  border: 0;
}

@media (min-width: 1024px) {
  header {
    display: flex;
    place-items: center;
    padding-right: calc(var(--section-gap) / 2);
  }

  .logo {
    margin: 0 2rem 0 0;
  }

  header .wrapper {
    display: flex;
    place-items: flex-start;
    flex-wrap: wrap;
  }

  nav {
    text-align: left;
    margin-left: -1rem;
    font-size: 1rem;

    padding: 1rem 0;
    margin-top: 1rem;
  }
} */
</style>

<script setup>
import {isDark, toggleTheme} from './theme.js'

const nav = [
  {to: '/overview', label: 'Overview', icon: 'pi pi-chart-bar'},
  {to: '/jobs', label: 'Jobs', icon: 'pi pi-calendar'},
  {to: '/logs', label: 'Logs', icon: 'pi pi-history'},
  {to: '/flags', label: 'Settings', icon: 'pi pi-sliders-h'},
]
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <i class="pi pi-bolt"/>
        <span>Bot Dashboard</span>
      </div>
      <nav class="nav">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-link">
          <i :class="item.icon"/>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-footer">
        <Button
            :icon="isDark ? 'pi pi-sun' : 'pi pi-moon'"
            text rounded severity="secondary"
            :aria-label="isDark ? 'Light mode' : 'Dark mode'"
            v-tooltip.top="isDark ? 'Light mode' : 'Dark mode'"
            @click="toggleTheme"
        />
      </div>
    </aside>

    <main class="content">
      <RouterView/>
    </main>

    <Toast position="bottom-right"/>
    <ConfirmDialog/>
  </div>
</template>

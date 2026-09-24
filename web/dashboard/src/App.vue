<script setup>
import {computed} from 'vue'
import {useToast} from 'primevue/usetoast'
import {isDark, toggleTheme} from './theme.js'
import {connectEvents, liveStatus, onEvent} from './events.js'
import {activeRuns, runLabel, trackRuns} from './runs.js'
import {durationHuman} from './format.js'

const toast = useToast()

const nav = [
  {to: '/overview', label: 'Overview', icon: 'pi pi-chart-bar'},
  {to: '/jobs', label: 'Jobs', icon: 'pi pi-calendar'},
  {to: '/logs', label: 'Logs', icon: 'pi pi-history'},
  {to: '/flags', label: 'Settings', icon: 'pi pi-sliders-h'},
]

connectEvents()

const RUN_TOASTS = {
  success: {severity: 'success', summary: 'Run finished'},
  failed: {severity: 'error', summary: 'Run failed'},
  timeout: {severity: 'warn', summary: 'No answer from the bot'},
  error: {severity: 'error', summary: 'Run error'},
}

trackRuns((run) => {
  const took = run.finished_ts ? ` · ${durationHuman(run.finished_ts - run.started_ts)}` : ''
  const ok = run.status === 'success'
  toast.add({
    ...(RUN_TOASTS[run.status] || RUN_TOASTS.error),
    detail: ok ? `${runLabel(run)}${took}` : `${runLabel(run)}: ${run.result}`,
    life: ok ? 5000 : 15000,
  })
})

// scheduled runs that fail (manual runs are reported above, they carry a run_id)
onEvent('log', ({source, entry}) => {
  if (source !== 'PublicScheduler' || entry?.action !== 'run' || entry.phase !== 'failed' || entry.run_id) return
  toast.add({
    severity: 'error',
    summary: 'Scheduled job failed',
    detail: `${entry.job_id || entry.job}: ${entry.error || 'unknown error'}`,
    life: 15000,
  })
})

const LIVE = {
  live: {label: 'Live', cls: 'ok', tip: 'Receiving live updates'},
  connecting: {label: 'Connecting', cls: 'warn', tip: 'Connecting to live updates…'},
  reconnecting: {label: 'Reconnecting', cls: 'warn', tip: 'Live updates interrupted; reconnecting…'},
}
const live = computed(() => LIVE[liveStatus.value] || LIVE.connecting)
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
          <Badge v-if="item.to === '/jobs' && activeRuns.length" :value="activeRuns.length" severity="info"
                 class="nav-badge" v-tooltip.right="`${activeRuns.length} manual run(s) in progress`"/>
        </RouterLink>
      </nav>
      <div class="sidebar-footer">
        <span class="live" :class="live.cls" v-tooltip.top="live.tip">
          <i class="live-dot" :class="{pulse: liveStatus !== 'live'}"/>
          <span class="live-label">{{ live.label }}</span>
        </span>
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

<style scoped>
.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .5rem;
}

.live {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  font-size: .8rem;
  font-weight: 600;
  padding-left: .5rem;
}

.live-dot {
  width: .5rem;
  height: .5rem;
  border-radius: 50%;
  background: currentColor;
}

.nav-badge {
  margin-left: auto;
}

@media (max-width: 800px) {
  .live-label {
    display: none;
  }
}
</style>

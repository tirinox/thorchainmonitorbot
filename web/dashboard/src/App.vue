<script setup>
import {computed, onMounted, provide, ref, watchEffect} from 'vue'
import {useRoute} from 'vue-router'
import {useToast} from 'primevue/usetoast'
import {isDark, toggleTheme} from './theme.js'
import {displayMode, displayTz, toggleDisplayTz, tzShortName} from './timezone.js'
import {connectEvents, liveStatus, onEvent} from './events.js'
import {activeRuns, runLabel, trackRuns} from './runs.js'
import {durationHuman} from './format.js'
import {api} from './api.js'
import {usePolling} from './composables/usePolling.js'

const toast = useToast()

const nav = [
  {to: '/', label: 'Status', icon: 'pi pi-home'},
  {to: '/overview', label: 'Overview', icon: 'pi pi-chart-bar'},
  {to: '/jobs', label: 'Jobs', icon: 'pi pi-calendar'},
  {to: '/logs', label: 'Logs', icon: 'pi pi-history'},
  {to: '/activity', label: 'Activity', icon: 'pi pi-user-edit'},
  {to: '/flags', label: 'Settings', icon: 'pi pi-sliders-h'},
]

// ---- health summary: polled once for the whole app, even in a background tab, so the tab title and
// icon can tell you something is wrong while you look elsewhere; the Status page reads the same data
const summary = usePolling(api.summary, {
  interval: 60000,
  refreshOn: ['scanner', 'fetchers', 'log', 'flags', 'run'],
  eventDelay: 2000,
  pauseWhenHidden: false,
})
provide('summary', summary)

const problemCount = computed(() =>
    (summary.data.value?.checks || []).filter(c => c.status === 'warn' || c.status === 'error').length)

const route = useRoute()
watchEffect(() => {
  const page = route.meta.title ? `${route.meta.title} · Bot Dashboard` : 'Bot Dashboard'
  document.title = problemCount.value ? `(${problemCount.value}) ${page}` : page
})

const FAVICON_COLORS = {ok: '#10b981', warn: '#f59e0b', error: '#ef4444', unknown: '#9ca3af'}
watchEffect(() => {
  const status = summary.data.value?.status
  const dot = status
      ? `<circle cx='76' cy='76' r='22' fill='${FAVICON_COLORS[status] || FAVICON_COLORS.unknown}' stroke='white' stroke-width='6'/>`
      : ''
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text>${dot}</svg>`
  let link = document.querySelector("link[rel='icon']")
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  link.href = `data:image/svg+xml,${encodeURIComponent(svg)}`
})

// the basic-auth user as the server sees it (recorded in the activity log)
const me = ref(null)
onMounted(async () => {
  try {
    me.value = (await api.whoami()).actor
  } catch {
    // only cosmetic
  }
})

connectEvents()

const RUN_TOASTS = {
  success: {severity: 'success', summary: 'Run finished'},
  failed: {severity: 'error', summary: 'Run failed'},
  timeout: {severity: 'warn', summary: 'No answer from the bot'},
  error: {severity: 'error', summary: 'Run error'},
}
const MODE_SUCCESS = {
  preview: 'Preview ready',
  test: 'Sent to the test channel',
}

trackRuns((run) => {
  const took = run.finished_ts ? ` · ${durationHuman(run.finished_ts - run.started_ts)}` : ''
  const ok = run.status === 'success'
  const base = RUN_TOASTS[run.status] || RUN_TOASTS.error
  toast.add({
    ...base,
    summary: ok && MODE_SUCCESS[run.mode] ? MODE_SUCCESS[run.mode] : base.summary,
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
          <Badge v-if="item.to === '/' && problemCount" :value="problemCount"
                 :severity="summary.data.value?.status === 'error' ? 'danger' : 'warn'"
                 class="nav-badge" v-tooltip.right="`${problemCount} check(s) need attention`"/>
        </RouterLink>
      </nav>
      <div v-if="me" class="whoami small muted" v-tooltip.right="'Your actions are recorded in Activity'">
        <i class="pi pi-user"/> <span>{{ me }}</span>
      </div>
      <div class="sidebar-footer">
        <span class="live" :class="live.cls" v-tooltip.top="live.tip">
          <i class="live-dot" :class="{pulse: liveStatus !== 'live'}"/>
          <span class="live-label">{{ live.label }}</span>
        </span>
        <Button
            :label="tzShortName(displayTz)" icon="pi pi-globe" text size="small" severity="secondary"
            class="tz-toggle"
            v-tooltip.top="displayMode === 'utc' ? 'Showing times in UTC. Click for your local time' : `Showing your local time (${displayTz}). Click for UTC`"
            @click="toggleDisplayTz"
        />
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

.tz-toggle {
  margin-left: auto;
  padding-inline: .4rem;
}

.whoami {
  display: flex;
  align-items: center;
  gap: .4rem;
  padding: 0 1.25rem;
  word-break: break-all;
}

@media (max-width: 800px) {
  .live-label, .whoami {
    display: none;
  }
}
</style>

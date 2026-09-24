<script setup>
import {computed} from 'vue'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {useNow} from '../composables/useNow.js'
import {durationHuman} from '../format.js'
import {actionInfo, auditSummary} from '../audit.js'
import {activeRuns, runLabel} from '../runs.js'
import PollStatus from '../components/PollStatus.vue'
import RelTime from '../components/RelTime.vue'

const now = useNow()

const STATUS = {
  ok: {icon: 'pi pi-check-circle', tag: 'success', label: 'OK'},
  warn: {icon: 'pi pi-exclamation-triangle', tag: 'warn', label: 'Attention'},
  error: {icon: 'pi pi-times-circle', tag: 'danger', label: 'Problem'},
  unknown: {icon: 'pi pi-question-circle', tag: 'secondary', label: 'No data'},
}
const ITEMS_SHOWN = 4

// almost anything the bot or the dashboard does can change a check; coalesce into one reload per 2 s
const {data, error, loading, updatedAt} = usePolling(api.summary, {
  interval: 60000,
  refreshOn: ['scanner', 'fetchers', 'log', 'flags', 'run'],
  eventDelay: 2000,
})

const {data: activity} = usePolling(() => api.audit({limit: 8}), {
  interval: 60000,
  refreshOn: 'log',
  eventFilter: (e) => e.source === 'DashboardAudit',
})

const problems = computed(() => (data.value?.checks || []).filter(c => c.status === 'warn' || c.status === 'error'))

const banner = computed(() => {
  const d = data.value
  if (!d) return null
  const n = problems.value.length
  if (d.status === 'ok') return {status: 'ok', title: 'All systems normal', text: 'Every check passed.'}
  if (!n) return {status: 'unknown', title: 'Some checks have no data', text: 'Is the bot running?'}
  return {
    status: d.status,
    title: `${n} ${n === 1 ? 'check needs' : 'checks need'} attention`,
    text: problems.value.map(c => c.title).join(', '),
  }
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Status</h1>
      <div class="actions">
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
      </div>
    </div>

    <div v-if="!data && !error" class="row muted"><ProgressSpinner style="width: 1.5rem; height: 1.5rem"/> Checking…</div>

    <div v-if="data" class="stack">
      <div class="banner" :class="`st-${banner.status}`">
        <i :class="STATUS[banner.status].icon" class="banner-icon"/>
        <div>
          <div class="banner-title">{{ banner.title }}</div>
          <div class="muted">{{ banner.text }}</div>
        </div>
      </div>

      <div class="checks">
        <RouterLink v-for="c in data.checks" :key="c.key" :to="c.link || '/'" class="check" :class="`st-${c.status}`">
          <div class="check-head">
            <span class="check-title"><i :class="STATUS[c.status].icon"/> {{ c.title }}</span>
            <Tag :severity="STATUS[c.status].tag" :value="STATUS[c.status].label"/>
          </div>
          <div class="check-value">{{ c.value }}</div>
          <div class="muted small">{{ c.detail }}</div>
          <ul v-if="c.items.length" class="check-items small">
            <li v-for="item in c.items.slice(0, ITEMS_SHOWN)" :key="item.label + item.text">
              <span class="mono">{{ item.label }}</span> <span class="muted">— {{ item.text }}</span>
            </li>
            <li v-if="c.items.length > ITEMS_SHOWN" class="muted">+{{ c.items.length - ITEMS_SHOWN }} more</li>
          </ul>
          <span class="check-open small">Open <i class="pi pi-arrow-right"/></span>
        </RouterLink>
      </div>

      <div class="lower">
        <div class="panel">
          <div class="panel-head">
            <h3>Recent activity</h3>
            <RouterLink :to="{name: 'activity'}" class="small">All activity <i class="pi pi-arrow-right"/></RouterLink>
          </div>
          <ul v-if="activity?.items.length" class="feed">
            <li v-for="e in activity.items" :key="`${e.ts}-${e.action}-${e.target}`">
              <i :class="actionInfo(e.action).icon" class="muted"/>
              <div>
                <div><strong>{{ e.actor }}</strong> {{ actionInfo(e.action).label.toLowerCase() }}
                  <span class="mono">{{ e.target }}</span></div>
                <div class="muted small"><RelTime :ts="e.ts" mode="ago"/><template v-if="auditSummary(e)"> · {{ auditSummary(e) }}</template></div>
              </div>
            </li>
          </ul>
          <p v-else class="muted small">No changes recorded yet.</p>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>Manual runs in progress</h3>
            <RouterLink :to="{name: 'jobs'}" class="small">Jobs <i class="pi pi-arrow-right"/></RouterLink>
          </div>
          <ul v-if="activeRuns.length" class="feed">
            <li v-for="r in activeRuns" :key="r.run_id">
              <i class="pi pi-spin pi-spinner muted"/>
              <div>
                <div class="mono">{{ runLabel(r) }}</div>
                <div class="muted small">{{ r.actor || 'someone' }} · running {{ durationHuman(now - r.started_ts) }}</div>
              </div>
            </li>
          </ul>
          <p v-else class="muted small">Nothing is running right now.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.st-ok {
  --st: var(--app-ok);
}

.st-warn {
  --st: var(--app-warn);
}

.st-error {
  --st: var(--app-err);
}

.st-unknown {
  --st: var(--app-muted);
}

.banner {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--st) 45%, var(--app-border));
  background: color-mix(in srgb, var(--st) 10%, var(--app-panel));
}

.banner-icon {
  font-size: 1.75rem;
  color: var(--st);
}

.banner-title {
  font-size: 1.15rem;
  font-weight: 700;
}

.checks {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}

.check {
  display: flex;
  flex-direction: column;
  gap: .35rem;
  padding: 1rem 1.1rem;
  border-radius: 12px;
  background: var(--app-panel);
  border: 1px solid var(--app-border);
  border-left: 4px solid var(--st);
  color: inherit;
  text-decoration: none;
  transition: border-color .15s, transform .15s;
}

.check:hover {
  border-color: var(--st);
  transform: translateY(-1px);
}

.check-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: .5rem;
}

.check-title {
  font-weight: 600;
}

.check-title .pi {
  color: var(--st);
}

.check-value {
  font-size: 1.4rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.check-items {
  margin: .25rem 0 0;
  padding-left: 1rem;
  word-break: break-word;
}

.check-open {
  margin-top: auto;
  padding-top: .5rem;
  color: var(--p-primary-color);
}

.lower {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: .75rem;
}

.panel-head h3 {
  margin: 0;
  font-size: 1rem;
}

.feed {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: .75rem;
}

.feed li {
  display: flex;
  gap: .75rem;
  align-items: flex-start;
  word-break: break-word;
}

.feed .pi {
  margin-top: .2rem;
}
</style>

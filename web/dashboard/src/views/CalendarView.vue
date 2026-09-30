<script setup>
import {computed, nextTick, reactive, ref, watch} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {useNow} from '../composables/useNow.js'
import {durationHuman, formatDate, formatRunTime} from '../format.js'
import {displayTz, sameOffset, tzShortName, zonedParts} from '../timezone.js'
import {jobType} from '../jobTypes.js'
import PollStatus from '../components/PollStatus.vue'
import RelTime from '../components/RelTime.vue'
import JobTypeBadge from '../components/JobTypeBadge.vue'
import PreviewDialog from '../components/PreviewDialog.vue'

// A week (or 3 / 14 days) of upcoming scheduled posts: when each alert goes out and which ones come too close.
const route = useRoute()
const router = useRouter()
const now = useNow()

const DAY_OPTIONS = [3, 7, 14]
const WINDOW_OPTIONS = [5, 15, 30, 60]
const HOUR_PX = 44
const PILL_PX = 22
const PILL_MIN = PILL_PX / HOUR_PX * 60  // how many minutes a pill covers on the grid

const view = reactive({
  days: DAY_OPTIONS.includes(+route.query.days) ? +route.query.days : 7,
  window: WINDOW_OPTIONS.includes(+route.query.window) ? +route.query.window : 15,
  disabled: route.query.disabled === '1',
  mode: route.query.mode === 'list' ? 'list' : (window.innerWidth < 800 ? 'list' : 'grid'),
})
const hiddenTypes = ref(new Set())

watch(view, () => router.replace({
  query: {
    days: view.days !== 7 ? view.days : undefined,
    window: view.window !== 15 ? view.window : undefined,
    disabled: view.disabled ? '1' : undefined,
    mode: view.mode !== 'grid' ? view.mode : undefined,
  },
}))

// job config changes and Apply are logged by the scheduler; reload on them
const {data, error, loading, updatedAt, refresh} = usePolling(() => api.upcoming(view.days), {
  interval: 5 * 60000,
  refreshOn: 'log',
  eventFilter: (e) => e.source === 'PublicScheduler',
  eventDelay: 1500,
})
watch(() => view.days, () => refresh())

const tz = displayTz
const jobs = computed(() => (data.value?.jobs || []).filter(j => view.disabled || j.enabled))

// ---- events, with "too close to another job" neighbours
const events = computed(() => {
  const list = []
  for (const job of jobs.value) {
    if (hiddenTypes.value.has(job.func) || job.frequent) continue
    for (const ts of job.runs) {
      const p = zonedParts(ts, tz.value)
      list.push({key: `${job.id}@${ts}`, ts, job, dayKey: p.dayKey, minute: p.hour * 60 + p.minute, near: []})
    }
  }
  list.sort((a, b) => a.ts - b.ts)
  const win = view.window * 60
  for (let i = 0; i < list.length; i++) {
    for (let j = i + 1; j < list.length && list[j].ts - list[i].ts < win; j++) {
      if (list[j].job.id !== list[i].job.id) {
        list[i].near.push(list[j])
        list[j].near.push(list[i])
      }
    }
  }
  return list
})

const conflictPairs = computed(() => events.value.reduce((n, e) => n + e.near.length, 0) / 2)
const frequentJobs = computed(() => jobs.value.filter(j => j.frequent && !hiddenTypes.value.has(j.func)))
const invalidJobs = computed(() => jobs.value.filter(j => j.invalid))

// ---- the day columns, in the display timezone, starting today
const days = computed(() => {
  const d = data.value
  if (!d) return []
  const keys = []
  for (let h = 0; keys.length < view.days && h < (view.days + 2) * 24; h++) {
    const ts = d.now + h * 3600
    const p = zonedParts(ts, tz.value)
    if (!keys.some(k => k.key === p.dayKey)) keys.push({key: p.dayKey, ts})
  }
  const todayKey = zonedParts(now.value, tz.value).dayKey
  return keys.map(({key, ts}) => {
    const dayEvents = events.value.filter(e => e.dayKey === key)
    return {
      key,
      isToday: key === todayKey,
      label: new Date(ts * 1000).toLocaleDateString(undefined, {weekday: 'short', timeZone: tz.value}),
      date: new Date(ts * 1000).toLocaleDateString(undefined, {day: 'numeric', month: 'short', timeZone: tz.value}),
      events: layoutLanes(dayEvents),
      conflicts: dayEvents.filter(e => e.near.length).length,
    }
  })
})

// side-by-side placement of pills that would overlap on the grid
function layoutLanes(dayEvents) {
  const placed = []
  let cluster = []
  let clusterEnd = -1
  let laneEnds = []
  const flush = () => {
    const lanes = laneEnds.length
    for (const e of cluster) e.lanes = lanes
    cluster = []
    laneEnds = []
  }
  for (const e of [...dayEvents].sort((a, b) => a.minute - b.minute)) {
    if (e.minute >= clusterEnd) flush()
    let lane = laneEnds.findIndex(end => end <= e.minute)
    if (lane === -1) lane = laneEnds.push(0) - 1
    laneEnds[lane] = e.minute + PILL_MIN
    e.lane = lane
    cluster.push(e)
    clusterEnd = Math.max(clusterEnd, e.minute + PILL_MIN)
    placed.push(e)
  }
  flush()
  return placed
}

const busiestDay = computed(() => days.value.reduce((best, d) => (!best || d.events.length > best.events.length) ? d : best, null))
const nowMinute = computed(() => {
  const p = zonedParts(now.value, tz.value)
  return p.hour * 60 + p.minute
})

// ---- the legend doubles as a filter
const legend = computed(() => {
  const counts = new Map()
  for (const job of jobs.value) {
    const c = counts.get(job.func) || {func: job.func, jobs: 0, runs: 0, frequent: false}
    c.jobs += 1
    c.runs += job.runs.length
    c.frequent = c.frequent || job.frequent
    counts.set(job.func, c)
  }
  return [...counts.values()].sort((a, b) => a.func.localeCompare(b.func))
})

function toggleType(func) {
  const next = new Set(hiddenTypes.value)
  next.has(func) ? next.delete(func) : next.add(func)
  hiddenTypes.value = next
}

// ---- event details
const popover = ref(null)
const selected = ref(null)
const showSchedulerTz = computed(() => data.value && !sameOffset(data.value.scheduler_tz, tz.value))

function openEvent(event, domEvent) {
  selected.value = event
  popover.value.show(domEvent)
}

function nearLabel(e, other) {
  const diff = other.ts - e.ts
  if (Math.abs(diff) < 1) return 'at the same time'
  return `${durationHuman(Math.abs(diff))} ${diff > 0 ? 'later' : 'earlier'}`
}

const previewVisible = ref(false)
const previewJob = ref(null)

function preview(job) {
  previewJob.value = {id: job.id, config: {func: job.func}}
  previewVisible.value = true
  popover.value.hide()
}

const pillStyle = (e) => ({
  top: `${e.minute / 60 * HOUR_PX}px`,
  left: `calc(${e.lane / e.lanes * 100}% + 2px)`,
  width: `calc(${100 / e.lanes}% - 4px)`,
  '--jt': jobType(e.job.func).color,
})

const timeLabel = (ts) => new Date(ts * 1000).toLocaleTimeString(undefined, {
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: tz.value,
})

// open the grid around the current hour
const gridScroll = ref(null)
let scrolled = false
watch(() => data.value && view.mode, async (ready) => {
  if (!ready || scrolled || view.mode !== 'grid') return
  await nextTick()
  if (gridScroll.value) {
    gridScroll.value.scrollTop = Math.max(0, (nowMinute.value / 60 - 1.5) * HOUR_PX)
    scrolled = true
  }
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Calendar</h1>
      <div class="actions">
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
        <Button label="Jobs" icon="pi pi-list-check" severity="secondary" outlined
                @click="router.push({name: 'jobs'})"/>
      </div>
    </div>

    <div class="stack">
      <div class="panel toolbar">
        <SelectButton v-model="view.days" :options="DAY_OPTIONS" :allow-empty="false" size="small">
          <template #option="{option}">{{ option }} days</template>
        </SelectButton>
        <span class="row small">
          <label for="cal-window" class="muted">Too close:</label>
          <Select input-id="cal-window" v-model="view.window" :options="WINDOW_OPTIONS" size="small">
            <template #value="{value}">&lt; {{ value }} min</template>
            <template #option="{option}">&lt; {{ option }} min</template>
          </Select>
        </span>
        <span class="row small">
          <ToggleSwitch input-id="cal-disabled" v-model="view.disabled"/>
          <label for="cal-disabled">Disabled jobs</label>
        </span>
        <SelectButton v-model="view.mode" :options="[{v: 'grid', i: 'pi pi-th-large', l: 'Week'}, {v: 'list', i: 'pi pi-list', l: 'List'}]"
                      option-value="v" :allow-empty="false" size="small" class="mode">
          <template #option="{option}"><i :class="option.i"/> {{ option.l }}</template>
        </SelectButton>
      </div>

      <div v-if="data" class="summary small">
        <span><strong>{{ events.length }}</strong> posts in {{ view.days }} days</span>
        <span v-if="busiestDay?.events.length" class="muted">
          · busiest: {{ busiestDay.label }} {{ busiestDay.date }} ({{ busiestDay.events.length }})
        </span>
        <span v-if="conflictPairs" class="warn">
          · <i class="pi pi-exclamation-triangle"/> {{ conflictPairs }} pair(s) less than {{ view.window }} min apart
        </span>
        <span v-else class="ok">· no posts closer than {{ view.window }} min</span>
        <span class="muted">· times in {{ tzShortName(tz) }}; the bot schedules in {{ data.scheduler_tz }}</span>
      </div>

      <div v-if="legend.length" class="legend">
        <button v-for="l in legend" :key="l.func" type="button" class="legend-item"
                :class="{off: hiddenTypes.has(l.func)}" @click="toggleType(l.func)"
                v-tooltip.top="hiddenTypes.has(l.func) ? 'Hidden — click to show' : 'Click to hide'">
          <JobTypeBadge :func="l.func" size="small"/>
          <span class="muted small">{{ l.frequent ? 'frequent' : l.runs }}</span>
        </button>
      </div>

      <Message v-if="invalidJobs.length" severity="error">
        Invalid schedules (the bot cannot run them):
        <span v-for="j in invalidJobs" :key="j.id" class="mono"> {{ j.id }}</span>
      </Message>

      <div v-if="frequentJobs.length" class="panel frequent">
        <div class="small muted">Too frequent to place on the calendar (more than {{ data.frequent_per_day }} a day):</div>
        <div v-for="j in frequentJobs" :key="j.id" class="row small">
          <JobTypeBadge :func="j.func" size="small"/>
          <span class="mono muted">{{ j.id }}</span>
          <span>— {{ j.schedule }}</span>
          <Tag v-if="!j.enabled" value="disabled" severity="secondary"/>
        </div>
      </div>

      <div v-if="!data && !error" class="row muted"><ProgressSpinner style="width: 1.5rem; height: 1.5rem"/> Loading…</div>
      <p v-else-if="data && !events.length && !frequentJobs.length" class="muted">
        Nothing scheduled in the next {{ view.days }} days{{ view.disabled ? '' : ' (enabled jobs)' }}.
      </p>

      <!-- ===== week grid ===== -->
      <div v-else-if="data && view.mode === 'grid'" class="grid-wrap panel">
        <div class="grid-head" :style="{'--cols': days.length}">
          <div class="axis-head"/>
          <div v-for="d in days" :key="d.key" class="day-head" :class="{today: d.isToday}">
            <div class="day-name">{{ d.label }} <span class="muted">{{ d.date }}</span></div>
            <div class="small muted">
              {{ d.events.length }} post(s)
              <span v-if="d.conflicts" class="warn"> · <i class="pi pi-exclamation-triangle"/> {{ d.conflicts }}</span>
            </div>
          </div>
        </div>
        <div ref="gridScroll" class="grid-scroll">
          <div class="grid-body" :style="{'--cols': days.length, height: `${24 * HOUR_PX}px`}">
            <div class="axis">
              <div v-for="h in 24" :key="h" class="hour-label" :style="{top: `${(h - 1) * HOUR_PX}px`}">
                {{ String(h - 1).padStart(2, '0') }}:00
              </div>
            </div>
            <div v-for="d in days" :key="d.key" class="day-col" :class="{today: d.isToday}">
              <div v-for="h in 24" :key="h" class="hour-line" :style="{top: `${(h - 1) * HOUR_PX}px`}"/>
              <div v-if="d.isToday" class="now-line" :style="{top: `${nowMinute / 60 * HOUR_PX}px`}"/>
              <button v-for="e in d.events" :key="e.key" type="button" class="pill"
                      :class="{conflict: e.near.length, approx: e.job.approximate, disabled: !e.job.enabled}"
                      :style="pillStyle(e)" @click="openEvent(e, $event)"
                      v-tooltip.top="`${timeLabel(e.ts)} ${e.job.func}${e.near.length ? ' — too close to ' + e.near.length + ' other' : ''}`">
                <span>{{ jobType(e.job.func).emoji }}</span>
                <span class="pill-time">{{ timeLabel(e.ts) }}</span>
                <span class="pill-name">{{ e.job.func }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== agenda list ===== -->
      <div v-else-if="data" class="stack">
        <div v-for="d in days" :key="d.key" class="panel day-list">
          <div class="row day-list-head">
            <strong>{{ d.label }} {{ d.date }}</strong>
            <Tag v-if="d.isToday" value="today" severity="info"/>
            <span class="muted small">{{ d.events.length }} post(s)</span>
          </div>
          <p v-if="!d.events.length" class="muted small" style="margin: .25rem 0 0">No posts.</p>
          <button v-for="e in [...d.events].sort((a, b) => a.ts - b.ts)" :key="e.key" type="button" class="agenda-row"
                  :class="{conflict: e.near.length, disabled: !e.job.enabled}" @click="openEvent(e, $event)">
            <span class="mono agenda-time">{{ timeLabel(e.ts) }}</span>
            <JobTypeBadge :func="e.job.func" size="small"/>
            <span class="mono muted small agenda-id">{{ e.job.id }}</span>
            <span v-if="e.near.length" class="warn small nowrap">
              <i class="pi pi-exclamation-triangle"/> {{ nearLabel(e, e.near[0]) }}: {{ jobType(e.near[0].job.func).emoji }}
            </span>
            <span v-if="e.job.approximate" class="muted small">≈</span>
          </button>
        </div>
      </div>
    </div>

    <Popover ref="popover">
      <div v-if="selected" class="event-card stack">
        <JobTypeBadge :func="selected.job.func" title/>
        <span class="mono muted small">{{ selected.job.id }}</span>
        <div>
          <strong>{{ formatDate(selected.ts, {tzName: true}) }}</strong>
          · <RelTime :ts="selected.ts"/>
          <div v-if="showSchedulerTz" class="muted small">
            = {{ formatRunTime(selected.ts, {tz: data.scheduler_tz}) }} {{ data.scheduler_tz }}
          </div>
        </div>
        <div class="small">{{ selected.job.schedule }}</div>
        <div class="row small">
          <Tag v-if="!selected.job.enabled" value="disabled" severity="secondary"/>
          <Tag v-if="selected.job.is_dirty" value="not applied" severity="warn"/>
          <span v-if="selected.job.approximate" class="muted">≈ approximate: an interval job counts from Apply</span>
        </div>
        <div v-if="selected.near.length" class="near">
          <div class="warn small"><i class="pi pi-exclamation-triangle"/> Less than {{ view.window }} min from:</div>
          <div v-for="n in selected.near" :key="n.key" class="row small">
            <JobTypeBadge :func="n.job.func" size="small"/>
            <span class="muted">{{ timeLabel(n.ts) }} · {{ nearLabel(selected, n) }}</span>
          </div>
        </div>
        <div class="row">
          <Button label="Preview" icon="pi pi-eye" size="small" severity="secondary" outlined
                  @click="preview(selected.job)"/>
          <Button label="Edit job" icon="pi pi-pencil" size="small" text
                  @click="router.push({name: 'job-edit', params: {id: selected.job.id}})"/>
        </div>
      </div>
    </Popover>

    <PreviewDialog v-model:visible="previewVisible" :job="previewJob" :test-channels="data?.test_channels || []"/>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: .75rem 1.25rem;
  align-items: center;
  padding: .75rem;
}

.toolbar .mode {
  margin-left: auto;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: .35rem;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  color: inherit;
  font: inherit;
}

.legend-item.off {
  opacity: .35;
  text-decoration: line-through;
}

.frequent {
  display: flex;
  flex-direction: column;
  gap: .35rem;
  padding: .75rem 1rem;
}

/* ---- grid ---- */
.grid-wrap {
  padding: 0;
  overflow-x: auto;
}

.grid-head, .grid-body {
  display: grid;
  grid-template-columns: 3.25rem repeat(var(--cols), minmax(110px, 1fr));
  min-width: calc(3.25rem + var(--cols) * 110px);
}

.grid-head {
  border-bottom: 1px solid var(--app-border);
}

.day-head {
  padding: .5rem .6rem;
  border-left: 1px solid var(--app-border);
}

.day-head.today {
  background: color-mix(in srgb, var(--p-primary-color) 10%, transparent);
}

.day-name {
  font-weight: 600;
}

.grid-scroll {
  max-height: 68vh;
  overflow-y: auto;
  min-width: calc(3.25rem + var(--cols, 7) * 110px);
}

.grid-body {
  position: relative;
}

.axis {
  position: relative;
}

.hour-label {
  position: absolute;
  right: .4rem;
  transform: translateY(-.5em);
  font-size: .7rem;
  color: var(--app-muted);
  font-variant-numeric: tabular-nums;
}

.hour-label:first-child {
  transform: none;
}

.day-col {
  position: relative;
  border-left: 1px solid var(--app-border);
}

.day-col.today {
  background: color-mix(in srgb, var(--p-primary-color) 5%, transparent);
}

.hour-line {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 1px dashed color-mix(in srgb, var(--app-border) 70%, transparent);
}

.now-line {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 2px solid var(--app-err);
  z-index: 3;
}

.now-line::before {
  content: '';
  position: absolute;
  left: -4px;
  top: -5px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-err);
}

.pill {
  position: absolute;
  height: 22px;
  display: flex;
  align-items: center;
  gap: .25rem;
  padding: 0 .3rem;
  overflow: hidden;
  white-space: nowrap;
  font: inherit;
  font-size: .72rem;
  color: var(--app-text);
  background: color-mix(in srgb, var(--jt) 24%, var(--app-panel));
  border: 1px solid color-mix(in srgb, var(--jt) 55%, transparent);
  border-left: 3px solid var(--jt);
  border-radius: 5px;
  cursor: pointer;
  z-index: 2;
}

.pill:hover {
  z-index: 4;
  filter: brightness(1.1);
}

.pill-time {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.pill-name {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--app-muted);
}

.pill.conflict, .agenda-row.conflict {
  outline: 2px solid var(--app-err);
  outline-offset: -1px;
}

.pill.approx {
  border-style: dashed;
}

.pill.disabled, .agenda-row.disabled {
  opacity: .45;
}

/* ---- list ---- */
.day-list {
  display: flex;
  flex-direction: column;
  gap: .3rem;
  padding: .75rem 1rem;
}

.day-list-head {
  margin-bottom: .25rem;
}

.agenda-row {
  display: flex;
  align-items: center;
  gap: .6rem;
  flex-wrap: wrap;
  padding: .3rem .4rem;
  border: 0;
  border-radius: 6px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.agenda-row:hover {
  background: var(--p-content-hover-background);
}

.agenda-time {
  font-weight: 600;
  min-width: 3rem;
}

.agenda-id {
  flex: 1 1 10rem;
}

/* ---- popover ---- */
.event-card {
  gap: .5rem;
  max-width: 22rem;
}

.near {
  display: flex;
  flex-direction: column;
  gap: .25rem;
}
</style>

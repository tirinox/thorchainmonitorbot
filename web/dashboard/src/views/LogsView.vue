<script setup>
import {computed, reactive, watch} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {formatDate, formatNumber, timeAgo} from '../format.js'
import PollStatus from '../components/PollStatus.vue'
import {isDark} from '../theme.js'

const route = useRoute()
const router = useRouter()

const FILTER_KEYS = ['level', 'action', 'phase', 'job', 'q']
const LEVELS = ['error', 'warning', 'info']
const LEVEL_SEVERITY = {error: 'danger', warning: 'warn', info: 'success'}
const LIMITS = [200, 500, 1000, 5000]

// filters are mirrored in the URL (Jobs → "Logs" links here with ?q=<job id>)
const filters = reactive(Object.fromEntries(FILTER_KEYS.map(k => [k, route.query[k] || null])))
const search = reactive({text: filters.q || '', limit: 500})

let debounce = null
watch(() => search.text, (text) => {
  clearTimeout(debounce)
  debounce = setTimeout(() => (filters.q = text.trim() || null), 300)
})

watch(filters, () => {
  const query = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
  router.replace({query})
  refresh()
})
watch(() => search.limit, () => refresh())

const {data, error, loading, updatedAt, refresh} = usePolling(
    () => api.logs({...filters, limit: search.limit}),
    {interval: 5000},
)

const hasFilters = computed(() => FILTER_KEYS.some(k => filters[k]))

function resetFilters() {
  FILTER_KEYS.forEach(k => (filters[k] = null))
  search.text = ''
}

const rowClass = (row) => row.level === 'error' ? 'row-error' : row.level === 'warning' ? 'row-warning' : ''

function detailText(value, key) {
  if (key === 'elapsed' && typeof value === 'number') return `${value.toFixed(3)}s`
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

// ---- chart: daily count per level (stacked) ----
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

const chartData = computed(() => {
  const hist = data.value?.histogram || []
  const dates = [...new Set(hist.map(h => h.date))].sort()
  const colors = {error: cssVar('--p-red-500'), warning: cssVar('--p-amber-400'), info: cssVar('--p-emerald-500')}
  return {
    labels: dates,
    datasets: LEVELS.map(level => ({
      label: level,
      backgroundColor: colors[level],
      borderRadius: 2,
      data: dates.map(d => hist.find(h => h.date === d && h.level === level)?.count || 0),
    })),
  }
})

const chartOptions = computed(() => {
  void isDark.value  // re-read theme colors when the theme changes
  const text = cssVar('--p-text-muted-color')
  const grid = cssVar('--p-content-border-color')
  return {
    maintainAspectRatio: false,
    animation: false,
    plugins: {legend: {labels: {color: text}}},
    scales: {
      x: {stacked: true, ticks: {color: text}, grid: {display: false}},
      y: {stacked: true, ticks: {color: text, precision: 0}, grid: {color: grid}},
    },
  }
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Scheduler logs</h1>
      <div class="actions">
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
      </div>
    </div>

    <div class="stack">
      <div class="panel filters">
        <IconField class="search">
          <InputIcon class="pi pi-search"/>
          <InputText v-model="search.text" placeholder="Search anything…" fluid/>
        </IconField>
        <Select v-model="filters.level" :options="LEVELS" placeholder="Level" show-clear/>
        <Select v-model="filters.action" :options="data?.facets.actions || []" placeholder="Action" show-clear filter/>
        <Select v-model="filters.phase" :options="data?.facets.phases || []" placeholder="Phase" show-clear filter/>
        <Select v-model="filters.job" :options="data?.facets.jobs || []" placeholder="Job" show-clear filter/>
        <Button v-if="hasFilters" icon="pi pi-filter-slash" label="Reset" text severity="secondary" @click="resetFilters"/>
      </div>

      <div v-if="data" class="row small muted">
        {{ formatNumber(data.matched) }} matching of {{ formatNumber(data.total) }} stored entries
        <template v-if="data.matched > data.items.length">· showing the newest {{ formatNumber(data.items.length) }}</template>
      </div>

      <div v-if="data?.histogram.length" class="panel" style="height: 220px">
        <Chart type="bar" :data="chartData" :options="chartOptions" style="height: 100%"/>
      </div>

      <DataTable :value="data?.items || []" :loading="!data && !error" size="small" :row-class="rowClass"
                 paginator :rows="50" :rows-per-page-options="[50, 100, 250]" scrollable>
        <template #empty>No log entries.</template>
        <template #paginatorend>
          <span class="row small muted">
            load
            <Select v-model="search.limit" :options="LIMITS" size="small"/>
          </span>
        </template>
        <Column header="Level" style="width: 1%">
          <template #body="{data: r}">
            <Tag :severity="LEVEL_SEVERITY[r.level]" :value="r.level"/>
          </template>
        </Column>
        <Column header="Time" style="width: 1%">
          <template #body="{data: r}">
            <div class="nowrap">{{ formatDate(r.ts) }}</div>
            <div class="muted small nowrap">{{ timeAgo(r.ts) }}</div>
          </template>
        </Column>
        <Column field="action" header="Action"/>
        <Column field="job" header="Job">
          <template #body="{data: r}"><span class="mono">{{ r.job }}</span></template>
        </Column>
        <Column field="phase" header="Phase"/>
        <Column header="Details" style="min-width: 22rem">
          <template #body="{data: r}">
            <span v-for="(v, k) in r.details" :key="k" class="detail mono">
              <span class="muted">{{ k }}=</span>{{ detailText(v, k) }}
            </span>
          </template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  gap: .5rem;
  flex-wrap: wrap;
  align-items: center;
  padding: .75rem;
}

.filters .search {
  flex: 1 1 240px;
}

.detail {
  display: inline-block;
  margin-right: .75rem;
  word-break: break-word;
}
</style>

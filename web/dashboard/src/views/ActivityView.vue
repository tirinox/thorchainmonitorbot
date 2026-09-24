<script setup>
import {computed, reactive, watch} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {useNow} from '../composables/useNow.js'
import {formatDate, formatNumber, timeAgo} from '../format.js'
import {actionInfo} from '../audit.js'
import PollStatus from '../components/PollStatus.vue'
import AuditDetails from '../components/AuditDetails.vue'

const route = useRoute()
const router = useRouter()
const now = useNow()

const FILTER_KEYS = ['actor', 'action', 'q']
const filters = reactive(Object.fromEntries(FILTER_KEYS.map(k => [k, route.query[k] || null])))
const search = reactive({text: filters.q || ''})

let debounce = null
watch(() => search.text, (text) => {
  clearTimeout(debounce)
  debounce = setTimeout(() => (filters.q = text.trim() || null), 300)
})

watch(filters, () => {
  router.replace({query: Object.fromEntries(Object.entries(filters).filter(([, v]) => v))})
  refresh()
})

// every audit entry is announced as a `log` event with source=DashboardAudit
const {data, error, loading, updatedAt, refresh} = usePolling(
    () => api.audit({...filters, limit: 1000}),
    {interval: 60000, refreshOn: 'log', eventFilter: (e) => e.source === 'DashboardAudit'},
)

const actionOptions = computed(() => (data.value?.facets.actions || []).map(a => ({value: a, label: actionInfo(a).label})))
const hasFilters = computed(() => FILTER_KEYS.some(k => filters[k]))

function resetFilters() {
  FILTER_KEYS.forEach(k => (filters[k] = null))
  search.text = ''
}

function targetLink(entry) {
  if (!entry.target) return null
  if (entry.action.startsWith('flag.')) return {name: 'flags', query: {q: entry.target}}
  if (entry.action.startsWith('job.') && entry.action !== 'job.delete') return {name: 'jobs'}
  return null
}

const rowClass = (e) => e.level === 'warning' ? 'row-warning' : ''
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Activity</h1>
      <div class="actions">
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
      </div>
    </div>

    <div class="stack">
      <p class="muted" style="margin: 0">Who changed what in this dashboard: jobs, runs, config applies and flags.</p>

      <div class="panel filters">
        <IconField class="search">
          <InputIcon class="pi pi-search"/>
          <InputText v-model="search.text" placeholder="Search…" fluid/>
        </IconField>
        <Select v-model="filters.actor" :options="data?.facets.actors || []" placeholder="Who" show-clear/>
        <Select v-model="filters.action" :options="actionOptions" option-label="label" option-value="value"
                placeholder="Action" show-clear/>
        <Button v-if="hasFilters" icon="pi pi-filter-slash" label="Reset" text severity="secondary" @click="resetFilters"/>
      </div>

      <div v-if="data" class="small muted">
        {{ formatNumber(data.matched) }} of {{ formatNumber(data.total) }} entries
      </div>

      <DataTable :value="data?.items || []" :loading="!data && !error" size="small" :row-class="rowClass"
                 paginator :rows="50" :rows-per-page-options="[50, 100, 250]" scrollable>
        <template #empty>Nothing recorded yet.</template>
        <Column header="When" style="width: 1%">
          <template #body="{data: e}">
            <div class="nowrap">{{ formatDate(e.ts) }}</div>
            <div class="muted small nowrap">{{ timeAgo(e.ts, now) }}</div>
          </template>
        </Column>
        <Column header="Who" style="width: 1%">
          <template #body="{data: e}">
            <span class="nowrap"><i class="pi pi-user muted small"/> {{ e.actor }}</span>
          </template>
        </Column>
        <Column header="Action" style="width: 1%">
          <template #body="{data: e}">
            <Tag :severity="actionInfo(e.action).severity" class="nowrap">
              <i :class="actionInfo(e.action).icon"/> {{ actionInfo(e.action).label }}
            </Tag>
          </template>
        </Column>
        <Column header="Target" style="min-width: 12rem">
          <template #body="{data: e}">
            <RouterLink v-if="targetLink(e)" :to="targetLink(e)" class="mono break">{{ e.target }}</RouterLink>
            <span v-else class="mono break">{{ e.target || '—' }}</span>
          </template>
        </Column>
        <Column header="Details" style="min-width: 20rem">
          <template #body="{data: e}">
            <AuditDetails :entry="e"/>
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
</style>

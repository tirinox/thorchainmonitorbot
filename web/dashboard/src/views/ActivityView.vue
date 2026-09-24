<script setup>
import {computed, reactive, ref, watch} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {useToast} from 'primevue/usetoast'
import {useConfirm} from 'primevue/useconfirm'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {formatDate, formatNumber} from '../format.js'
import {actionInfo} from '../audit.js'
import PollStatus from '../components/PollStatus.vue'
import AuditDetails from '../components/AuditDetails.vue'
import RelTime from '../components/RelTime.vue'

const route = useRoute()
const router = useRouter()

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

// ---- restore a deleted job from the config saved with its job.delete entry
const toast = useToast()
const confirm = useConfirm()
const restoring = ref(null)

const canRestore = (e) => e.action === 'job.delete' && !!e.details?.config

// ---- put a flag back to the value it had before this entry (a normal change, so it is audited too)
const hasOldFlagValue = (e) => typeof e.details?.old === 'boolean'
const canRevertFlag = (e) => (e.action === 'flag.set' || e.action === 'flag.delete') && hasOldFlagValue(e)
const revertLabel = (e) => e.action === 'flag.delete'
    ? `Recreate as ${e.details.old ? 'on' : 'off'}`
    : `Revert to ${e.details.old ? 'on' : 'off'}`

function revertFlag(entry) {
  const {old} = entry.details
  confirm.require({
    header: entry.action === 'flag.delete' ? 'Recreate flag' : 'Revert flag',
    message: `Set "${entry.target}" back to ${old ? 'ON' : 'OFF'}?`,
    icon: 'pi pi-undo',
    acceptProps: {label: old ? 'Turn on' : 'Turn off', severity: old ? undefined : 'warn'},
    rejectProps: {label: 'Cancel', severity: 'secondary', text: true},
    accept: async () => {
      restoring.value = entry
      try {
        await api.setFlag(entry.target, old)
        toast.add({severity: 'success', summary: `${entry.target} = ${old}`, life: 4000})
      } catch (e) {
        toast.add({severity: 'error', summary: 'Revert failed', detail: e.message, life: 10000})
      } finally {
        restoring.value = null
      }
    },
  })
}

function restore(entry) {
  const config = entry.details.config
  confirm.require({
    header: 'Restore job',
    message: `Restore "${config.id}" (${config.func}) as it was when deleted? ` +
        `It comes back ${config.enabled ? 'enabled' : 'disabled'} and needs Apply on the Jobs page.`,
    icon: 'pi pi-replay',
    acceptProps: {label: 'Restore'},
    rejectProps: {label: 'Cancel', severity: 'secondary', text: true},
    accept: async () => {
      restoring.value = entry
      try {
        await api.restoreJob(config)
        toast.add({severity: 'success', summary: 'Job restored', detail: `${config.id} — press Apply on the Jobs page.`, life: 6000})
      } catch (e) {
        toast.add({severity: 'error', summary: 'Restore failed', detail: e.message, life: 10000})
      } finally {
        restoring.value = null
      }
    },
  })
}
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
            <div class="muted small nowrap"><RelTime :ts="e.ts" mode="ago"/></div>
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
            <Button v-if="canRestore(e)" label="Restore job" icon="pi pi-replay" size="small" text
                    class="restore" :loading="restoring === e" @click="restore(e)"/>
            <Button v-if="canRevertFlag(e)" :label="revertLabel(e)" icon="pi pi-undo" size="small" text
                    class="restore" :loading="restoring === e" @click="revertFlag(e)"/>
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

.restore {
  margin: .25rem 0 0 -.5rem;
}
</style>

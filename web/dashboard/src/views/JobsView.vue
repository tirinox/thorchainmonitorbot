<script setup>
import {computed, reactive, ref, watch} from 'vue'
import {useRouter} from 'vue-router'
import {useToast} from 'primevue/usetoast'
import {useConfirm} from 'primevue/useconfirm'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {durationHuman, formatPercent, shortJson} from '../format.js'
import {channelIcon, channelLabel, channelTitle} from '../channels.js'
import PollStatus from '../components/PollStatus.vue'
import RunNowDialog from '../components/RunNowDialog.vue'
import {activeRunForJob, startJobRun} from '../runs.js'
import {displayTz, tzShortName} from '../timezone.js'
import RelTime from '../components/RelTime.vue'
import ScheduleText from '../components/ScheduleText.vue'

const router = useRouter()
const toast = useToast()
const confirm = useConfirm()

// scheduler actions and job runs are all logged, and each log line arrives as a `log` event
const {data, error, loading, updatedAt, refresh} = usePolling(() => api.jobs(displayTz.value), {
  interval: 30000,
  refreshOn: ['log', 'run'],
  eventFilter: (e) => e.type === 'run' || e.source === 'PublicScheduler',
})
// fixed cron times are also shown in the display timezone, which the server converts to
watch(displayTz, () => refresh())

const rows = computed(() => (data.value?.jobs || []).map(j => {
  const {channels: _, ...args} = j.config.args || {}
  return {...j, id: j.config.id, extraArgs: args}
}))

const distribution = computed(() => {
  const d = data.value
  if (!d) return []
  return d.available_types.map(func => ({func, count: d.distribution[func] || 0}))
})

const expandedRows = ref({})
const busy = reactive({})  // job id -> action name
const applying = ref(false)
const runNowVisible = ref(false)

const VARIANT_ICONS = {interval: 'pi pi-clock', cron: 'pi pi-calendar', date: 'pi pi-calendar-clock'}

function notifyError(e, summary = 'Error') {
  toast.add({severity: 'error', summary, detail: e.message, life: 8000})
}

async function withBusy(id, action, fn) {
  busy[id] = action
  try {
    await fn()
  } finally {
    delete busy[id]
    refresh()
  }
}

function setEnabled(job, enabled) {
  withBusy(job.id, 'toggle', async () => {
    try {
      await api.setJobEnabled(job.id, enabled)
      toast.add({severity: 'info', summary: `${enabled ? 'Enabled' : 'Disabled'} ${job.id}`, detail: 'Apply the configuration to take effect.', life: 3000})
    } catch (e) {
      notifyError(e, 'Toggle failed')
    }
  })
}

function runJob(job) {
  confirm.require({
    header: 'Run job now',
    message: `Run "${job.id}" (${job.config.func}) right now?`,
    icon: 'pi pi-play',
    acceptProps: {label: 'Run it'},
    rejectProps: {label: 'Cancel', severity: 'secondary', text: true},
    accept: async () => {
      try {
        await startJobRun(job.id)
        toast.add({severity: 'info', summary: 'Started', detail: `${job.id} — you will be notified when it ends.`, life: 3000})
      } catch (e) {
        notifyError(e, 'Could not start the job')
      }
    },
  })
}

function deleteJob(job) {
  confirm.require({
    header: 'Delete job',
    message: `Delete "${job.id}"? This cannot be undone.`,
    icon: 'pi pi-exclamation-triangle',
    acceptProps: {label: 'Delete', severity: 'danger'},
    rejectProps: {label: 'Cancel', severity: 'secondary', text: true},
    accept: () => withBusy(job.id, 'delete', async () => {
      try {
        await api.deleteJob(job.id)
        toast.add({severity: 'info', summary: 'Deleted', detail: job.id, life: 3000})
      } catch (e) {
        notifyError(e, 'Delete failed')
      }
    }),
  })
}

async function applyConfig() {
  applying.value = true
  try {
    const r = await api.reloadScheduler()
    toast.add(r.ok
        ? {severity: 'success', summary: 'Configuration applied', life: 3000}
        : {severity: 'error', summary: 'Apply failed', detail: String(r.result), life: 8000})
  } catch (e) {
    notifyError(e, 'Apply failed')
  } finally {
    applying.value = false
    refresh()
  }
}

const editJob = (job) => router.push({name: 'job-edit', params: {id: job.id}})
const viewLogs = (job) => router.push({name: 'logs', query: {q: job.id}})

const successRate = (s) => s.run_count ? formatPercent(s.run_count - s.error_count, s.run_count) : '—'
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Scheduled jobs</h1>
      <div class="actions">
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
        <Button label="Run function…" icon="pi pi-play" severity="secondary" outlined
                :disabled="!data" @click="runNowVisible = true"/>
        <Button label="New job" icon="pi pi-plus" @click="router.push({name: 'job-new'})"/>
      </div>
    </div>

    <div class="stack">
      <p v-if="data" class="muted small" style="margin: 0">
        <i class="pi pi-globe"/> The bot evaluates cron and one-off schedules in <strong>{{ data.scheduler_tz }}</strong>.
        Times below are shown in {{ tzShortName(displayTz) }}; hover a relative time for the exact moment.
      </p>
      <Message v-if="data?.is_dirty" severity="warn">
        <div class="row" style="justify-content: space-between; width: 100%">
          <span>The scheduler configuration has unapplied changes.</span>
          <Button label="Apply" icon="pi pi-check" size="small" :loading="applying" @click="applyConfig"/>
        </div>
      </Message>

      <div v-if="distribution.length" class="row">
        <span class="muted small">Job types:</span>
        <Tag v-for="d in distribution" :key="d.func" :severity="d.count ? 'success' : 'secondary'"
             :value="`${d.func} · ${d.count}`" :class="{'dim': !d.count}"/>
      </div>

      <Panel toggleable collapsed>
        <template #header>
          <span class="row"><i class="pi pi-megaphone"/> <strong>Broadcast channels ({{ data?.channels.length ?? '…' }})</strong></span>
        </template>
        <DataTable v-if="data?.channels.length" :value="data.channels" size="small">
          <Column header="Type">
            <template #body="{data: c}"><i :class="channelIcon(c.type)"/> {{ channelTitle(c.type) }}</template>
          </Column>
          <Column field="channel" header="Channel"/>
          <Column field="lang" header="Lang"/>
          <Column header="Selector">
            <template #body="{data: c}"><span class="mono">{{ c.selector }}</span></template>
          </Column>
        </DataTable>
        <p v-else class="muted">No channels are configured in <code>broadcasting.channels</code>.</p>
      </Panel>

      <DataTable :value="rows" data-key="id" v-model:expanded-rows="expandedRows" :loading="!data && !error"
                 scrollable class="jobs-table">
        <template #empty>No jobs configured yet.</template>
        <Column expander style="width: 3rem"/>

        <Column header="Job" style="min-width: 16rem">
          <template #body="{data: job}">
            <div class="stack" style="gap: .3rem">
              <strong>{{ job.config.func }}</strong>
              <span class="mono muted">{{ job.id }}</span>
              <div class="row small" style="gap: .35rem">
                <template v-if="job.channels.resolved.length || job.channels.unknown.length">
                  <Tag v-for="c in job.channels.resolved" :key="c.selector" severity="secondary" v-tooltip="channelLabel(c)">
                    <i :class="channelIcon(c.type)"/> {{ c.channel }}
                  </Tag>
                  <Tag v-for="u in job.channels.unknown" :key="u" severity="danger" v-tooltip="'Unknown channel selector'"
                       :value="u"/>
                </template>
                <span v-else class="muted">All channels</span>
              </div>
              <span v-if="Object.keys(job.extraArgs).length" class="mono muted small break">
                args: {{ shortJson(job.extraArgs) }}
              </span>
            </div>
          </template>
        </Column>

        <Column header="Schedule" style="min-width: 14rem">
          <template #body="{data: job}">
            <div class="schedule-cell">
              <i :class="VARIANT_ICONS[job.config.variant]" class="muted" v-tooltip.top="job.config.variant"/>
              <ScheduleText :schedule="job.schedule"/>
            </div>
          </template>
        </Column>

        <Column header="State">
          <template #body="{data: job}">
            <div class="stack" style="gap: .4rem">
              <div class="row">
                <ToggleSwitch :model-value="job.config.enabled" :disabled="!!busy[job.id]"
                              @update:model-value="v => setEnabled(job, v)"/>
                <span :class="job.config.enabled ? 'ok' : 'muted'">{{ job.config.enabled ? 'ON' : 'OFF' }}</span>
              </div>
              <Tag v-if="job.stats.is_running || activeRunForJob(job.id)" severity="info" value="RUNNING" class="pulse"/>
              <Tag v-else severity="secondary" value="idle"/>
            </div>
          </template>
        </Column>

        <Column header="Stats" style="min-width: 15rem">
          <template #body="{data: job}">
            <div class="stats small">
              <span class="muted">runs</span><span>{{ job.stats.run_count }}</span>
              <span class="muted">errors</span>
              <span :class="{err: job.stats.error_count}">{{ job.stats.error_count }} · {{ successRate(job.stats) }} ok</span>
              <span class="muted">last</span>
              <span><RelTime :ts="job.stats.last_ts" mode="ago" empty="never"/>
                <template v-if="job.stats.last_elapsed"> · took {{ durationHuman(job.stats.last_elapsed) }}</template>
              </span>
              <span class="muted">avg</span><span>{{ durationHuman(job.stats.avg_elapsed) }}</span>
              <template v-if="job.stats.next_run_ts && job.config.enabled">
                <span class="muted">next</span><span><RelTime :ts="job.stats.next_run_ts" mode="until"/></span>
              </template>
            </div>
            <div v-if="job.stats.last_status === 'error' && job.stats.last_error" class="err small break" style="margin-top: .35rem">
              <i class="pi pi-exclamation-circle"/> {{ job.stats.last_error }}
            </div>
          </template>
        </Column>

        <Column header="" style="width: 1%">
          <template #body="{data: job}">
            <div class="row nowrap" style="flex-wrap: nowrap; gap: .15rem">
              <Button icon="pi pi-play" text rounded v-tooltip.top="'Run now'" aria-label="Run now"
                      :loading="!!activeRunForJob(job.id)" :disabled="!!busy[job.id] || !!activeRunForJob(job.id)"
                      @click="runJob(job)"/>
              <Button icon="pi pi-pencil" text rounded v-tooltip.top="'Edit'" aria-label="Edit"
                      @click="editJob(job)"/>
              <Button icon="pi pi-history" text rounded severity="secondary" v-tooltip.top="'Logs'" aria-label="Logs"
                      @click="viewLogs(job)"/>
              <Button icon="pi pi-trash" text rounded severity="danger" v-tooltip.top="'Delete'" aria-label="Delete"
                      :loading="busy[job.id] === 'delete'" :disabled="!!busy[job.id]" @click="deleteJob(job)"/>
            </div>
          </template>
        </Column>

        <template #expansion="{data: job}">
          <div class="expansion">
            <div>
              <h4>Config</h4>
              <pre class="json">{{ JSON.stringify(job.config, null, 2) }}</pre>
            </div>
            <div>
              <h4>Stats</h4>
              <pre class="json">{{ JSON.stringify(job.stats, null, 2) }}</pre>
            </div>
          </div>
        </template>
      </DataTable>
    </div>

    <RunNowDialog v-model:visible="runNowVisible" :functions="data?.available_types || []"/>
  </div>
</template>

<style scoped>
.stats {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: .15rem .75rem;
}

.dim {
  opacity: .6;
}

.schedule-cell {
  display: flex;
  gap: .5rem;
  align-items: flex-start;
}

.schedule-cell > .pi {
  margin-top: .2rem;
}

.expansion {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.expansion h4 {
  margin: 0 0 .5rem;
}

.jobs-table :deep(td) {
  vertical-align: top;
}
</style>

<script setup>
import {api} from '../../api.js'
import {usePolling} from '../../composables/usePolling.js'
import {durationHuman, formatNumber, formatPercent} from '../../format.js'
import PollStatus from '../PollStatus.vue'
import {useNow} from '../../composables/useNow.js'
import RelTime from '../RelTime.vue'

const STALE_AFTER_SEC = 10 * 60

// the bot saves fetcher stats every ~20 s and announces it with a `fetchers` event
const {data, error, loading, updatedAt} = usePolling(() => api.overview('fetchers'), {
  interval: 60000,
  refreshOn: 'fetchers',
})
const now = useNow()

function health(f) {
  if (f.success_rate < 90) return {severity: 'danger', label: `${f.error_counter} errors`}
  if (f.error_counter) return {severity: 'warn', label: `${f.error_counter} errors`}
  return {severity: 'success', label: 'OK'}
}

const isStale = (f, now) => now - f.last_timestamp > STALE_AFTER_SEC
</script>

<template>
  <div class="stack">
    <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
    <Message v-if="data?.all_paused" severity="warn">All fetchers are paused.</Message>
    <DataTable :value="data?.trackers || []" :loading="!data && !error" size="small" striped-rows scrollable
               sort-field="name" :sort-order="1">
      <Column field="name" header="Fetcher" sortable>
        <template #body="{data: f}"><span class="mono">{{ f.name }}</span></template>
      </Column>
      <Column header="Health">
        <template #body="{data: f}">
          <Tag :severity="health(f).severity" :value="health(f).label"/>
        </template>
      </Column>
      <Column field="last_timestamp" header="Last run" sortable>
        <template #body="{data: f}">
          <span :class="{err: isStale(f, now)}" class="nowrap">
            <i v-if="isStale(f, now)" class="pi pi-exclamation-triangle"/>
            <RelTime :ts="f.last_timestamp" mode="ago" empty="never"/>
          </span>
        </template>
      </Column>
      <Column field="sleep_period" header="Interval" sortable body-class="num" header-class="num-h">
        <template #body="{data: f}">{{ durationHuman(f.sleep_period) }}</template>
      </Column>
      <Column field="success_rate" header="Success" sortable body-class="num" header-class="num-h">
        <template #body="{data: f}">{{ formatPercent(f.success_rate) }}</template>
      </Column>
      <Column field="total_ticks" header="Ticks" sortable body-class="num" header-class="num-h">
        <template #body="{data: f}">
          <span v-if="f.total_ticks">{{ formatNumber(f.total_ticks) }}</span>
          <span v-else class="muted">none yet</span>
        </template>
      </Column>
      <Column field="avg_run_time" header="Avg run" sortable body-class="num" header-class="num-h">
        <template #body="{data: f}">{{ f.avg_run_time ? durationHuman(f.avg_run_time) : '—' }}</template>
      </Column>
      <Column field="last_run_time" header="Last run time" sortable body-class="num" header-class="num-h">
        <template #body="{data: f}">{{ f.last_run_time ? durationHuman(f.last_run_time) : '—' }}</template>
      </Column>
    </DataTable>
  </div>
</template>

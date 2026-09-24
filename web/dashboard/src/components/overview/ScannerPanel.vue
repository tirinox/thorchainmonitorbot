<script setup>
import {computed} from 'vue'
import {api} from '../../api.js'
import {usePolling} from '../../composables/usePolling.js'
import {formatDate, formatNumber, formatPercent, timeAgo} from '../../format.js'
import PollStatus from '../PollStatus.vue'
import {useNow} from '../../composables/useNow.js'

const {data, error, loading, updatedAt} = usePolling(() => api.overview('scanner'), {
  interval: 30000,
  refreshOn: 'scanner',
  eventFilter: (e) => e.role === 'main',
  eventDelay: 250,
})
const now = useNow()

const s = computed(() => {
  const d = data.value
  if (!d) return null
  const sinceScan = now.value - d.last_scanned_at_ts
  return {
    ...d,
    now: now.value,
    sinceScan,
    scanIsOld: sinceScan > 30,
    scanIsVeryOld: sinceScan > 5 * 60,
  }
})
</script>

<template>
  <div class="stack">
    <div class="row" style="justify-content: space-between">
      <div v-if="s" class="row">
        <Tag v-if="s.is_scanning" severity="success" value="SCANNING NOW" class="pulse"/>
        <Tag v-else severity="secondary" value="Idle"/>
        <Tag v-if="s.is_aggressive_mode" severity="warn" value="Aggressive mode"/>
        <span class="muted small">role: {{ s.role }}</span>
      </div>
      <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
    </div>

    <template v-if="s">
      <Message v-if="s.last_message && s.last_message.length > 3" severity="warn">
        Last message: <em>{{ s.last_message }}</em>
      </Message>

      <div class="grid">
        <div class="metric">
          <div class="label">Last scanned block</div>
          <div class="value">{{ formatNumber(s.last_scanned_block) }}</div>
          <div class="hint" :class="{err: s.scanIsOld}">
            <i v-if="s.scanIsOld" class="pi pi-exclamation-triangle"/>
            {{ timeAgo(s.last_scanned_at_ts, s.now) }}
          </div>
        </div>
        <div class="metric">
          <div class="label">Last THOR block</div>
          <div class="value">{{ formatNumber(s.thor_height_block) }}</div>
          <div class="hint">Lag: <strong :class="{warn: s.lag_behind_thor > 5}">{{ s.lag_behind_thor }}</strong> blocks</div>
        </div>
        <div class="metric">
          <div class="label">Success rate</div>
          <div class="value">{{ formatPercent(s.success_rate, undefined, 2) }}</div>
          <div class="hint">{{ formatNumber(s.errors_encountered) }} errors</div>
        </div>
        <div class="metric">
          <div class="label">Blocks scanned / processed</div>
          <div class="value">{{ formatNumber(s.total_blocks_scanned) }}</div>
          <div class="hint">{{ formatNumber(s.total_blocks_processed) }} processed</div>
        </div>
      </div>

      <div class="panel">
        <table class="kv">
          <tbody>
          <tr>
            <th>Last scanned at</th>
            <td>
              {{ formatDate(s.last_scanned_at_ts) }} · {{ timeAgo(s.last_scanned_at_ts, s.now) }}
              <i v-if="s.scanIsVeryOld" class="pi pi-exclamation-circle err"/>
            </td>
          </tr>
          <tr>
            <th>Scanner started at</th>
            <td>{{ formatDate(s.started_at_ts) }} · {{ timeAgo(s.started_at_ts, s.now) }}</td>
          </tr>
          <tr>
            <th>Scanning time</th>
            <td>max <strong>{{ s.max_block_scanning_time.toFixed(2) }}</strong> s,
              avg <strong>{{ s.avg_block_scanning_time.toFixed(2) }}</strong> s
            </td>
          </tr>
          <tr>
            <th>Processing time</th>
            <td>max <strong>{{ s.max_block_processing_time.toFixed(2) }}</strong> s,
              avg <strong>{{ s.avg_block_processing_time.toFixed(2) }}</strong> s
            </td>
          </tr>
          </tbody>
        </table>
      </div>

      <Panel header="Raw state" toggleable collapsed>
        <pre class="json">{{ JSON.stringify(s, null, 2) }}</pre>
      </Panel>
    </template>
  </div>
</template>

<style scoped>
.kv {
  border-collapse: collapse;
  width: 100%;
}

.kv th {
  text-align: left;
  font-weight: 500;
  color: var(--app-muted);
  padding: .35rem 1rem .35rem 0;
  white-space: nowrap;
  width: 1%;
}

.kv td {
  padding: .35rem 0;
}
</style>

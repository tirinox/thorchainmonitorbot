<script setup>
import {computed} from 'vue'
import {useToast} from 'primevue/usetoast'
import {useConfirm} from 'primevue/useconfirm'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {durationHuman, formatUsd} from '../format.js'
import PollStatus from '../components/PollStatus.vue'
import RelTime from '../components/RelTime.vue'

const toast = useToast()
const confirm = useConfirm()

// the bars fall with time, so there is no event for them: plain polling
const {data, error, loading, updatedAt, refresh} = usePolling(api.thresholds, {interval: 10000})

const directions = computed(() => data.value?.directions || [])

const staticMetrics = computed(() => {
  const s = data.value?.static
  if (!s) return []
  return [
    {label: 'Swap start (streaming ≥)', value: formatUsd(s.start_usd)},
    {label: 'Swap finish, regular rule (≥)', value: formatUsd(s.finish_min_usd_total), hint: `and ${s.curve_mult}× the depth curve share of the shallowest pool`},
    {label: 'Affiliate fee (≥)', value: formatUsd(s.affiliate_fee_usd)},
    {label: 'DEX aggregator swap (≥)', value: formatUsd(s.dex_usd)},
    {label: 'Trade asset swap (≥)', value: formatUsd(s.trade_asset_usd)},
  ]
})


function reset(direction) {
  const all = !direction
  confirm.require({
    header: all ? 'Reset all dynamic bars' : 'Reset dynamic bar',
    message: all
        ? 'Drop the dynamic bars of all directions? The next swaps are checked by the static thresholds only.'
        : `Drop the dynamic bar of ${direction}? The next swap of it is checked by the static thresholds only.`,
    icon: 'pi pi-exclamation-triangle',
    acceptProps: {label: 'Reset', severity: 'danger'},
    rejectProps: {label: 'Cancel', severity: 'secondary', text: true},
    accept: async () => {
      try {
        const res = await api.resetThresholds(direction)
        toast.add({severity: 'info', summary: 'Reset', detail: `${res.reset} direction(s)`, life: 3000})
      } catch (e) {
        toast.add({severity: 'error', summary: 'Reset failed', detail: e.message, life: 8000})
      }
      refresh()
    },
  })
}

const arrow = (dir) => dir.replace('>', ' → ')
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Swap thresholds</h1>
      <div class="actions">
        <Button label="Reset all" icon="pi pi-refresh" severity="danger" text size="small"
                :disabled="!directions.length" @click="reset(null)"/>
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
      </div>
    </div>

    <div class="stack">
      <Panel header="Static thresholds (before the dynamic correction)">
        <div class="grid">
          <div v-for="m in staticMetrics" :key="m.label" class="metric">
            <div class="label">{{ m.label }}</div>
            <div class="value">{{ m.value }}</div>
            <div v-if="m.hint" class="muted small">{{ m.hint }}</div>
          </div>
        </div>
      </Panel>

      <Panel header="Dynamic correction">
        <p v-if="data && !data.enabled" class="muted" style="margin: 0">
          Turned off: <code>tx.swap.dynamic_threshold.enabled</code> is not set in the config.
        </p>
        <template v-else-if="data">
          <p class="muted small" style="margin-top: 0">
            Every announced swap raises the bar of its direction to its volume × (1 + growth). A swap must clear the
            bar on top of the static thresholds (a finish of a swap whose start was announced is never held back).
            The bar halves every half-life.
          </p>
          <div class="grid">
            <div class="metric">
              <div class="label">Growth per message</div>
              <div class="value">+{{ Math.round(data.config.growth * 100) }}%</div>
            </div>
            <div class="metric">
              <div class="label">Half-life</div>
              <div class="value">{{ durationHuman(data.config.half_life_sec) }}</div>
            </div>
            <div class="metric">
              <div class="label">Bar cap</div>
              <div class="value">{{ formatUsd(data.config.max_bar_usd) }}</div>
            </div>
            <div class="metric">
              <div class="label">Raised directions</div>
              <div class="value" :class="{warn: directions.length}">{{ directions.length }}</div>
            </div>
          </div>
        </template>
      </Panel>

      <DataTable v-if="data?.enabled" :value="directions" data-key="direction" size="small" scrollable
                 :loading="!data && !error">
        <template #empty>All directions are cool: only the static thresholds apply.</template>
        <Column header="Direction">
          <template #body="{data: d}"><span class="mono">{{ arrow(d.direction) }}</span></template>
        </Column>
        <Column header="Dynamic bar">
          <template #body="{data: d}"><strong>{{ formatUsd(d.bar_usd) }}</strong></template>
        </Column>
        <Column header="Start: static → now">
          <template #body="{data: d}">
            <span class="muted">{{ formatUsd(d.static_start_usd) }}</span> → <strong>{{ formatUsd(d.effective_start_usd) }}</strong>
          </template>
        </Column>
        <Column header="Finish: static → now">
          <template #body="{data: d}">
            <span class="muted">{{ formatUsd(d.static_finish_usd) }}</span> → <strong>{{ formatUsd(d.effective_finish_usd) }}</strong>
          </template>
        </Column>
        <Column header="Last announced">
          <template #body="{data: d}">
            {{ formatUsd(d.last_volume_usd) }}
            <span class="muted small"> · <RelTime :ts="d.ts" mode="ago"/> · series of {{ d.count }}</span>
            <div v-if="d.last_tx" class="mono muted small">{{ d.last_tx.slice(0, 12) }}…</div>
          </template>
        </Column>
        <Column header="Back to normal">
          <template #body="{data: d}">
            <RelTime v-if="d.cools_at_ts" :ts="d.cools_at_ts" mode="until"/>
            <span v-else class="muted">below static</span>
          </template>
        </Column>
        <Column style="width: 1%">
          <template #body="{data: d}">
            <Button icon="pi pi-refresh" text rounded severity="danger" size="small"
                    v-tooltip.left="'Reset this direction'" aria-label="Reset this direction"
                    @click="reset(d.direction)"/>
          </template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

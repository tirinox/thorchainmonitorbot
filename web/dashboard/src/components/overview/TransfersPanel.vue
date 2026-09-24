<script setup>
import {computed} from 'vue'
import {api} from '../../api.js'
import {usePolling} from '../../composables/usePolling.js'
import {formatNumber, formatUsd} from '../../format.js'
import PollStatus from '../PollStatus.vue'

const {data, error, loading, updatedAt} = usePolling(() => api.overview('transfers'), {interval: 30000})

const metrics = computed(() => {
  const d = data.value
  if (!d) return []
  const usd = (rune) => d.usd_per_rune ? formatUsd(rune * d.usd_per_rune) : ''
  return [
    {label: 'Total volume', value: `${formatNumber(d.volume_rune)} ᚱ`, hint: usd(d.volume_rune)},
    {label: 'Transfers', value: formatNumber(d.transfer_count)},
    {label: 'CEX inflow', value: `${formatNumber(d.cex_inflow_rune)} ᚱ`, hint: `${formatNumber(d.cex_inflow_count)} deposits`},
    {label: 'CEX outflow', value: `${formatNumber(d.cex_outflow_rune)} ᚱ`, hint: `${formatNumber(d.cex_outflow_count)} withdrawals`},
    {label: 'CEX netflow', value: `${formatNumber(d.cex_netflow_rune)} ᚱ`, hint: 'positive = net deposits to CEX'},
  ]
})
</script>

<template>
  <div class="stack">
    <div class="row" style="justify-content: space-between">
      <span v-if="data" class="muted">
        {{ data.period_days }} days · {{ data.start_date }} — {{ data.end_date }}
      </span>
      <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
    </div>
    <div class="grid">
      <div v-for="m in metrics" :key="m.label" class="metric">
        <div class="label">{{ m.label }}</div>
        <div class="value">{{ m.value }}</div>
        <div v-if="m.hint" class="hint">{{ m.hint }}</div>
      </div>
    </div>
    <DataTable v-if="data?.daily?.length" :value="data.daily" size="small" striped-rows scrollable>
      <Column field="date" header="Day"/>
      <Column header="Volume" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.volume_rune) }} ᚱ</template>
      </Column>
      <Column header="Transfers" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.transfer_count) }}</template>
      </Column>
      <Column header="CEX in" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.cex_inflow_rune) }} ᚱ</template>
      </Column>
      <Column header="CEX out" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.cex_outflow_rune) }} ᚱ</template>
      </Column>
      <Column header="Netflow" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.cex_netflow_rune) }} ᚱ</template>
      </Column>
    </DataTable>
  </div>
</template>

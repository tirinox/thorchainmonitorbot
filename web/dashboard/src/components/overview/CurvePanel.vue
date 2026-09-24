<script setup>
import {api} from '../../api.js'
import {usePolling} from '../../composables/usePolling.js'
import {formatNumber, formatUsd} from '../../format.js'
import PollStatus from '../PollStatus.vue'

// pool depths change slowly
const {data, error, loading, updatedAt} = usePolling(() => api.overview('curve'), {interval: 30000})
</script>

<template>
  <div class="stack">
    <p class="muted small" style="margin: 0">
      Minimum transaction volume that triggers an alert, per pool, derived from the depth curve.
    </p>
    <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
    <DataTable :value="data || []" :loading="!data && !error" size="small" striped-rows scrollable
               row-group-mode="subheader" group-rows-by="module">
      <template #groupheader="{data: r}">
        <strong>{{ r.module }}</strong>
        <span class="muted small"> · multiplier {{ r.curve_mult }}</span>
      </template>
      <Column field="module" header="Module"/>
      <Column field="pool" header="Pool">
        <template #body="{data: r}"><span class="mono">{{ r.pool }}</span></template>
      </Column>
      <Column header="Pool depth" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatUsd(r.depth_usd) }}</template>
      </Column>
      <Column header="Min volume, USD" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatUsd(r.min_usd_volume) }}</template>
      </Column>
      <Column header="Min volume, RUNE" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.min_rune_volume) }} ᚱ</template>
      </Column>
    </DataTable>
  </div>
</template>

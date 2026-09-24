<script setup>
import {api} from '../../api.js'
import {usePolling} from '../../composables/usePolling.js'
import {formatNumber, formatPercent} from '../../format.js'
import PollStatus from '../PollStatus.vue'

const {data, error, loading, updatedAt} = usePolling(() => api.overview('dedup'), {interval: 3000})
</script>

<template>
  <div class="stack">
    <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
    <DataTable :value="data || []" :loading="!data && !error" size="small" striped-rows scrollable>
      <Column field="name" header="Name">
        <template #body="{data: r}"><span class="mono">{{ r.name }}</span></template>
      </Column>
      <Column header="Bits set" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.bits_set) }}</template>
      </Column>
      <Column header="Size" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.size) }}</template>
      </Column>
      <Column header="Fill" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatPercent(r.bits_set, r.size, 3) }}</template>
      </Column>
      <Column header="Reads" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.total_reads) }}</template>
      </Column>
      <Column header="Positive" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.positive) }}</template>
      </Column>
      <Column header="Hit rate" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatPercent(r.positive, r.total_reads) }}</template>
      </Column>
      <Column header="Writes" body-class="num" header-class="num-h">
        <template #body="{data: r}">{{ formatNumber(r.writes) }}</template>
      </Column>
    </DataTable>
  </div>
</template>

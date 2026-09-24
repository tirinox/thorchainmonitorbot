<script setup>
import {api} from '../../api.js'
import {usePolling} from '../../composables/usePolling.js'
import {formatNumber} from '../../format.js'
import PollStatus from '../PollStatus.vue'

const {data, error, loading, updatedAt} = usePolling(() => api.overview('stats'), {interval: 10000})
</script>

<template>
  <div class="stack">
    <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
    <div class="grid">
      <div class="metric">
        <div class="label">Users with settings</div>
        <div class="value">{{ data ? formatNumber(data.user_settings_count) : '…' }}</div>
      </div>
      <div class="metric">
        <div class="label">Bot users</div>
        <div class="value">{{ data ? formatNumber(data.bot_user_count) : '…' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {actionInfo} from '../audit.js'
import RelTime from './RelTime.vue'

// "alice · 2 h ago": the latest change made through the dashboard (from the activity log).
defineProps({
  change: {type: Object, default: null},
})
</script>

<template>
  <span v-if="change" class="last-change muted small" v-tooltip.top="`${actionInfo(change.action).label} by ${change.actor}`">
    <i class="pi pi-user-edit"/> {{ change.actor }} · <RelTime :ts="change.ts" mode="ago"/>
  </span>
</template>

<style scoped>
.last-change {
  white-space: nowrap;
}

.last-change .pi {
  font-size: .75rem;
}
</style>

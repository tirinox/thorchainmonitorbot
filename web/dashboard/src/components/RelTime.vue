<script setup>
import {computed} from 'vue'
import {useNow} from '../composables/useNow.js'
import {formatDate, timeAgo, timeUntil} from '../format.js'
import {displayTz} from '../timezone.js'

// "5 min ago" / "in 3 min" that stays current, with the exact time on hover.
const props = defineProps({
  ts: {type: Number, default: null},
  // 'ago' | 'until' | 'auto' (past → ago, future → until)
  mode: {type: String, default: 'auto'},
  empty: {type: String, default: '—'},
})

const now = useNow()

const text = computed(() => {
  if (!props.ts) return props.empty
  const future = props.ts > now.value
  if (props.mode === 'ago' || (props.mode === 'auto' && !future)) return timeAgo(props.ts, now.value)
  return timeUntil(props.ts, now.value)
})

const tooltip = computed(() => {
  if (!props.ts) return null
  const shown = formatDate(props.ts, {tzName: true})
  return displayTz.value === 'UTC' ? shown : `${shown} · ${formatDate(props.ts, {tz: 'UTC', tzName: true})}`
})
</script>

<template>
  <span v-tooltip.top="tooltip" :class="{reltime: !!ts}">{{ text }}</span>
</template>

<style scoped>
.reltime {
  cursor: help;
  text-decoration: underline dotted color-mix(in srgb, currentColor 35%, transparent);
  text-underline-offset: 3px;
}
</style>

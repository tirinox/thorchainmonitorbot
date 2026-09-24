<script setup>
import {durationHuman, formatDate} from '../format.js'

// The last finished runs of a job as a row of dots, oldest on the left.
defineProps({
  runs: {type: Array, default: () => []},
})

const LABELS = {ok: 'success', error: 'failed', skipped: 'skipped (job disabled)'}

function tooltip(run) {
  const parts = [`${formatDate(run.ts)} — ${LABELS[run.status] || run.status}`]
  if (run.elapsed) parts.push(`took ${durationHuman(run.elapsed)}`)
  if (run.manual) parts.push('started from the dashboard')
  if (run.error) parts.push(run.error)
  return parts.join(' · ')
}
</script>

<template>
  <div class="history" :aria-label="`Last ${runs.length} runs`">
    <span v-for="(run, i) in runs" :key="`${run.ts}-${i}`" class="dot" :class="[run.status, {manual: run.manual}]"
          v-tooltip.top="tooltip(run)"/>
    <span v-if="!runs.length" class="muted small">no runs yet</span>
  </div>
</template>

<style scoped>
.history {
  display: flex;
  gap: 3px;
  align-items: center;
  min-height: 12px;
  margin-bottom: .35rem;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  background: var(--app-muted);
  cursor: help;
}

.dot.ok {
  background: var(--app-ok);
}

.dot.error {
  background: var(--app-err);
}

.dot.skipped {
  background: var(--app-warn);
}

/* runs started by hand get a ring, scheduled ones are plain */
.dot.manual {
  box-shadow: 0 0 0 1.5px var(--app-panel), 0 0 0 3px currentColor;
  color: var(--app-muted);
}
</style>

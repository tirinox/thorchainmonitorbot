<script setup>
import {computed} from 'vue'
import {formatRunTime} from '../format.js'
import {displayTz, sameOffset, tzShortName} from '../timezone.js'
import RelTime from './RelTime.vue'

// A schedule as described by the API (see app/dashboard/services/schedule.py), with the viewer's local
// equivalents whenever the scheduler's timezone differs from the display one.
const props = defineProps({
  schedule: {type: Object, required: true},
})

const differentZone = computed(() => !sameOffset(props.schedule.timezone, displayTz.value))

const localTimes = computed(() => {
  const times = props.schedule.local_times
  if (!times?.length) return null
  const shift = (d) => d > 0 ? ' (next day)' : d < 0 ? ' (previous day)' : ''
  return times.map(t => `${t.time}${shift(t.day_shift)}`).join(', ')
})
</script>

<template>
  <div class="schedule">
    <div>
      <span :class="{err: schedule.invalid}">{{ schedule.text }}</span>
      <Tag v-if="schedule.tz_relevant" :value="schedule.timezone" severity="secondary" class="tz"
           v-tooltip.top="`The bot evaluates this schedule in ${schedule.timezone}`"/>
    </div>
    <div v-if="localTimes" class="muted small">
      = {{ localTimes }} {{ tzShortName(displayTz) }}
    </div>
    <div v-if="schedule.run_ts" class="muted small">
      <template v-if="differentZone">= {{ formatRunTime(schedule.run_ts, {tzName: true}) }} · </template>
      <RelTime :ts="schedule.run_ts"/>
    </div>
  </div>
</template>

<style scoped>
.tz {
  margin-left: .4rem;
  font-size: .7rem;
  padding: .05rem .35rem;
  vertical-align: middle;
}
</style>

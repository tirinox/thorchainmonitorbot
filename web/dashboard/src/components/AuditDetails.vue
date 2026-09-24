<script setup>
import {computed} from 'vue'
import {formatValue} from '../audit.js'

const props = defineProps({
  entry: {type: Object, required: true},
})

const d = computed(() => props.entry.details || {})
const changes = computed(() => Object.entries(d.value.changes || {}))
// everything that is not rendered in a special way
const extra = computed(() => {
  const {changes: _c, old: _o, new: _n, run_id: _r, config: _cfg, ...rest} = d.value
  return Object.entries(rest)
})
</script>

<template>
  <div class="details">
    <template v-if="entry.action === 'flag.set' || entry.action === 'flag.delete'">
      <span class="change">
        <span class="old">{{ formatValue(d.old) }}</span>
        <template v-if="entry.action === 'flag.set'"> → <span class="new">{{ formatValue(d.new) }}</span></template>
      </span>
    </template>

    <div v-for="[key, [before, after]] in changes" :key="key" class="change">
      <span class="key mono">{{ key }}</span>
      <span class="old mono">{{ formatValue(before) }}</span> →
      <span class="new mono">{{ formatValue(after) }}</span>
    </div>
    <span v-if="entry.action === 'job.update' && !changes.length" class="muted">saved without changes</span>

    <span v-for="[key, value] in extra" :key="key" class="kv mono">
      <span class="muted">{{ key }}=</span>{{ formatValue(value) }}
    </span>

    <RouterLink v-if="d.run_id" :to="{name: 'logs', query: {q: d.run_id}}" class="small">
      <i class="pi pi-history"/> run logs
    </RouterLink>
  </div>
</template>

<style scoped>
.details {
  display: flex;
  flex-wrap: wrap;
  gap: .25rem .75rem;
  align-items: baseline;
}

.change {
  width: 100%;
  word-break: break-word;
}

.key {
  color: var(--app-muted);
  margin-right: .4rem;
}

.old {
  color: var(--app-err);
  text-decoration: line-through;
  text-decoration-color: color-mix(in srgb, currentColor 40%, transparent);
}

.new {
  color: var(--app-ok);
}

.kv {
  word-break: break-word;
}
</style>

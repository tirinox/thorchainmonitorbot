<script setup>
import {computed, ref, watch} from 'vue'
import {api} from '../api.js'
import {runs} from '../runs.js'
import {durationHuman} from '../format.js'
import {useNow} from '../composables/useNow.js'
import PreviewMessages from './PreviewMessages.vue'

// What a "preview" run built: the messages per public channel, as the bot would have posted them.
const props = defineProps({
  runId: {type: String, required: true},
})

const now = useNow()
const run = computed(() => runs[props.runId])
const preview = ref(null)
const loadError = ref(null)

async function load() {
  try {
    preview.value = await api.preview(props.runId)
  } catch (e) {
    loadError.value = e.message
  }
}

watch(() => run.value?.status, (status) => {
  if (status === 'success' && !preview.value) load()
}, {immediate: true})
</script>

<template>
  <div class="preview-result">
    <div v-if="!run || run.status === 'running'" class="row muted">
      <i class="pi pi-spin pi-spinner"/>
      Building the alert<template v-if="run"> · {{ durationHuman(now - run.started_ts) }}</template>…
      <span class="small">(infographics can take a while)</span>
    </div>
    <Message v-else-if="run.status !== 'success'" severity="error">{{ run.result }}</Message>
    <Message v-else-if="loadError" severity="error">{{ loadError }}</Message>
    <div v-else-if="!preview" class="row muted"><i class="pi pi-spin pi-spinner"/> Loading…</div>

    <PreviewMessages v-else :preview="preview"/>
  </div>
</template>

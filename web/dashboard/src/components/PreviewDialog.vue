<script setup>
import {computed, ref, watch} from 'vue'
import {runs, startJobRun} from '../runs.js'
import {channelLabel} from '../channels.js'
import PreviewResult from './PreviewResult.vue'

// Preview a job's alert (nothing is sent) and optionally try it in the test channel(s).
const props = defineProps({
  job: {type: Object, default: null},  // a row of GET /jobs
  testChannels: {type: Array, default: () => []},
})
const visible = defineModel('visible', {type: Boolean, default: false})

const previewRunId = ref(null)
const testRunId = ref(null)
const startError = ref(null)

const previewRun = computed(() => previewRunId.value ? runs[previewRunId.value] : null)
const testRun = computed(() => testRunId.value ? runs[testRunId.value] : null)

async function start(mode) {
  startError.value = null
  try {
    const run = await startJobRun(props.job.id, mode)
    if (mode === 'preview') previewRunId.value = run.run_id
    else testRunId.value = run.run_id
  } catch (e) {
    startError.value = e.message
  }
}

watch(visible, (v) => {
  if (v && props.job) {
    previewRunId.value = null
    testRunId.value = null
    start('preview')
  }
})

const busy = computed(() => previewRun.value?.status === 'running' || testRun.value?.status === 'running')
const testTargets = computed(() => props.testChannels.map(channelLabel).join(', '))

const testStatus = computed(() => {
  const r = testRun.value
  if (!r) return null
  if (r.status === 'running') return {severity: 'info', text: `Sending to ${testTargets.value}…`}
  if (r.status === 'success') return {severity: 'success', text: `Sent to ${testTargets.value}.`}
  return {severity: 'error', text: String(r.result)}
})
</script>

<template>
  <Dialog v-model:visible="visible" modal :style="{width: '52rem'}" :breakpoints="{'900px': '96vw'}">
    <template #header>
      <div>
        <div class="p-dialog-title">Alert preview</div>
        <div v-if="job" class="muted small">{{ job.config.func }} · <span class="mono">{{ job.id }}</span></div>
      </div>
    </template>

    <div class="stack">
      <Message v-if="startError" severity="error">{{ startError }}</Message>
      <PreviewResult v-if="previewRunId" :key="previewRunId" :run-id="previewRunId"/>
      <Message v-if="testStatus" :severity="testStatus.severity">{{ testStatus.text }}</Message>
    </div>

    <template #footer>
      <span v-if="!testChannels.length" class="muted small footer-note">
        Add <code>broadcasting.test_channels</code> to config.yaml to send test posts.
      </span>
      <Button label="Close" text severity="secondary" @click="visible = false"/>
      <Button label="Rebuild" icon="pi pi-refresh" severity="secondary" outlined :disabled="busy"
              @click="start('preview')"/>
      <Button label="Send to test channel" icon="pi pi-send" :disabled="!testChannels.length || busy"
              :loading="testRun?.status === 'running'"
              v-tooltip.top="testChannels.length ? testTargets : 'No test channels configured'"
              @click="start('test')"/>
    </template>
  </Dialog>
</template>

<style scoped>
.footer-note {
  margin-right: auto;
}
</style>

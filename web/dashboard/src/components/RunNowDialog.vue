<script setup>
import {computed, ref, watch} from 'vue'
import {isFinished, runs, startFunctionRun} from '../runs.js'
import {useNow} from '../composables/useNow.js'
import {durationHuman} from '../format.js'
import {parseJsonObject} from '../jsonArgs.js'

const props = defineProps({
  functions: {type: Array, default: () => []},
})
const visible = defineModel('visible', {type: Boolean, default: false})

const func = ref(null)
const argsText = ref('{}')
const timeout = ref(3600)
const starting = ref(false)
const formError = ref(null)
const runId = ref(null)
const now = useNow()

// the run started from this dialog, kept live by `run` events
const run = computed(() => runId.value ? runs[runId.value] : null)

const status = computed(() => {
  const r = run.value
  if (!r) return null
  const elapsed = durationHuman((r.finished_ts || now.value) - r.started_ts)
  switch (r.status) {
    case 'running':
      return {severity: 'info', text: `${r.func} is running… ${elapsed}. You can close this dialog; you will be notified.`}
    case 'success':
      return {severity: 'success', text: `${r.func} finished in ${elapsed}.`}
    case 'timeout':
      return {severity: 'warn', text: r.result}
    default:
      return {severity: 'error', text: `${r.func}: ${r.result}`}
  }
})

watch(visible, (v) => {
  if (v) {
    formError.value = null
    if (isFinished(run.value)) runId.value = null
    if (!func.value && props.functions.length) func.value = props.functions[0]
  }
})

const argsCheck = computed(() => parseJsonObject(argsText.value))

async function start() {
  formError.value = null
  const {value: args, error} = argsCheck.value
  if (error) return
  starting.value = true
  try {
    runId.value = (await startFunctionRun(func.value, args, timeout.value)).run_id
  } catch (e) {
    formError.value = e.message
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Run a job function now" :style="{width: '36rem'}"
          :breakpoints="{'640px': '95vw'}">
    <div class="stack">
      <div class="field">
        <label for="rn-func">Function</label>
        <Select id="rn-func" v-model="func" :options="functions" filter placeholder="Select a function"/>
      </div>
      <div class="field">
        <label for="rn-args">Arguments (JSON object)</label>
        <Textarea id="rn-args" v-model="argsText" rows="6" class="mono" auto-resize :invalid="!!argsCheck.error"/>
        <span v-if="argsCheck.error" class="err small"><i class="pi pi-times-circle"/> {{ argsCheck.error }}</span>
        <span class="help">Passed only to this one-off run.</span>
      </div>
      <div class="field">
        <label for="rn-timeout">Wait for the result up to, seconds</label>
        <InputNumber input-id="rn-timeout" v-model="timeout" :min="5" :max="21600" :step="60" show-buttons/>
        <span class="help">The job keeps running in the bot even if nobody waits for it.</span>
      </div>
      <Message v-if="formError" severity="error">{{ formError }}</Message>
      <Message v-if="status" :severity="status.severity">
        <span class="row"><i v-if="run?.status === 'running'" class="pi pi-spin pi-spinner"/> {{ status.text }}</span>
      </Message>
    </div>
    <template #footer>
      <Button label="Close" text severity="secondary" @click="visible = false"/>
      <Button label="Run now" icon="pi pi-play" :loading="starting"
              :disabled="!func || run?.status === 'running' || !!argsCheck.error"
              @click="start"/>
    </template>
  </Dialog>
</template>

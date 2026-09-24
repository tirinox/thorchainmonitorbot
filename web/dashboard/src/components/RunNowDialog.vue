<script setup>
import {computed, ref, watch} from 'vue'
import {isFinished, runs, startFunctionRun} from '../runs.js'
import {useNow} from '../composables/useNow.js'
import {durationHuman} from '../format.js'
import {parseJsonObject} from '../jsonArgs.js'
import {channelLabel} from '../channels.js'
import PreviewResult from './PreviewResult.vue'

const props = defineProps({
  functions: {type: Array, default: () => []},
  testChannels: {type: Array, default: () => []},
})

const MODES = computed(() => [
  {value: 'preview', label: 'Preview', icon: 'pi pi-eye', help: 'Builds the messages and shows them here. Nothing is sent.'},
  {
    value: 'test', label: 'Test channel', icon: 'pi pi-send', disabled: !props.testChannels.length,
    help: props.testChannels.length
        ? `Posts only to ${props.testChannels.map(channelLabel).join(', ')}.`
        : 'Add broadcasting.test_channels to config.yaml to use this.',
  },
  {value: 'normal', label: 'Real run', icon: 'pi pi-play', help: 'Posts to all public channels, like a scheduled run.'},
])
const mode = ref('preview')
const modeHelp = computed(() => MODES.value.find(m => m.value === mode.value)?.help)
const START_LABELS = {preview: 'Build preview', test: 'Send to test channel', normal: 'Run now'}
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
    runId.value = (await startFunctionRun(func.value, args, timeout.value, mode.value)).run_id
  } catch (e) {
    formError.value = e.message
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Run a job function now" :style="{width: '44rem'}"
          :breakpoints="{'760px': '96vw'}">
    <div class="stack">
      <div class="field">
        <label for="rn-func">Function</label>
        <Select id="rn-func" v-model="func" :options="functions" filter placeholder="Select a function"/>
      </div>
      <div class="field">
        <label>Mode</label>
        <SelectButton v-model="mode" :options="MODES" option-label="label" option-value="value"
                      option-disabled="disabled" :allow-empty="false">
          <template #option="{option}"><i :class="option.icon"/> <span>{{ option.label }}</span></template>
        </SelectButton>
        <span class="help">{{ modeHelp }}</span>
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
      <PreviewResult v-if="run?.mode === 'preview'" :key="runId" :run-id="runId"/>
      <Message v-else-if="status" :severity="status.severity">
        <span class="row"><i v-if="run?.status === 'running'" class="pi pi-spin pi-spinner"/> {{ status.text }}</span>
      </Message>
    </div>
    <template #footer>
      <Button label="Close" text severity="secondary" @click="visible = false"/>
      <Button :label="START_LABELS[mode]" :icon="MODES.find(m => m.value === mode)?.icon" :loading="starting"
              :severity="mode === 'normal' ? 'danger' : undefined"
              :disabled="!func || run?.status === 'running' || !!argsCheck.error"
              @click="start"/>
    </template>
  </Dialog>
</template>

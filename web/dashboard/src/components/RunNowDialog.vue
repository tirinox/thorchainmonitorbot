<script setup>
import {ref, watch} from 'vue'
import {api} from '../api.js'

const props = defineProps({
  functions: {type: Array, default: () => []},
})
const visible = defineModel('visible', {type: Boolean, default: false})

const func = ref(null)
const argsText = ref('{}')
const timeout = ref(30)
const running = ref(false)
const result = ref(null)  // {severity, text}

watch(visible, (v) => {
  if (v) {
    result.value = null
    if (!func.value && props.functions.length) func.value = props.functions[0]
  }
})

function parseArgs() {
  const parsed = JSON.parse(argsText.value.trim() || '{}')
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Arguments must be a JSON object')
  }
  return parsed
}

async function run() {
  let args
  try {
    args = parseArgs()
  } catch (e) {
    result.value = {severity: 'error', text: `Invalid arguments: ${e.message}`}
    return
  }
  running.value = true
  result.value = null
  try {
    const r = await api.runFunction(func.value, args, timeout.value)
    result.value = r.ok
        ? {severity: 'success', text: `${func.value} executed successfully.`}
        : {severity: 'error', text: `${func.value}: ${r.result}`}
  } catch (e) {
    result.value = {severity: 'error', text: e.message}
  } finally {
    running.value = false
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
        <Textarea id="rn-args" v-model="argsText" rows="6" class="mono" auto-resize/>
        <span class="help">Passed only to this one-off run.</span>
      </div>
      <div class="field">
        <label for="rn-timeout">Timeout, seconds</label>
        <InputNumber input-id="rn-timeout" v-model="timeout" :min="5" :max="3600" :step="5" show-buttons/>
      </div>
      <Message v-if="result" :severity="result.severity">{{ result.text }}</Message>
    </div>
    <template #footer>
      <Button label="Close" text severity="secondary" @click="visible = false"/>
      <Button label="Run now" icon="pi pi-play" :loading="running" :disabled="!func" @click="run"/>
    </template>
  </Dialog>
</template>

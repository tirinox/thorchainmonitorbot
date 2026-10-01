<script setup>
import {computed, ref, watch} from 'vue'
import {api} from '../api.js'
import {formatNumber} from '../format.js'
import PreviewMessages from './PreviewMessages.vue'

// The post of an achievement as the bot would publish it: built by the dashboard itself, nothing is sent
// and the achievement records are not touched.
const props = defineProps({
  item: {type: Object, default: null},  // a row of GET /achievements
})
const visible = defineModel('visible', {type: Boolean, default: false})

const mode = ref('next')
const customValue = ref(null)
const preview = ref(null)
const error = ref(null)
const loading = ref(false)
let requestNo = 0

const modes = computed(() => {
  const it = props.item
  if (!it) return []
  return [
    {value: 'next', label: it.next && it.milestone ? `Next milestone · ${it.next.text}` : 'Next milestone'},
    ...(it.milestone ? [{value: 'last', label: `Last recorded · ${it.milestone.text}`}] : []),
    {value: 'value', label: 'Custom value'},
  ]
})

async function build() {
  if (mode.value === 'value' && !customValue.value) return
  const no = ++requestNo
  loading.value = true
  error.value = null
  try {
    const result = await api.previewAchievement({
      key: props.item.key,
      specialization: props.item.specialization,
      mode: mode.value,
      ...(mode.value === 'value' ? {value: Math.round(customValue.value)} : {}),
    })
    if (no === requestNo) preview.value = result
  } catch (e) {
    if (no === requestNo) {
      error.value = e.message
      preview.value = null
    }
  } finally {
    if (no === requestNo) loading.value = false
  }
}

watch(visible, (v) => {
  if (v && props.item) {
    mode.value = 'next'
    customValue.value = props.item.current?.value ?? null
    preview.value = null
    build()
  } else {
    requestNo++  // drop the answer of a request still in flight
  }
})

watch(mode, () => visible.value && build())

const event = computed(() => preview.value?.event)
</script>

<template>
  <Dialog v-model:visible="visible" modal :style="{width: '52rem'}" :breakpoints="{'900px': '96vw'}">
    <template #header>
      <div>
        <div class="p-dialog-title">Post preview</div>
        <div v-if="item" class="row small" style="gap: .4rem">
          <span>{{ item.title }}</span> <span class="mono muted">{{ item.id }}</span>
        </div>
      </div>
    </template>

    <div class="stack">
      <div class="row">
        <SelectButton v-model="mode" :options="modes" option-label="label" option-value="value"
                      :allow-empty="false" size="small"/>
        <template v-if="mode === 'value'">
          <InputNumber v-model="customValue" :min="1" :use-grouping="true" placeholder="Value of the metric"
                       size="small" @keydown.enter="build"/>
          <Button label="Build" icon="pi pi-refresh" size="small" :disabled="!customValue || loading" @click="build"/>
        </template>
      </div>

      <Message v-if="error" severity="error">{{ error }}</Message>
      <div v-if="loading" class="row muted">
        <i class="pi pi-spin pi-spinner"/> Building the post… <span class="small">(the card can take a while)</span>
      </div>

      <template v-if="preview && !loading">
        <div v-if="event" class="muted small">
          As if the value were <strong>{{ formatNumber(event.value) }}</strong>:
          milestone {{ formatNumber(event.milestone) }}<template v-if="event.prev_milestone">,
          previous {{ formatNumber(event.prev_milestone) }}</template>.
        </div>
        <PreviewMessages :preview="preview"/>
      </template>
    </div>

    <template #footer>
      <Button label="Close" text severity="secondary" @click="visible = false"/>
      <Button label="Rebuild" icon="pi pi-refresh" severity="secondary" outlined :disabled="loading" @click="build"/>
    </template>
  </Dialog>
</template>

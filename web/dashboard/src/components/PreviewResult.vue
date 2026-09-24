<script setup>
import {computed, ref, watch} from 'vue'
import {api} from '../api.js'
import {runs} from '../runs.js'
import {channelIcon, channelTitle} from '../channels.js'
import {durationHuman} from '../format.js'
import {useNow} from '../composables/useNow.js'
import {telegramHtml} from '../telegramHtml.js'

// What a "preview" run built: the messages per public channel, as the bot would have posted them.
const props = defineProps({
  runId: {type: String, required: true},
})

const now = useNow()
const run = computed(() => runs[props.runId])
const preview = ref(null)
const loadError = ref(null)
const showRaw = ref(false)

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

// channels with the same language get the very same message: show each distinct message once
const variants = computed(() => {
  const groups = new Map()
  for (const m of preview.value?.messages || []) {
    const key = `${m.image}|${m.text}`
    if (!groups.has(key)) groups.set(key, {text: m.text, image: m.image, channels: []})
    groups.get(key).channels.push({...m.channel, blocked_by_flag: m.blocked_by_flag})
  }
  return [...groups.values()]
})

const rendersHtml = (variant) => !showRaw.value && variant.channels.some(c => c.type === 'telegram')
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

    <div v-else class="stack">
      <div class="row" style="justify-content: space-between">
        <span class="muted small">
          {{ preview.messages.length }} channel(s) · {{ variants.length }} distinct message(s) · nothing was sent
        </span>
        <span class="row small">
          <ToggleSwitch input-id="preview-raw" v-model="showRaw"/>
          <label for="preview-raw">Raw text</label>
        </span>
      </div>

      <div v-for="(v, i) in variants" :key="i" class="variant">
        <div class="row channels">
          <Tag v-for="c in v.channels" :key="c.selector" :severity="c.blocked_by_flag ? 'warn' : 'secondary'"
               v-tooltip.top="c.blocked_by_flag ? `Would not be sent: flag ${c.blocked_by_flag} is off` : channelTitle(c.type)">
            <i :class="channelIcon(c.type)"/> {{ c.channel }} · {{ c.lang }}
            <i v-if="c.blocked_by_flag" class="pi pi-ban"/>
          </Tag>
        </div>
        <a v-if="v.image !== null" :href="api.previewImageUrl(runId, v.image)" target="_blank" rel="noopener">
          <img :src="api.previewImageUrl(runId, v.image)" class="shot" alt="Alert image"/>
        </a>
        <div v-if="v.text && rendersHtml(v)" class="msg-text" v-html="telegramHtml(v.text)"/>
        <pre v-else-if="v.text" class="msg-text">{{ v.text }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.variant {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: .75rem;
  display: flex;
  flex-direction: column;
  gap: .6rem;
}

.channels {
  gap: .35rem;
}

.shot {
  display: block;
  max-width: 100%;
  max-height: 60vh;
  border-radius: 6px;
  border: 1px solid var(--app-border);
}

.msg-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: .9rem;
  line-height: 1.45;
  background: var(--app-bg);
  border-radius: 6px;
  padding: .6rem .75rem;
}

.msg-text :deep(code), .msg-text :deep(pre) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: .85em;
}

.msg-text :deep(tg-spoiler) {
  background: var(--app-muted);
  color: transparent;
  border-radius: 3px;
}

.msg-text :deep(tg-spoiler:hover) {
  color: inherit;
  background: transparent;
}
</style>

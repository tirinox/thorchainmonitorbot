<script setup>
import {computed, onMounted, reactive, ref, watch} from 'vue'
import {useRouter} from 'vue-router'
import {useToast} from 'primevue/usetoast'
import {api} from '../api.js'
import {channelIcon, channelLabel} from '../channels.js'
import {formatRunTime} from '../format.js'
import {browserTz, displayTz, sameOffset} from '../timezone.js'
import RelTime from '../components/RelTime.vue'
import ScheduleText from '../components/ScheduleText.vue'

const props = defineProps({
  id: {type: String, default: null},  // set when editing
})

const router = useRouter()
const toast = useToast()

const isEdit = computed(() => !!props.id)
const meta = ref(null)
const loadError = ref(null)
const saveError = ref(null)
const saving = ref(false)
const existing = ref(null)

const VARIANTS = [
  {value: 'interval', label: 'Interval', icon: 'pi pi-clock'},
  {value: 'cron', label: 'Cron', icon: 'pi pi-calendar'},
  {value: 'date', label: 'One-off date', icon: 'pi pi-calendar-plus'},
]
const INTERVAL_FIELDS = ['weeks', 'days', 'hours', 'minutes', 'seconds']
const CRON_FIELDS = ['year', 'month', 'day', 'week', 'day_of_week', 'hour', 'minute', 'second']

const form = reactive({
  func: null,
  enabled: false,
  variant: 'interval',
  argsText: '{}',
  channels: [],
  interval: {weeks: 0, days: 0, hours: 1, minutes: 0, seconds: 0},
  cron: Object.fromEntries(CRON_FIELDS.map(f => [f, ''])),
  date: new Date(Date.now() + 3600_000),
  max_instances: 1,
  coalesce: true,
  misfire_grace_time: 0,
})

// "not added yet" function types first, like the old dashboard did
const functionOptions = computed(() => {
  const m = meta.value
  if (!m) return []
  const opts = m.available_types.map(func => ({func, count: m.distribution[func] || 0}))
  return [...opts.filter(o => !o.count), ...opts.filter(o => o.count)]
})

const unknownChannels = computed(() => existing.value?.channels.unknown || [])

// Dates saved by the old dashboard are naive; the server runs in UTC
function parseServerDate(s) {
  if (!s) return new Date()
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`)
}

function fillFromJob(job) {
  const c = job.config
  const {channels: _, ...args} = c.args || {}
  Object.assign(form, {
    func: c.func,
    enabled: c.enabled,
    variant: c.variant,
    argsText: JSON.stringify(args, null, 2),
    channels: job.channels.resolved.map(ch => ch.selector),
    max_instances: c.max_instances,
    coalesce: c.coalesce,
    misfire_grace_time: c.misfire_grace_time || 0,
  })
  if (c.interval) {
    form.interval = Object.fromEntries(INTERVAL_FIELDS.map(f => [f, c.interval[f] || 0]))
  }
  if (c.cron) {
    form.cron = Object.fromEntries(CRON_FIELDS.map(f => [f, c.cron[f] ?? '']))
  }
  if (c.date) {
    form.date = parseServerDate(c.date.run_date)
  }
}

onMounted(async () => {
  try {
    meta.value = await api.jobs()
    if (isEdit.value) {
      existing.value = meta.value.jobs.find(j => j.config.id === props.id)
      if (!existing.value) {
        loadError.value = `Job "${props.id}" not found.`
        return
      }
      fillFromJob(existing.value)
    } else {
      form.func = functionOptions.value[0]?.func ?? null
    }
  } catch (e) {
    loadError.value = e.message
  }
})

// just the trigger part of the payload; also what the live preview sends
function schedulePart() {
  const part = {variant: form.variant}
  if (form.variant === 'interval') {
    part.interval = Object.fromEntries(INTERVAL_FIELDS.map(f => [f, form.interval[f] || null]))
  } else if (form.variant === 'cron') {
    part.cron = Object.fromEntries(CRON_FIELDS.map(f => [f, String(form.cron[f] ?? '').trim() || null]))
  } else if (form.variant === 'date') {
    part.date = form.date ? {run_date: form.date.toISOString()} : null
  }
  return part
}

// ---- live preview: description + next runs, computed by the server with the bot's own APScheduler rules
const preview = ref(null)
const previewLoading = ref(false)
let previewTimer = null
let previewSeq = 0

async function loadPreview() {
  const seq = ++previewSeq
  previewLoading.value = true
  try {
    const result = await api.previewSchedule({...schedulePart(), tz: displayTz.value, count: 5})
    if (seq === previewSeq) preview.value = result
  } catch (e) {
    if (seq === previewSeq) preview.value = {ok: false, error: e.message}
  } finally {
    if (seq === previewSeq) previewLoading.value = false
  }
}

watch(() => JSON.stringify(schedulePart()) + displayTz.value, () => {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(loadPreview, 350)
}, {immediate: true})

const showSchedulerTz = computed(() => preview.value?.ok && !sameOffset(preview.value.timezone, displayTz.value))

function buildPayload() {
  let args
  try {
    args = JSON.parse(form.argsText.trim() || '{}')
  } catch (e) {
    throw new Error(`Job arguments are not valid JSON: ${e.message}`)
  }
  if (!args || typeof args !== 'object' || Array.isArray(args)) {
    throw new Error('Job arguments must be a JSON object.')
  }

  if (form.variant === 'date' && !form.date) throw new Error('Pick a run date.')
  const payload = {
    ...schedulePart(),
    func: form.func,
    enabled: form.enabled,
    args,
    channels: form.channels,
    max_instances: form.max_instances,
    coalesce: form.coalesce,
    misfire_grace_time: form.misfire_grace_time || null,
  }
  return payload
}

async function save() {
  saveError.value = null
  let payload
  try {
    payload = buildPayload()
  } catch (e) {
    saveError.value = e.message
    return
  }

  saving.value = true
  try {
    const job = isEdit.value ? await api.updateJob(props.id, payload) : await api.createJob(payload)
    toast.add({
      severity: 'success',
      summary: isEdit.value ? 'Job saved' : 'Job created',
      detail: `${job.id} — apply the configuration on the Jobs page to take effect.`,
      life: 5000,
    })
    router.push({name: 'jobs'})
  } catch (e) {
    saveError.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div style="max-width: 900px">
    <div class="page-header">
      <h1>{{ isEdit ? 'Edit job' : 'New job' }}</h1>
      <div class="actions">
        <span v-if="isEdit" class="mono muted">{{ id }}</span>
      </div>
    </div>

    <Message v-if="loadError" severity="error">{{ loadError }}</Message>
    <div v-else-if="!meta" class="row muted"><ProgressSpinner style="width: 1.5rem; height: 1.5rem"/> Loading…</div>

    <form v-else class="stack" @submit.prevent="save">
      <div class="panel stack">
        <div class="field">
          <label for="job-func">Function</label>
          <InputText v-if="isEdit" id="job-func" :model-value="form.func" disabled/>
          <Select v-else input-id="job-func" v-model="form.func" :options="functionOptions" option-label="func"
                  option-value="func" filter placeholder="Select a job function">
            <template #option="{option}">
              <div class="row" style="justify-content: space-between; width: 100%">
                <span>{{ option.func }}</span>
                <Tag v-if="option.count" severity="secondary" :value="`added · ${option.count}`"/>
                <Tag v-else severity="success" value="new"/>
              </div>
            </template>
          </Select>
          <span v-if="!isEdit" class="help">Types that are not configured yet are listed first.</span>
        </div>

        <div class="row">
          <ToggleSwitch input-id="job-enabled" v-model="form.enabled"/>
          <label for="job-enabled">Enabled</label>
        </div>
      </div>

      <div class="panel stack">
        <div class="field">
          <label>Trigger</label>
          <SelectButton v-model="form.variant" :options="VARIANTS" option-label="label" option-value="value"
                        :allow-empty="false">
            <template #option="{option}">
              <i :class="option.icon"/> <span>{{ option.label }}</span>
            </template>
          </SelectButton>
        </div>

        <div v-if="form.variant === 'interval'" class="form-grid">
          <div v-for="f in INTERVAL_FIELDS" :key="f" class="field">
            <label :for="`iv-${f}`">{{ f }}</label>
            <InputNumber :input-id="`iv-${f}`" v-model="form.interval[f]" :min="0" :max="1000" show-buttons fluid/>
          </div>
        </div>

        <template v-else-if="form.variant === 'cron'">
          <div class="form-grid">
            <div v-for="f in CRON_FIELDS" :key="f" class="field">
              <label :for="`cron-${f}`">{{ f }}</label>
              <InputText :id="`cron-${f}`" v-model="form.cron[f]" placeholder="*" class="mono" fluid/>
            </div>
          </div>
          <span class="help muted small">
            APScheduler cron fields. Empty fields larger than the smallest one you fill mean “any”; smaller ones
            mean 0 (so hour <code>9</code> alone is 09:00:00). Examples: minute <code>*/10</code>,
            day_of_week <code>mon-fri</code>, hour <code>9,18</code>. Check the preview below.
          </span>
        </template>

        <div v-else class="field">
          <label for="job-date">Run at (your browser's time, {{ browserTz }})</label>
          <DatePicker input-id="job-date" v-model="form.date" show-time hour-format="24" show-seconds show-icon/>
          <span class="help">Stored in UTC: {{ form.date ? form.date.toISOString() : '—' }}</span>
        </div>

        <div class="preview" :class="{stale: previewLoading}">
          <div v-if="!preview" class="muted small">Preview…</div>
          <div v-else-if="!preview.ok" class="err small"><i class="pi pi-times-circle"/> {{ preview.error }}</div>
          <template v-else>
            <ScheduleText :schedule="preview.schedule"/>
            <div class="small muted" style="margin-top: .5rem">Next runs</div>
            <ol class="runs small">
              <li v-for="ts in preview.next_runs" :key="ts">
                <span>{{ formatRunTime(ts) }}</span>
                <span v-if="showSchedulerTz" class="muted"> · {{ formatRunTime(ts, {tz: preview.timezone}) }} {{ preview.timezone }}</span>
                <span class="muted"> · <RelTime :ts="ts"/></span>
              </li>
            </ol>
            <Message v-if="preview.warning" severity="secondary" size="small" :closable="false">
              {{ preview.warning }}
            </Message>
          </template>
        </div>
      </div>

      <div class="panel stack">
        <div class="field">
          <label for="job-channels">Broadcast channels</label>
          <MultiSelect input-id="job-channels" v-model="form.channels" :options="meta.channels" option-value="selector"
                       :option-label="channelLabel" display="chip" filter placeholder="All channels (default)">
            <template #option="{option}">
              <span class="row"><i :class="channelIcon(option.type)"/> {{ channelLabel(option) }}</span>
            </template>
          </MultiSelect>
          <span class="help">Leave empty to send scheduled alerts to every configured channel. Saved as <code>args.channels</code>.</span>
        </div>
        <Message v-if="unknownChannels.length" severity="warn">
          Saved <code>args.channels</code> has entries that do not match configured channels:
          <strong>{{ unknownChannels.join(', ') }}</strong>. Saving will replace them with the selection above.
        </Message>

        <div class="field">
          <label for="job-args">Job arguments (JSON object)</label>
          <Textarea id="job-args" v-model="form.argsText" rows="6" auto-resize class="mono"/>
          <span class="help">Passed as kwargs to the job function on every run.</span>
        </div>
      </div>

      <Panel header="Advanced" toggleable collapsed>
        <div class="form-grid">
          <div class="field">
            <label for="job-maxinst">max_instances</label>
            <InputNumber input-id="job-maxinst" v-model="form.max_instances" :min="1" :max="100" show-buttons fluid/>
          </div>
          <div class="field">
            <label for="job-misfire">misfire_grace_time, s</label>
            <InputNumber input-id="job-misfire" v-model="form.misfire_grace_time" :min="0" :max="3600" fluid/>
            <span class="help">0 = not set</span>
          </div>
          <div class="field">
            <label for="job-coalesce">coalesce</label>
            <ToggleSwitch input-id="job-coalesce" v-model="form.coalesce"/>
          </div>
        </div>
      </Panel>

      <Message v-if="saveError" severity="error">{{ saveError }}</Message>

      <div class="row">
        <Button type="submit" :label="isEdit ? 'Save job' : 'Create job'" icon="pi pi-check" :loading="saving"
                :disabled="!form.func || preview?.ok === false"/>
        <Button label="Cancel" severity="secondary" text @click="router.push({name: 'jobs'})"/>
      </div>
    </form>
  </div>
</template>

<style scoped>
.preview {
  border-top: 1px dashed var(--app-border);
  padding-top: .75rem;
  transition: opacity .15s;
}

.preview.stale {
  opacity: .6;
}

.runs {
  margin: .35rem 0 .5rem;
  padding-left: 1.4rem;
  font-variant-numeric: tabular-nums;
}
</style>

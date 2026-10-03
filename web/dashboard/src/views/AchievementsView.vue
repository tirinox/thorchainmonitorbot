<script setup>
import {computed, reactive, ref} from 'vue'
import {useRoute} from 'vue-router'
import {useToast} from 'primevue/usetoast'
import {useConfirm} from 'primevue/useconfirm'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {useNow} from '../composables/useNow.js'
import {durationHuman, formatPercent} from '../format.js'
import PollStatus from '../components/PollStatus.vue'
import RelTime from '../components/RelTime.vue'
import AchievementPreviewDialog from '../components/AchievementPreviewDialog.vue'

// the bot rewrites a live value at most once a minute, so there is nothing to gain from a faster poll
const {data, error, loading, updatedAt, refresh} = usePolling(api.achievements, {interval: 30000})

const toast = useToast()
const confirm = useConfirm()
const now = useNow()
// the Activity page links here with ?q=<achievement id>
const search = ref(useRoute().query.q || '')
const show = ref('all')

const settings = computed(() => data.value?.settings)
const items = computed(() => data.value?.items || [])
const count = (status) => items.value.filter(i => i.status === status).length

const STATUS = {
  tracking: {label: 'tracking', severity: 'success'},
  pending: {label: 'waiting to post', severity: 'warn'},
  stale: {label: 'stale', severity: 'warn'},
  below_threshold: {label: 'below cut-off', severity: 'secondary'},
  no_data: {label: 'no data', severity: 'secondary'},
  disabled: {label: 'off', severity: 'secondary'},
}

function statusTip(item) {
  switch (item.status) {
    case 'tracking':
      return 'Fed by the bot; a post goes out when it crosses the next milestone.'
    case 'pending':
      return item.single_event
          ? 'This record is past its next milestone, but the post was held back and a single event is not fed again. It is posted only when a larger one comes.'
          : 'Past its next milestone. The post is held back by the post limit and goes out on a later feed.'
    case 'stale':
      return `Not fed for more than ${durationHuman(settings.value.stale_after)}. Its next milestone will be saved without a post.`
    case 'disabled':
      return 'Turned off in ach_list.py: the bot ignores it and keeps its last milestone as it is.'
    case 'below_threshold':
      return 'Under its cut-off: the bot ignores it until it gets there. Passing the cut-off starts tracking, without a post.'
    default:
      return 'The bot has never fed this metric.'
  }
}

const FILTERS = computed(() => [
  {value: 'all', label: `All ${items.value.length}`},
  ...Object.entries(STATUS).map(([value, s]) => ({value, label: `${s.label} ${count(value)}`})),
])

const visibleItems = computed(() => {
  const q = search.value.trim().toLowerCase()
  return items.value.filter(i =>
      (show.value === 'all' || i.status === show.value) &&
      (!q || `${i.title} ${i.id}`.toLowerCase().includes(q)))
})

const SCALES = {
  normal: {label: '1 · 2 · 5', tip: 'Milestones at 1, 2, 5, 10, 20, 50, 100…'},
  every_digit: {label: '1 · 2 · 3 … 9', tip: 'Milestones at every leading digit: 1, 2, 3 … 9, 10, 20, 30…'},
  every_int: {label: 'every 1', tip: 'Every whole number is a milestone.'},
}

const cooldown = computed(() => {
  const cd = settings.value?.cooldown
  if (!cd) return null
  const paused = cd.active_until && cd.active_until > now.value
  return {
    ...cd,
    paused,
    rule: `${cd.hits_before_cd} posts, then a ${durationHuman(cd.period)} pause`,
  }
})

const rowClass = (item) => item.status === 'pending' ? 'row-warning' : ''
const percent = (item) => formatPercent(100 * item.progress, undefined, 0)

// ---- stale on demand: the tracker goes by the time of the last feed, which this rewrites
const busy = reactive({})

async function setStale(item, stale) {
  busy[item.id] = true
  try {
    await api.setAchievementStale(item.key, item.specialization, stale)
    toast.add({
      severity: 'info',
      summary: stale ? 'Marked stale' : 'No longer stale',
      detail: `${item.title}: the next milestone ${stale ? 'is saved without a post' : 'will be posted'}`,
      life: 4000,
    })
    await refresh()
  } catch (e) {
    toast.add({severity: 'error', summary: 'Failed to change the achievement', detail: e.message, life: 8000})
  } finally {
    delete busy[item.id]
  }
}

function clearStale(item) {
  // a post may go out right away: say so before it does
  const next = item.next?.text
  let warning = null
  if (item.crossed) {
    warning = `Its value is already past ${next}: the bot will post this milestone on the next feed.`
  } else if (item.current?.source !== 'live') {
    warning = `The value now is unknown here. If it is already past ${next}, the bot will post this milestone on the next feed.`
  }
  if (!warning) return setStale(item, false)

  confirm.require({
    header: 'Clear stale',
    message: `${item.title}. ${warning}`,
    icon: 'pi pi-megaphone',
    acceptProps: {label: 'Clear stale'},
    rejectProps: {label: 'Cancel', severity: 'secondary', text: true},
    accept: () => setStale(item, false),
  })
}

const previewVisible = ref(false)
const previewItem = ref(null)

function openPreview(item) {
  previewItem.value = item
  previewVisible.value = true
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Achievements</h1>
      <div class="actions">
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
      </div>
    </div>

    <div class="stack">
      <p class="muted" style="margin: 0">
        Protocol milestones the bot announces. A metric is tracked once it passes its cut-off; a post goes out when
        its value crosses the next milestone of its scale.
      </p>

      <Message v-if="settings && !settings.enabled" severity="warn" :closable="false">
        Achievements are turned off (<code>achievements.enabled</code> in config.yaml): nothing is fed or posted.
      </Message>

      <div v-if="settings" class="grid">
        <div class="metric">
          <div class="label">Tracked</div>
          <div class="value">{{ count('tracking') + count('pending') }} <span class="muted of">of {{ items.length }}</span></div>
          <div class="hint">{{ count('below_threshold') }} below cut-off · {{ count('no_data') }} without data</div>
        </div>
        <div class="metric">
          <div class="label">Waiting to post</div>
          <div class="value" :class="{warn: count('pending')}">{{ count('pending') }}</div>
          <div class="hint">{{ count('stale') }} stale: will catch up without a post</div>
        </div>
        <div class="metric" v-tooltip.top="'achievements.cooldown in config.yaml: after that many posts the bot waits; a milestone crossed meanwhile is posted on a later feed.'">
          <div class="label">Post limit</div>
          <div v-if="cooldown.paused" class="value warn">Paused</div>
          <div v-else class="value">{{ cooldown.hits }} <span class="muted of">of {{ cooldown.hits_before_cd }}</span></div>
          <div class="hint">
            <template v-if="cooldown.paused">ends <RelTime :ts="cooldown.active_until" mode="until"/> · </template>{{ cooldown.rule }}
          </div>
        </div>
        <div class="metric" v-tooltip.top="'achievements.stale_after in config.yaml: a metric not fed for longer (the bot or its source was down) saves the milestones it missed without posting them.'">
          <div class="label">Stale after</div>
          <div class="value">{{ durationHuman(settings.stale_after) }}</div>
          <div class="hint">without a feed: silent catch-up</div>
        </div>
      </div>

      <div class="toolbar">
        <IconField class="search">
          <InputIcon class="pi pi-search"/>
          <InputText v-model="search" placeholder="Search achievements…" fluid/>
        </IconField>
        <SelectButton v-model="show" :options="FILTERS" option-label="label" option-value="value"
                      :allow-empty="false" size="small"/>
      </div>

      <DataTable :value="visibleItems" data-key="id" :loading="!data && !error" :row-class="rowClass"
                 size="small" scrollable removable-sort class="ach-table">
        <template #empty>{{ items.length ? 'No achievements match the search or filter.' : 'No achievements.' }}</template>

        <Column header="Achievement" sortable sort-field="title" style="min-width: 15rem">
          <template #body="{data: a}">
            <div class="cell">
              <strong>{{ a.title }}</strong>
              <span class="mono muted break">{{ a.id }}</span>
              <span><Tag :severity="STATUS[a.status].severity" :value="STATUS[a.status].label"
                         v-tooltip.top="statusTip(a)"/></span>
            </div>
          </template>
        </Column>

        <Column header="Last milestone" sortable sort-field="milestone.ts" style="min-width: 13rem">
          <template #body="{data: a}">
            <div v-if="a.milestone" class="cell">
              <span class="big" v-tooltip.top="`The value was ${a.milestone.reached} then`">{{ a.milestone.text }}</span>
              <span v-if="!a.milestone.ts" class="muted small"
                    v-tooltip.top="'The starting point, saved on the first feed. Nothing has been posted since.'">
                never posted
              </span>
              <span v-else-if="a.milestone.silent" class="small warn"
                    v-tooltip.top="'Saved without a post: the metric caught up after an outage.'">
                <i class="pi pi-volume-off"/> not posted, saved <RelTime :ts="a.milestone.ts" mode="ago"/>
              </span>
              <span v-else class="small">posted <RelTime :ts="a.milestone.ts" mode="ago"/></span>
              <span v-if="a.previous" class="muted small">
                before: {{ a.previous.text }} · <RelTime :ts="a.previous.ts" mode="ago"/>
              </span>
            </div>
            <span v-else class="muted">—</span>
          </template>
        </Column>

        <Column header="Now" style="min-width: 11rem">
          <template #body="{data: a}">
            <div v-if="a.current" class="cell">
              <span class="num-left">{{ a.current.text }}</span>
              <span v-if="a.current.source === 'record'" class="muted small"
                    v-tooltip.top="'The bot has not saved a live value of this metric yet: this is the value at the last milestone.'">
                at the milestone
              </span>
              <span v-else-if="a.single_event" class="muted small"
                    v-tooltip.top="'The largest single event seen. It is not a level: smaller events do not change it.'">
                record, set <RelTime :ts="a.current.ts" mode="ago"/>
              </span>
              <span v-else-if="a.current.source === 'live'" class="muted small">
                fed <RelTime :ts="a.current.ts" mode="ago"/>
              </span>
            </div>
            <span v-else class="muted">—</span>
          </template>
        </Column>

        <Column header="Next milestone" sortable sort-field="progress" style="min-width: 13rem">
          <template #body="{data: a}">
            <div v-if="a.next || a.progress !== null" class="cell">
              <span v-if="a.next">
                <i class="pi muted small" :class="a.descending ? 'pi-arrow-down-right' : 'pi-arrow-up-right'"/>
                <strong> {{ a.next.text }}</strong>
                <span v-if="a.next.ts" class="muted small"> · <RelTime :ts="a.next.ts" mode="until"/></span>
              </span>
              <span v-else class="muted small">to the cut-off {{ a.threshold?.text }}</span>
              <template v-if="a.progress !== null">
                <ProgressBar :value="100 * a.progress" :show-value="false" class="bar"
                             :class="{dim: !a.next, full: a.status === 'pending'}"/>
                <span class="muted small">{{ percent(a) }}</span>
              </template>
            </div>
            <span v-else class="muted">—</span>
          </template>
        </Column>

        <Column header="Cut-off" style="min-width: 10rem">
          <template #body="{data: a}">
            <div class="cell">
              <span v-if="a.threshold" v-tooltip.top="'The bot ignores the metric until it gets here.'">
                {{ a.descending ? '≤' : '≥' }} {{ a.threshold.text }}
              </span>
              <span v-else-if="a.threshold_count" class="muted"
                    v-tooltip.top="'Each pool has its own cut-off, see ach_list.py.'">
                per pool ({{ a.threshold_count }})
              </span>
              <span v-else class="muted">none</span>
              <span class="muted small" v-tooltip.top="SCALES[a.scale].tip">steps {{ SCALES[a.scale].label }}</span>
            </div>
          </template>
        </Column>

        <Column header="" style="width: 1%">
          <template #body="{data: a}">
            <div class="row nowrap" style="flex-wrap: nowrap; gap: .15rem">
              <template v-if="a.milestone && a.can_be_stale">
                <Button v-if="a.stale" icon="pi pi-bell" text rounded aria-label="Clear stale"
                        :loading="!!busy[a.id]"
                        v-tooltip.left="'Clear stale: its next milestone will be posted'" @click="clearStale(a)"/>
                <Button v-else icon="pi pi-bell-slash" text rounded severity="secondary" aria-label="Mark stale"
                        :loading="!!busy[a.id]"
                        v-tooltip.left="'Mark stale: its next milestone is saved without a post. A feed that crosses no milestone clears the mark.'"
                        @click="setStale(a, true)"/>
              </template>
              <Button icon="pi pi-eye" text rounded severity="secondary" aria-label="Preview the post"
                      v-tooltip.left="'Preview the post (sends nothing)'" @click="openPreview(a)"/>
            </div>
          </template>
        </Column>
      </DataTable>
    </div>

    <AchievementPreviewDialog v-model:visible="previewVisible" :item="previewItem"/>
  </div>
</template>

<style scoped>
.of {
  font-size: 1rem;
  font-weight: 500;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
  align-items: center;
}

.toolbar .search {
  flex: 1 1 240px;
}

.cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: .25rem;
}

.big {
  font-size: 1.1rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.num-left {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.bar {
  width: 100%;
  max-width: 14rem;
  height: .45rem;
}

.bar.dim :deep(.p-progressbar-value) {
  background: var(--app-muted);
}

.bar.full :deep(.p-progressbar-value) {
  background: var(--app-warn);
}

.ach-table :deep(td) {
  vertical-align: top;
}
</style>

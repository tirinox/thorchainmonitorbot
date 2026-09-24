<script setup>
import {computed, reactive, ref, watch} from 'vue'
import {useToast} from 'primevue/usetoast'
import {useConfirm} from 'primevue/useconfirm'
import {api} from '../api.js'
import {usePolling} from '../composables/usePolling.js'
import {timeAgo} from '../format.js'
import PollStatus from '../components/PollStatus.vue'
import {useNow} from '../composables/useNow.js'

const toast = useToast()
const confirm = useConfirm()

// `flags` events come from dashboard edits; the bot may also create flags on its own, hence the slow poll
const {data, error, loading, updatedAt, refresh} = usePolling(api.flags, {interval: 60000, refreshOn: 'flags'})
const now = useNow()

const search = ref('')
const pending = reactive({})  // path -> optimistic value while the request is in flight
const expandedKeys = ref({})

const flags = computed(() => (data.value || []).map(f => (
    f.path in pending ? {...f, value: pending[f.path]} : f
)))

const visibleFlags = computed(() => {
  const q = search.value.trim().toLowerCase()
  return q ? flags.value.filter(f => f.path.toLowerCase().includes(q)) : flags.value
})

const countOn = (list) => list.filter(f => f.value).length

// "a:b:c" paths -> tree of groups with flags as leaves
const nodes = computed(() => {
  const root = {key: '', name: '', children: new Map(), flags: []}
  for (const flag of visibleFlags.value) {
    const parts = flag.path.split(':')
    let node = root
    parts.slice(0, -1).forEach((part, i) => {
      const key = parts.slice(0, i + 1).join(':')
      if (!node.children.has(part)) node.children.set(part, {key, name: part, children: new Map(), flags: []})
      node = node.children.get(part)
      node.flags.push(flag)
    })
    node.children.set(`#${flag.path}`, {key: flag.path, name: parts.at(-1), flag, children: new Map(), flags: [flag]})
  }
  const convert = (n) => ({
    key: n.key,
    leaf: !!n.flag,
    data: {name: n.name, flag: n.flag || null, total: n.flags.length, on: countOn(n.flags)},
    children: [...n.children.values()]
        .sort((a, b) => Number(!!a.flag) - Number(!!b.flag) || a.name.localeCompare(b.name))
        .map(convert),
  })
  return convert(root).children
})

function allGroupKeys(list, acc = {}) {
  for (const n of list) {
    if (!n.leaf) {
      acc[n.key] = true
      allGroupKeys(n.children, acc)
    }
  }
  return acc
}

const expandAll = () => (expandedKeys.value = allGroupKeys(nodes.value))
const collapseAll = () => (expandedKeys.value = {})

// expand everything on first load and while searching
let initialized = false
watch(nodes, (n) => {
  if (!initialized && n.length) {
    initialized = true
    expandAll()
  }
})
watch(search, (q) => q && expandAll())

async function setFlag(flag, value) {
  pending[flag.path] = value
  try {
    await api.setFlag(flag.path, value)
    toast.add({severity: 'info', summary: `${flag.path} = ${value}`, life: 2500})
    await refresh()
  } catch (e) {
    toast.add({severity: 'error', summary: 'Failed to change flag', detail: e.message, life: 8000})
  } finally {
    delete pending[flag.path]
  }
}

function deleteFlag(flag) {
  confirm.require({
    header: 'Delete flag',
    message: `Delete "${flag.path}" from the database? The bot recreates it with the default value on next access.`,
    icon: 'pi pi-exclamation-triangle',
    acceptProps: {label: 'Delete', severity: 'danger'},
    rejectProps: {label: 'Cancel', severity: 'secondary', text: true},
    accept: async () => {
      try {
        await api.deleteFlag(flag.path)
        toast.add({severity: 'info', summary: 'Deleted', detail: flag.path, life: 3000})
      } catch (e) {
        toast.add({severity: 'error', summary: 'Delete failed', detail: e.message, life: 8000})
      }
      refresh()
    },
  })
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Bot settings</h1>
      <div class="actions">
        <PollStatus :updated-at="updatedAt" :error="error" :loading="loading"/>
      </div>
    </div>

    <div class="stack">
      <p class="muted" style="margin: 0">Connection gate matrix: feature flags stored in Redis (<code>Flagship:*</code>).</p>

      <div class="grid">
        <div class="metric">
          <div class="label">Total flags</div>
          <div class="value">{{ flags.length }}</div>
        </div>
        <div class="metric">
          <div class="label">Enabled</div>
          <div class="value ok">{{ countOn(flags) }}</div>
        </div>
        <div class="metric">
          <div class="label">Disabled</div>
          <div class="value" :class="{err: flags.length - countOn(flags)}">{{ flags.length - countOn(flags) }}</div>
        </div>
      </div>

      <div class="row">
        <IconField style="flex: 1 1 240px">
          <InputIcon class="pi pi-search"/>
          <InputText v-model="search" placeholder="Filter by path…" fluid/>
        </IconField>
        <Button label="Expand all" icon="pi pi-plus" text severity="secondary" @click="expandAll"/>
        <Button label="Collapse all" icon="pi pi-minus" text severity="secondary" @click="collapseAll"/>
      </div>

      <TreeTable :value="nodes" v-model:expanded-keys="expandedKeys" :loading="!data && !error" size="small"
                 scrollable class="flags">
        <template #empty>No flags found.</template>
        <Column field="name" header="Flag" expander>
          <template #body="{node}">
            <span v-if="node.data.flag" class="mono" :class="node.data.flag.value ? 'ok' : 'err'">{{ node.data.name }}</span>
            <span v-else>
              <strong>{{ node.data.name }}</strong>
              <span class="muted small"> · {{ node.data.on }}/{{ node.data.total }} on</span>
            </span>
          </template>
        </Column>
        <Column header="Value" style="width: 7rem">
          <template #body="{node}">
            <ToggleSwitch v-if="node.data.flag" :model-value="node.data.flag.value"
                          :disabled="node.data.flag.path in pending"
                          :aria-label="node.data.flag.path"
                          @update:model-value="v => setFlag(node.data.flag, v)"/>
          </template>
        </Column>
        <Column header="Changed / accessed">
          <template #body="{node}">
            <span v-if="node.data.flag" class="muted small nowrap">
              {{ timeAgo(node.data.flag.last_changed_ts, now) }} · {{ timeAgo(node.data.flag.last_access_ts, now) }}
            </span>
          </template>
        </Column>
        <Column style="width: 1%">
          <template #body="{node}">
            <Button v-if="node.data.flag" icon="pi pi-trash" text rounded severity="danger" size="small"
                    v-tooltip.left="'Delete flag'" aria-label="Delete flag" @click="deleteFlag(node.data.flag)"/>
          </template>
        </Column>
      </TreeTable>
    </div>
  </div>
</template>

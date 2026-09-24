<script setup>
import {computed} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import DedupPanel from '../components/overview/DedupPanel.vue'
import FetchersPanel from '../components/overview/FetchersPanel.vue'
import CurvePanel from '../components/overview/CurvePanel.vue'
import StatsPanel from '../components/overview/StatsPanel.vue'
import TransfersPanel from '../components/overview/TransfersPanel.vue'
import ScannerPanel from '../components/overview/ScannerPanel.vue'

const TABS = [
  {value: 'scanner', label: 'Block scanner', component: ScannerPanel},
  {value: 'fetchers', label: 'Fetchers', component: FetchersPanel},
  {value: 'dedup', label: 'Tx dedup', component: DedupPanel},
  {value: 'curve', label: 'Curve', component: CurvePanel},
  {value: 'transfers', label: 'RUNE transfers', component: TransfersPanel},
  {value: 'stats', label: 'Users', component: StatsPanel},
]

const route = useRoute()
const router = useRouter()

// the active tab lives in the URL so reloads and links keep it
const tab = computed({
  get: () => TABS.some(t => t.value === route.query.tab) ? route.query.tab : TABS[0].value,
  set: (value) => router.replace({query: {...route.query, tab: value}}),
})
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Overview</h1>
    </div>
    <!-- lazy: only the visible tab is mounted, so only it polls the API -->
    <Tabs v-model:value="tab" lazy scrollable>
      <TabList>
        <Tab v-for="t in TABS" :key="t.value" :value="t.value">{{ t.label }}</Tab>
      </TabList>
      <TabPanels>
        <TabPanel v-for="t in TABS" :key="t.value" :value="t.value">
          <component :is="t.component"/>
        </TabPanel>
      </TabPanels>
    </Tabs>
  </div>
</template>

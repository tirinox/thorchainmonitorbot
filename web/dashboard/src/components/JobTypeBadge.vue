<script setup>
import {computed} from 'vue'
import {jobType} from '../jobTypes.js'

// A job function shown with its emoji and colour; `title` adds the human name next to the function name.
const props = defineProps({
  func: {type: String, required: true},
  title: {type: Boolean, default: false},
  size: {type: String, default: 'normal'},  // normal | small
})
const info = computed(() => jobType(props.func))
</script>

<template>
  <span class="jt" :class="[`jt-${size}`, {unknown: !info.known}]" :style="{'--jt': info.color}"
        v-tooltip.top="info.known ? info.title : 'Unknown job type (removed from the bot?)'">
    <span class="jt-emoji" aria-hidden="true">{{ info.emoji }}</span>
    <span class="jt-name">{{ func }}</span>
    <span v-if="title && info.known" class="jt-title">{{ info.title }}</span>
  </span>
</template>

<style scoped>
.jt {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  max-width: 100%;
  padding: .12rem .5rem .12rem .4rem;
  border-radius: 6px;
  border-left: 3px solid var(--jt);
  background: color-mix(in srgb, var(--jt) 15%, transparent);
  font-weight: 600;
  line-height: 1.35;
}

.jt-small {
  font-size: .8rem;
  padding: .05rem .4rem .05rem .3rem;
  gap: .25rem;
}

.jt-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.jt-title {
  font-weight: 400;
  color: var(--app-muted);
}

.jt.unknown {
  border-left-style: dashed;
}
</style>

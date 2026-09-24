<script setup>
defineProps({
  updatedAt: {type: Date, default: null},
  error: {type: Object, default: null},
  loading: {type: Boolean, default: false},
})
</script>

<template>
  <div class="row">
    <Message v-if="error" severity="error" size="small" :closable="false">
      {{ error.message || error }}
    </Message>
    <span v-if="updatedAt" class="updated">
      <i class="pi pi-sync" :class="{'pi-spin': loading}" style="font-size: .75rem"/>
      {{ updatedAt.toLocaleTimeString() }}
    </span>
  </div>
</template>

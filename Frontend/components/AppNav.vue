<template>
 <view class="bottom-nav">
  <button hover-class="none" v-for="item in items" :key="item.key" :aria-label="item.label" :aria-current="active === item.key ? 'page' : undefined" :class="{ active: active === item.key }" :disabled="disabled" @click="$emit('change', item.key)">
   <image class="nav-icon" :src="'/static/nav-' + item.icon + '.svg'" />
   <text>{{ item.label }}</text>
  </button>
 </view>
</template>
<script setup>
import { computed } from 'vue';
const props = defineProps({ active: String, project: Boolean, disabled: Boolean });
defineEmits(['change']);
const items = computed(() => [
 { key: 'home', label: props.project ? '记工' : '首页', icon: props.project ? 'work' : 'home' },
 { key: 'ledger', label: '账本', icon: 'ledger' },
 { key: 'check', label: '核账', icon: 'check' },
 { key: 'files', label: '档案', icon: 'files' },
]);
</script>
<style scoped>.bottom-nav button{touch-action:manipulation}</style>

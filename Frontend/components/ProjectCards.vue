<template>
 <view class="project-cards">
  <view v-for="project in projects" :key="project.id" class="project-card-item">
   <button hover-class="none" class="project-card" :disabled="disabled" :aria-label="actionLabel + ' ' + project.name" @click="$emit('open', project)">
    <view class="project-card-copy"><text class="project-card-name">{{ project.name }}</text><text class="muted">{{ project.boss || '未填写老板称呼' }}</text></view>
    <view class="project-card-action"><text>{{ actionLabel }}</text><image src="/static/chevron-right.svg" /></view>
   </button>
   <button hover-class="none" class="project-delete" :disabled="disabled" :aria-label="'删除项目 '+project.name" @click.stop="$emit('delete',project)"><image src="/static/trash.svg" /></button>
  </view>
  <view v-if="!projects.length" class="empty"><text class="section-title">还没有项目</text><text class="muted">先创建一个项目，再开始记工、核账和整理务工档案。</text></view>
 </view>
</template>
<script setup>
import { computed } from 'vue';
const props = defineProps({ projects: { type: Array, default: () => [] }, section: String,disabled:Boolean });
defineEmits(['open','delete']);
const actionLabel = computed(() => ({ home: '进入项目', ledger: '查看账本', check: '去核账', files: '查看档案' }[props.section] || '进入项目'));
</script>
<style scoped>
.project-card-item{display:flex;align-items:center;gap:2px;margin:18px 0;padding-right:6px;background:#f5f0e5;border-radius:14px}
.project-card { --button-background:#f5f0e5; --button-color:#17232c; flex:1; min-width:0; display:flex; align-items:center; justify-content:space-between; gap:12px; text-align:left; background:#f5f0e5; border-radius:14px; margin:0; padding:24px 18px; min-height:112px; line-height:1.5; }
.project-delete{--button-color:#a32c1c;display:flex;align-items:center;justify-content:center;flex:none;width:44px;height:44px;min-height:44px;margin:0;padding:10px;background:transparent;color:#a32c1c;border-radius:10px;line-height:1.5}
.project-delete image{width:22px;height:22px}
.project-card-copy { min-width:0; flex:1; display:flex; flex-direction:column; gap:8px; }
.project-card-name { font-size:22px; line-height:1.4; font-weight:700; overflow-wrap:anywhere; }
.project-card-action { display:flex; align-items:center; gap:6px; flex-shrink:0; color:#117c0d; font-size:15px; font-weight:650; }
.project-card-action image { width:18px; height:22px; }
@media(max-width:360px){.project-card{padding:20px 15px;gap:8px}.project-card-name{font-size:20px}.project-card-action{font-size:14px}}
</style>

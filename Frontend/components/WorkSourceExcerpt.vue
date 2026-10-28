<template>
 <view class="work-source-excerpt">
  <text class="source-excerpt-title">记工重点原话</text>
  <template v-if="excerpt?.has_source">
   <view class="source-keywords"><text v-for="keyword in excerpt.keywords" :key="keyword" class="source-keyword">{{ keyword }}</text></view>
   <view v-for="(fragment,index) in excerpt.fragments" :key="index" class="source-fragment"><text>“</text><text v-for="(part,partIndex) in fragment.parts" :key="partIndex" :class="{ 'source-important':part.important }">{{ part.text }}</text><text>”</text></view>
   <text v-if="excerpt.shortened" class="muted source-excerpt-note">已选取重点片段，完整内容可查看原话。</text>
   <view v-for="change in excerpt.corrections" :key="change.number" class="source-correction"><text class="muted block">第{{ change.number }}次纠正精选</text><view v-for="(fragment,index) in change.fragments" :key="index" class="source-fragment"><text>“</text><text v-for="(part,partIndex) in fragment.parts" :key="partIndex" :class="{ 'source-important':part.important }">{{ part.text }}</text><text>”</text></view></view>
   <text class="muted block source-excerpt-note">{{ excerpt.notice }}{{ excerpt.corrections_shortened?'精选仅显示最近3次纠正。':'' }}</text>
  </template>
  <text v-else class="muted block">这笔没有可选摘的原话，可直接核对记工表单。</text>
 </view>
</template>
<script setup>
defineProps({excerpt:Object});
</script>
<style scoped>
.work-source-excerpt{background:#f5f0e5;border:1px solid #d2d2ce;border-radius:12px;padding:14px;margin:14px 0;text-align:left;line-height:1.7}
.source-excerpt-title{display:block;font-size:18px;font-weight:650;margin-bottom:8px}
.source-keywords{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 12px}
.source-keyword{padding:2px 8px;background:#e4eadc;color:#246522;border-radius:6px;font-size:14px;line-height:1.6;overflow-wrap:anywhere}
.source-fragment{font-size:16px;white-space:pre-wrap;overflow-wrap:anywhere;margin:7px 0}
.source-important{font-weight:650;color:#117c0d}
.source-correction{border-top:1px solid #dedacf;padding-top:10px;margin-top:12px}
.source-excerpt-note{font-size:14px;line-height:1.7;margin-top:10px}
</style>

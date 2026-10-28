<template>
 <view>
  <view class="balance-card"><text class="section-title">本项目待收</text><text class="balance">¥{{ money(ledger.totals.balance_fen) }}</text><text class="muted">已记工钱 ¥{{ money(ledger.totals.wage_fen) }} · 已收/借支 ¥{{ money(ledger.totals.advance_fen) }}</text></view>
  <view class="recording-card">
   <text class="section-title">说清楚，我来记</text>
   <text class="muted speech-example">今天干1天，一天350元；加班2小时，每小时30元；借支100元。工资已收到的话，也一起说清楚。</text>
   <VoiceInput :disabled="busy" :processing="voiceProgress" :transcript="voiceTranscript" @recorded="$emit('recorded',$event)" @error="$emit('error',$event)" />
   <button hover-class="none" class="outline-button" @click="showText=!showText">打字记工</button>
   <view v-if="showText" class="text-entry"><textarea aria-label="记工描述" v-model="text" placeholder="说清日期、天数、单价、加班和借支，AI会帮你填写。" /><button hover-class="none" class="primary" :disabled="busy" :loading="loading==='work'" @click="$emit('text',text)">{{ loading==='work'?'正在整理记工…':'AI整理记工' }}</button><button hover-class="none" class="text-button" @click="$emit('manual')">手动填写</button></view>
  </view>
  <view class="section-heading"><text class="section-title">最近记录</text><button hover-class="none" class="text-button" @click="$emit('ledger')">查看全部</button></view>
  <view v-for="entry in ledger.entries.slice(-3).reverse()" :key="entry.id" class="record-card"><view class="record-row"><view><text>点工 {{ entry.fields.days }} 天</text><text class="muted block">{{ entry.date }}</text></view><text class="amount">¥{{ money(entry.wage_fen) }}</text></view><view v-if="entry.source_excerpt?.has_source || entry.source_text" class="record-actions"><button hover-class="none" class="text-button" :disabled="busy" :loading="loading==='source:'+entry.draft_id" @click="$emit('source',entry.draft_id)">{{ loading==='source:'+entry.draft_id?'正在读取原话…':'查看记工重点原话' }}</button></view></view>
  <text v-if="!ledger.entries.length" class="muted block">还没有记工，按住说一句就能开始。</text>
 </view>
</template>
<script setup>
import { ref } from 'vue';
import VoiceInput from './VoiceInput.vue';
import { money } from '../services/api';
defineProps({ ledger: Object, busy: Boolean, loading:String, voiceProgress:String, voiceTranscript:String });
defineEmits(['text','recorded','error','manual','ledger','source']);
const showText=ref(false),text=ref('');
</script>
<style scoped>
.recording-card{background:#f5f0e5;border:1px solid #dedacf;border-radius:14px;padding:20px 16px;text-align:center;margin-top:18px}
.speech-example{display:block;margin:12px 0 2px;font-size:16px;line-height:1.7}
.outline-button{--button-background:#f7f5ec;--button-color:#117c0d;width:100%;border:1px solid #a5b99b;border-radius:10px;color:#117c0d;background:#f7f5ec;padding:8px 12px;min-height:44px;margin:14px 0 0;font-size:17px;line-height:1.5;font-weight:600}
.text-entry{text-align:left;margin-top:18px}
.text-entry textarea{background:#f5f0e5;padding:12px;border-radius:10px;min-height:130px}
</style>

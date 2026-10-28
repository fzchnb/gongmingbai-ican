<template>
 <view>
  <view class="section-heading first-heading"><text class="section-title">项目账本</text><button hover-class="none" class="text-button" :disabled="busy" @click="$emit('new')">＋ 记工</button></view>
  <view class="ledger-totals"><text>工钱 ¥{{ money(ledger.totals.wage_fen) }}</text><text class="warning">待收 ¥{{ money(ledger.totals.balance_fen) }}</text></view>
  <view v-for="entry in ledger.entries.slice().reverse()" :key="entry.id" class="record-card"><button hover-class="none" class="record-row entry-button" :disabled="busy" @click="$emit('edit',entry)"><view><text>{{ entry.date }}</text><text class="muted block">{{ entry.fields.days }}天 · 加班{{ entry.fields.overtime_hours }}小时 · 修改</text></view><text class="amount">¥{{ money(entry.wage_fen) }}</text></button><view v-if="entry.source_text || entry.revision_history?.length" class="record-actions"><button hover-class="none" class="text-button" :disabled="busy" :loading="loading==='source:'+entry.draft_id" @click="$emit('source',entry.draft_id)">{{ loading==='source:'+entry.draft_id?'正在读取原话…':'查看记工原话' }}</button></view></view>
  <text v-if="!ledger.entries.length" class="muted block empty">这个项目还没有记工。</text>
  <view v-for="pay in ledger.payments.slice().reverse()" :key="pay.id" class="record-row record-card"><text>{{ pay.date }} · {{ pay.type==='advance'?'借支':'已收款' }}</text><text>¥{{ money(pay.amount_fen) }}</text></view>
  <button hover-class="none" class="secondary" :disabled="busy" @click="showPayment=!showPayment">记一笔实际收款</button>
  <view v-if="showPayment" class="panel"><input aria-label="收款金额" v-model="amount" type="digit" placeholder="已确认到账的金额（元）" /><button hover-class="none" class="primary" :disabled="busy" :loading="loading==='payment'" @click="submitPayment">{{ loading==='payment'?'正在保存收款…':'我已核对到账，保存' }}</button></view>
  <button hover-class="none" class="primary" :disabled="busy" :loading="loading==='statement'" @click="$emit('statement')">{{ loading==='statement'?'正在生成…':'生成微信对账内容' }}</button>
  <StatementImage :project="project" :totals="ledger.totals" :busy="busy" />
 </view>
</template>
<script setup>
import { ref,watch } from 'vue';
import StatementImage from './StatementImage.vue';
import { money,requestId } from '../services/api';
const props=defineProps({ project:Object,ledger:Object,busy:Boolean,loading:String });
const emit=defineEmits(['new','edit','payment','statement','source']);
const showPayment=ref(false),amount=ref('');
let paymentRequest;
watch(()=>props.ledger.payments,()=>{showPayment.value=false;amount.value='';paymentRequest=null;});
function submitPayment(){paymentRequest ||= requestId();emit('payment',{amount:amount.value,request_id:paymentRequest});}
</script>
<style scoped>
.first-heading{margin-top:0}.ledger-totals{display:flex;justify-content:space-between;gap:12px;padding:16px 0;font-weight:650;font-size:19px}
.entry-button{width:100%;background:transparent;text-align:left;border-radius:0;margin:0;line-height:1.5}
</style>

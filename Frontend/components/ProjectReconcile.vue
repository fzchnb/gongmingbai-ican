<template>
 <view>
  <text class="section-title">微信核账</text><text v-if="report?.status!=='awaiting_receipt'" class="muted intro">我会结合这个项目的账本和之前的核对记录，帮你接着核账。</text>
  <button v-if="report?.status!=='awaiting_receipt'" hover-class="none" class="primary" :disabled="busy" :loading="loading==='upload'" @click="$emit('upload')">{{ loading==='upload'?'正在结合账本核账…':'上传微信截图' }}</button>
  <view v-if="chat" class="panel">
   <text class="section-title">先核对截图里的信息</text><text class="muted block">本项目已记工钱 ¥{{ money(totals.wage_fen) }}，待收 ¥{{ money(totals.balance_fen) }}</text>
   <view class="quote">{{ form.excerpt || '未识别到明确消息' }}</view>
   <view v-if="chat.explanation || chat.note" class="notice">{{ chat.explanation || chat.note }}</view>
   <view v-if="chat.payments?.length" class="notice">发现本次付款信息，核对后我会询问你是否真正收到，不会直接写成已收款。</view>
   <view v-for="field in fields" :key="field.key" class="field"><text>{{ field.label }}</text><input :aria-label="field.label" v-model="form[field.key]" :type="field.key==='date'?'text':'digit'" :placeholder="field.key==='date'?'留空核对整个项目':'截图未明确'" /></view>
   <text class="muted block">本次转账金额与累计已收是两回事。日期不明确时请核实；留空按整个项目核账。</text>
   <button hover-class="none" class="primary" :disabled="busy" :loading="loading==='report'" @click="$emit('report',{...form})">{{ loading==='report'?'正在整理核对结果…':'信息核对好了，继续' }}</button>
   <button hover-class="none" class="text-button" :disabled="busy" @click="$emit('cancel')">取消这次核账</button>
  </view>
  <view v-if="report" class="report">
   <text class="section-title">{{ report.status==='awaiting_receipt'?'还差一步：确认到账':'这次核账已整理好' }}</text><view class="notice">{{ report.summary || '核对结果已保存' }}</view>
   <view v-if="report.context_changed" class="notice">核账期间账本有更新，本次已按最新账本重新计算。</view>
   <view v-for="receipt in (report.receipts || []).filter(value=>value.status==='pending')" :key="receipt.id" class="panel receipt-card">
    <template v-if="receipt.status==='pending'">
     <text class="section-title">{{ receipt.kind==='promise'?'这笔款现在收到了吗？':'这笔钱实际到账了吗？' }}</text><text class="quote block">{{ receipt.evidence || '截图中提到了付款，请你核实。' }}</text>
     <view class="field"><text>本次金额（元）</text><input :aria-label="'收款金额 '+receipt.id" type="digit" v-model="receiptForms[receipt.id].amount" /></view>
     <view class="field"><text>到账日期</text><input :aria-label="'到账日期 '+receipt.id" v-model="receiptForms[receipt.id].date" placeholder="YYYY-MM-DD，请核对" /></view>
     <text class="muted block receipt-date-hint">{{ receipt.date_hint || (receipt.date?'已按截图识别日期预填，请核对实际到账日期。':'截图未确定到账日期，请填写实际收到的日期。') }}</text>
     <button hover-class="none" class="primary" :disabled="busy" :loading="loading==='receipt:'+receipt.id" @click="$emit('receipt',{id:receipt.id,received:true,amount:receiptForms[receipt.id].amount,date:receiptForms[receipt.id].date})">{{ loading==='receipt:'+receipt.id?'正在核对保存…':'我确认已到账，记入账本' }}</button>
     <button hover-class="none" class="secondary" :disabled="busy" @click="$emit('receipt',{id:receipt.id,received:false})">还没收到，先不记收款</button><text class="muted block">也可以先离开，账本会保留待确认提醒。</text>
    </template>
   </view>
   <view class="panel current-ledger" aria-label="当前项目账本"><text class="section-title">当前项目账本</text><view class="current-row current-balance"><text>{{ totals.balance_fen===0?'已结清':totals.balance_fen<0?'账面多收':'当前待收' }}</text><text>¥{{ money(Math.abs(totals.balance_fen || 0)) }}</text></view><view class="current-row"><text>累计工钱</text><text>¥{{ money(totals.wage_fen) }}</text></view><view class="current-row"><text>已收/借支</text><text>¥{{ money(totals.advance_fen) }}</text></view></view>
   <view v-for="receipt in (report.receipts || []).filter(value=>value.status!=='pending')" :key="receipt.id" class="panel receipt-card"><text class="muted block">¥{{ money(receipt.amount_fen) }} · {{ receipt.status==='confirmed'?'你已确认到账，已记入账本':receipt.status==='already_recorded'?'这笔已在账本中，未重复记账':'你已确认尚未收到，未记收款' }}</text></view>
   <button hover-class="none" class="text-button" :aria-expanded="historyOpen" @click="historyOpen=!historyOpen">{{ historyOpen?'收起历史核对明细':'查看历史核对明细' }}</button>
   <view v-if="historyOpen" class="historical-comparison"><text class="muted block">以下是本次核账前的历史快照，不代表当前欠款。</text><view class="comparison"><view class="compare-row muted"><text>项目</text><text>核账前账本</text><text>截图提及</text></view><view v-for="row in report.rows" :key="row.label" class="compare-row"><text>{{ row.label }}</text><text>¥{{ money(row.mine_fen) }}</text><text>{{ row.chat_fen==null?'待核实':'¥'+money(row.chat_fen) }}</text></view></view><view v-for="row in report.rows.filter(row=>row.difference_fen)" :key="row.label" class="notice">核账前{{ row.label }}相差 ¥{{ money(Math.abs(row.difference_fen)) }}</view><text class="muted block">历史核账范围：{{ report.scope_date || '整个项目' }}</text></view>
   <button hover-class="none" class="primary" :disabled="busy" :loading="loading==='message'" @click="$emit('copy')">{{ loading==='message'?'正在整理跟进话术…':messageAction }}</button>
   <StatementImage :project="project" :totals="totals" :busy="busy" />
   <button hover-class="none" class="secondary" :disabled="busy" :loading="loading==='asset:'+report.asset_id" @click="$emit('view',report.asset_id)">{{ loading==='asset:'+report.asset_id?'正在打开截图…':'查看这次截图' }}</button>
  </view>
  <view v-if="message" class="panel"><text class="section-title">发给老板前再看看</text><textarea aria-label="微信核对话术" class="message-editor" :auto-height="true" v-model="messageText" /><button hover-class="none" class="primary" @click="copyMessage">复制这段话</button></view>
 </view>
</template>
<script setup>
import { reactive,watch,ref,computed } from 'vue';
import { money } from '../services/api';
import StatementImage from './StatementImage.vue';
import { syncReceiptForms } from '../services/receiptForms.mjs';
const props=defineProps({chat:Object,report:Object,busy:Boolean,loading:String,project:Object,totals:{type:Object,default:()=>({})},message:String});
defineEmits(['upload','report','copy','view','receipt','cancel']);
const form=reactive({}),receiptForms=reactive({}),messageText=ref(''),historyOpen=ref(false);
const messageAction=computed(()=>props.report?.receipts?.some(r=>r.status==='pending')?'生成到账跟进话术':props.totals.balance_fen>0?'帮我写催款跟进话术':props.totals.balance_fen===0?'生成结清回复':'生成金额核实回复');
watch(()=>props.chat,value=>{for(const key of Object.keys(form))delete form[key];for(const k of ['date','wage','advance','balance','excerpt'])form[k]=value?.[k]==null?'':String(value[k]);},{immediate:true});
let receiptReportId;
watch(()=>props.report,value=>{
 if(receiptReportId!==value?.id){for(const key of Object.keys(receiptForms))delete receiptForms[key];receiptReportId=value?.id;}
 syncReceiptForms(receiptForms,value?.receipts);
},{immediate:true,deep:true});
watch(()=>[props.report?.id,props.report?.status].join(':'),()=>{historyOpen.value=props.report?.status==='awaiting_receipt';},{immediate:true});
watch(()=>props.message,value=>{messageText.value=value||'';},{immediate:true});
function copyMessage(){uni.setClipboardData({data:messageText.value});}
const fields=[{key:'wage',label:'截图累计工钱（元）'},{key:'advance',label:'截图累计已收（元）'},{key:'balance',label:'截图待付（元）'},{key:'date',label:'账目核对日期'}];
</script>
<style scoped>.receipt-card{border:1px solid #d5dfca}.current-row{display:flex;justify-content:space-between;gap:16px;margin:12px 0}.current-balance{font-size:20px;font-weight:650;padding-top:12px;border-top:1px solid #d5dfca}.historical-comparison{margin:12px 0 20px}.message-editor{min-height:160px;margin:14px 0;line-height:1.8;white-space:pre-wrap}</style>

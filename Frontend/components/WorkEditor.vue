<template>
 <view class="work-review">
  <text class="page-title">{{ savedEntry?'修改这笔记工':'确认这笔记工' }}</text>
  <text class="muted review-message">{{ assistantMessage || (savedEntry?'核对后确认修改，原记录和历史会保留。':'已整理好，核对后就能保存。') }}</text>
  <WorkSourceExcerpt v-if="sourceExcerpt" :excerpt="sourceExcerpt" /><button v-if="source && sourceExcerpt" hover-class="none" class="text-button" @click="showOriginal=!showOriginal">{{ showOriginal?'收起完整原话':'查看完整原话' }}</button><view v-if="source && (!sourceExcerpt || showOriginal)" class="quote">{{ source }}</view>
  <view v-if="preview && !preview.missing.length && !previewLoading" class="balance-card review-balance"><text class="section-title">{{ preview.balance_fen===0?'本笔已结清':'本次待收' }}</text><text class="balance">¥{{ money(preview.balance_fen) }}</text><text class="muted">工钱 ¥{{ money(preview.wage_fen) }} · 借支 ¥{{ money(preview.advance_fen) }} · 已收工资 ¥{{ money(preview.received_fen || 0) }}</text></view>
  <view v-else class="notice">{{ previewLoading?'正在核算金额…':preview?.missing?.length?'请再告诉我：'+preview.missing.join('、'):previewError || '请补充日期、天数和单价。' }}</view>
  <view class="correction-panel">
   <text class="section-title correction-title">有哪里不对？告诉我</text>
   <textarea aria-label="修改要求" v-model="instruction" :disabled="busy" :maxlength="2000" :cursor-spacing="120" placeholder="例如：借支不是100，是80；备注加上今天做了吊顶" class="correction-input" />
   <view class="correction-actions"><VoiceInput compact :disabled="busy || !allowAgent" :processing="voiceProgress" @recorded="voiceRevision" @error="$emit('error',$event)" /><button hover-class="none" class="primary" :disabled="busy || !allowAgent || !instruction.trim()"  :loading="loading==='revise'" @click="textRevision">{{ loading==='revise'?'正在修改…':'让AI修改' }}</button></view>
   <view v-if="voiceProgress && voiceTranscript" class="quote" role="status"><text class="muted block">刚才的修改要求</text><text>{{ voiceTranscript }}</text></view>
   <text v-if="!allowAgent" class="muted agent-unavailable">AI修改暂不可用，可先点击下方“手动修改”。</text>
  </view>
  <view v-if="revisions.length" class="revision-history">
   <view v-for="(turn,index) in revisions.slice(-3)" :key="index" class="revision-turn"><text class="muted block">你：{{ turn.instruction }}</text><text class="agent-reply block">{{ turn.reply }}</text></view>
  </view>
  <view class="review-summary">
   <view class="summary-row"><text>日期</text><text>{{ form.date || '待补充' }}</text></view>
   <view class="summary-row"><text>点工</text><text>{{ form.days || '待补充' }}天 × {{ form.day_rate ? '¥'+form.day_rate : '单价待补充' }}</text></view>
   <view class="summary-row"><text>加班</text><text>{{ form.overtime_hours || '0' }}小时<text v-if="Number(form.overtime_hours)"> × {{ form.overtime_rate ? '¥'+form.overtime_rate : '单价待补充' }}</text></text></view>
   <view class="summary-row"><text>本笔已收工资</text><text>¥{{ money(preview?.received_fen || 0) }}</text></view>
   <button hover-class="none" class="secondary settlement-toggle" :disabled="busy" :aria-pressed="form.settled" @click="form.settled=!form.settled">{{ form.settled?'✓ 这笔工钱已全部收到':'这笔工钱已经全部收到？点此确认' }}</button>
   <text v-if="form.settled" class="muted block settlement-note">确认保存时会同时记录本笔收款，扣除本笔借支，不冲销其他欠款。</text>
   <text v-if="Number(preview?.received_fen)>0" class="muted block settlement-note">本笔收款日期：{{ form.received_date || form.date || '请补充日期' }}，可在手动修改中调整。</text>
   <view v-if="form.note" class="summary-note muted">{{ form.note }}</view>
   <button hover-class="none" class="text-button summary-edit" :disabled="busy" @click="editing=!editing">{{ editing?'收起手动修改':'手动修改' }}</button>
   <view v-if="editing" class="manual-fields">
    <view v-for="row in rows.filter(row=>!form.settled || row.key!=='received')" :key="row.key" class="field"><text>{{ row.label }}</text><input :aria-label="row.label" v-model="form[row.key]" :disabled="busy" :type="row.key.endsWith('date')?'text':'digit'" :placeholder="row.key==='received_date'?'留空按记工日期':row.key==='date'?'YYYY-MM-DD':'请填写'" /></view>
    <view class="note-field"><text>备注（可选）</text><textarea aria-label="备注" class="note-input" v-model="form.note" :disabled="busy" :maxlength="1000" :auto-height="true" :cursor-spacing="120" placeholder="可填写施工内容、地点或需要说明的情况，支持换行。" /><text class="muted note-count">{{ (form.note || '').length }}/1000</text></view>
   </view>
  </view>
  <view class="confirm-footer"><button hover-class="none" class="primary confirm-work" :disabled="busy || previewLoading || !preview || !!preview.missing.length" :loading="loading==='save'" @click="$emit('save',normalized())">{{ loading==='save'?'正在保存…':savedEntry?'确认修改':'确认保存' }}</button></view>
 </view>
</template>
<script setup>
import { reactive,ref,watch,onUnmounted } from 'vue';
import { api,money } from '../services/api';
import VoiceInput from './VoiceInput.vue';
import WorkSourceExcerpt from './WorkSourceExcerpt.vue';
const props=defineProps({ fields:Object,source:String,sourceExcerpt:Object,busy:Boolean,loading:String,manual:Boolean,assistantMessage:String,
 revisions:{type:Array,default:()=>[]},revision:{type:Number,default:0},allowAgent:Boolean,savedEntry:Boolean,voiceProgress:String,voiceTranscript:String });
const emit=defineEmits(['save','cancel','revise','error']);
const showOriginal=ref(false);
const form=reactive({}),editing=ref(props.manual),preview=ref(null),previewLoading=ref(false),previewError=ref(''),instruction=ref('');
const rows=[{key:'date',label:'日期'},{key:'days',label:'点工天数'},{key:'day_rate',label:'每天工钱（元）'},{key:'overtime_hours',label:'加班小时'},{key:'overtime_rate',label:'加班每小时（元）'},{key:'advance',label:'已借支（元）'},{key:'received',label:'本笔另已收工资（元，不含借支）'},{key:'received_date',label:'本笔实际收款日期'}];
function normalized(){return {...form,date:form.date||null,days:form.days||null,day_rate:form.day_rate||null,
 overtime_hours:form.overtime_hours||'0',overtime_rate:form.overtime_rate||null,advance:form.advance||'0',received:form.received||'0',settled:form.settled===true,received_date:form.received_date||null};}
watch(()=>props.fields,value=>{
 const defaults={date:'',days:'',day_rate:'',overtime_hours:'0',overtime_rate:'',advance:'0',received:'0',settled:false,received_date:'',note:''};
 Object.assign(form,defaults,Object.fromEntries(Object.entries(value||{}).map(([key,v])=>[key,key==='settled'?v===true:v==null?'':String(v)])));
},{immediate:true});
watch(()=>props.revision,()=>{instruction.value='';editing.value=false;});
let timer,version=0;
watch(()=>[...rows.map(row=>form[row.key]),form.settled],()=>{
 clearTimeout(timer);const current=++version;previewLoading.value=true;previewError.value='';
 timer=setTimeout(async()=>{
  try{const result=await api('/drafts/preview','POST',normalized());if(current===version)preview.value=result;}
  catch(e){if(current===version){preview.value=null;previewError.value=e.message;}}
  finally{if(current===version)previewLoading.value=false;}
 },250);
},{immediate:true});
function textRevision(){emit('revise',{text:instruction.value.trim(),fields:normalized()});}
function voiceRevision(result){emit('revise',{...result,fields:normalized()});}
onUnmounted(()=>{clearTimeout(timer);version++;});
</script>
<style scoped>
.review-message{display:block;margin:8px 0 18px}.review-balance{margin:16px 0}
.review-summary{border:1px solid #e4e9ec;border-radius:12px;padding:0 16px;margin:16px 0 20px}
.summary-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 0;border-bottom:1px solid #edf0f2;font-size:17px;line-height:1.5}
.summary-row>text:last-child{text-align:right;color:#495b6a}.summary-note{padding:12px 0;white-space:pre-wrap;overflow-wrap:anywhere}
.summary-edit.text-button{--button-color:#117c0d;display:flex;margin-left:auto;justify-content:center;width:max-content;color:#117c0d;min-height:42px}
.manual-fields{padding-bottom:10px}.manual-fields .field input{font-size:16px}
.note-field{padding:18px 0 10px}.note-field>text:first-child{display:block;font-size:16px;font-weight:600;margin-bottom:10px}
.note-input{display:block;width:100%;height:auto;min-height:160px;box-sizing:border-box;padding:12px;background:#faf8f1;border:1px solid #d6dfe4;border-radius:10px;font-size:17px;line-height:1.7;text-align:left}
.note-count{display:block;text-align:right;font-size:14px;margin-top:6px}
.correction-title{font-size:20px;margin:14px 0 12px}
.correction-input{display:block;width:100%;height:86px;min-height:86px;box-sizing:border-box;border:1px solid #d6dfe4;border-radius:10px;padding:12px;font-size:16px;line-height:1.6;text-align:left;background:#faf8f1}
.agent-unavailable{display:block;margin:10px 0;font-size:15px}
.correction-actions{display:flex;gap:12px;margin:10px 0 0;align-items:stretch}
.correction-actions>view,.correction-actions>button{flex:1;min-width:0}
.correction-actions .primary{margin:0;padding:10px;min-height:48px;font-size:16px;line-height:1.5}
.confirm-footer{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:100%;max-width:520px;padding:12px 20px calc(12px + env(safe-area-inset-bottom));background:#f1ece0;border-top:1px solid #dedacf;z-index:25}
.confirm-work{margin:0}
.revision-turn{background:#f8f5ed;border-left:3px solid #b3c3a7;padding:12px;margin:10px 0}
.agent-reply{margin-top:6px;font-size:16px;line-height:1.6;color:#276322}
.settlement-toggle{margin:14px 0 8px}.settlement-note{margin:8px 0 12px;line-height:1.6}
</style>

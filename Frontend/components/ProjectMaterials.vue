<template>
 <view>
  <text class="section-title">务工证据时间线</text>
  <text class="muted intro">按时间查看记工、收款和已归档的核账凭据。</text>
  <view v-for="event in events" :key="event.id" class="timeline-item"><text class="muted">{{ chinaTime(event.created_at) }}</text><text class="event-title">{{ event.title }}</text><text v-if="event.summary" class="muted block">{{ event.summary }}</text><button v-if="workDraftId(event)" hover-class="none" class="text-button work-source-link" :disabled="busy" :loading="loading==='source:'+workDraftId(event)" @click="$emit('source',workDraftId(event))">{{ loading==='source:'+workDraftId(event)?'正在读取原话…':'查看记工原话' }}</button><button v-if="event.report_id" hover-class="none" class="text-button" :disabled="busy" :loading="loading==='report:'+event.report_id" @click="$emit('report',event.report_id)">{{ loading==='report:'+event.report_id?'正在读取核账…':'查看这次核账' }}</button><button hover-class="none" v-if="event.asset_id" class="text-button" :disabled="busy" :loading="loading==='asset:'+event.asset_id" @click="$emit('view',event.asset_id)">{{ loading==='asset:'+event.asset_id?'正在打开原件…':playing===event.asset_id?'停止播放录音':'查看 / 播放原件' }}</button></view>
  <text v-if="!events.length" class="muted empty block">记工或完成核账后，这里会自动整理证据时间线。</text>
  <text class="muted intro">给AI记工、纠正时说的语音不作为证据归档。</text>
  <view class="archive-export">
   <button hover-class="none" class="primary" :disabled="busy" :loading="loading==='export'" @click="$emit('export','pdf')">{{ loading==='export'?'正在生成PDF档案…':'导出PDF档案' }}</button>
   <text class="muted block">包含账本、收款、证据时间线和已归档截图，方便查看、转发和打印。</text>
   <view v-if="archive" class="panel archive-result" role="status" aria-live="polite">
    <text class="archive-name">{{ archive.filename }}</text>
    <text class="muted block">{{ chinaTime(archive.created_at) }}生成</text>
    <text class="archive-feedback">{{ archive.feedback }}</text>
    <view class="archive-actions"><button hover-class="none" class="secondary" :disabled="busy" @click="$emit('open')">{{ archive.format==='pdf'?'打开PDF':'打开文件' }}</button><button hover-class="none" class="primary" :disabled="busy" :loading="loading==='save_archive'" @click="$emit('save')">{{ loading==='save_archive'?'正在保存…':'保存到手机 / 设备' }}</button></view>
   </view>
   <button hover-class="none" class="text-button backup-toggle" :disabled="busy" @click="backup=!backup">{{ backup?'收起原始文件备份':'需要原始文件？' }}</button>
   <view v-if="backup" class="backup-detail"><text class="muted block">ZIP保留原始凭据、账本和核账数据；PDF中的图片为便于阅读的排版版本。</text><button hover-class="none" class="secondary" :disabled="busy" :loading="loading==='export_zip'" @click="$emit('export','zip')">{{ loading==='export_zip'?'正在打包原始文件…':'导出原始凭据ZIP' }}</button></view>
  </view>
 </view>
</template>
<script setup>
import { ref } from 'vue';
import { chinaTime } from '../services/display.mjs';
defineProps({ events:{type:Array,default:()=>[]},busy:Boolean,loading:String,playing:String,archive:Object });
defineEmits(['view','export','report','open','save','source']);
const backup=ref(false);
function workDraftId(event){
 const value=event.draft_id||event.after?.draft_id||event.before?.draft_id;
 return typeof value==='string'?value:'';
}
</script>
<style scoped>
.timeline-item .text-button{display:flex;width:max-content;max-width:100%;margin-top:8px}
.archive-export{margin:28px 0 0;padding-top:16px;border-top:1px solid #d2d2ce}
.archive-name{display:block;font-size:17px;font-weight:650;overflow-wrap:anywhere;line-height:1.6}
.archive-feedback{display:block;margin:12px 0;line-height:1.7;font-size:16px;overflow-wrap:anywhere}
.archive-actions{display:flex;flex-wrap:wrap;gap:8px}
.archive-actions button{flex:1 1 130px;font-size:16px;margin:0;padding:12px 10px;min-height:48px}
.backup-toggle{margin-top:8px}
.backup-detail{padding:12px 0 0}
</style>

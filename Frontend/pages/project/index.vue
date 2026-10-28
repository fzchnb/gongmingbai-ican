<template>
 <view class="app-shell project-shell">
  <button hover-class="none" class="back-button" :disabled="!!busy" @click="back"><image src="/static/chevron-right.svg" /><text>{{ draft?'记工':'全部项目' }}</text></button>
  <view v-if="error" class="error" role="alert">{{ error }}<button hover-class="none" class="text-button" @click="error=''">收起</button></view>
  <view v-if="busy && !operation && (!project || draft)" class="processing">{{ busy }}</view>
  <view v-if="playing" class="panel" role="status"><text>正在播放原始录音</text><button hover-class="none" class="text-button" @click="stopAudio">停止播放</button></view>
  <view v-if="source" class="sheet-mask" @click="source=null"><view class="sheet" @click.stop><text class="section-title">记工原话</text><scroll-view scroll-y style="max-height:65vh"><WorkSourceExcerpt v-if="source.excerpt" :excerpt="source.excerpt" /><button hover-class="none" class="text-button" @click="sourceFull=!sourceFull">{{ sourceFull?'收起完整原话':'查看完整原话与纠正记录' }}</button><template v-if="sourceFull || !source.excerpt"><text class="quote block source-text">{{ source.text || '这笔记工由手动填写，没有原始语音或文字。' }}</text><view v-for="(change,index) in source.corrections" :key="index"><text class="section-title">第{{ index+1 }}次纠正</text><text class="quote block source-text">{{ change.instruction }}</text><text class="muted block">{{ change.reply }}</text></view></template></scroll-view><button hover-class="none" class="secondary" @click="source=null">关闭</button></view></view>
  <view v-if="failedTask" class="notice">这次处理没有完成，输入内容已保留。<button hover-class="none" class="secondary" :disabled="!!busy" @click="retryTask">重试这次处理</button><button hover-class="none" class="text-button" :disabled="!!busy" @click="dismissTask">取消本次处理</button></view>
  <button hover-class="none" v-else-if="pendingId && !busy && task?.status!=='completed'" class="secondary" @click="continueTask">继续查看处理结果</button>
  <template v-if="project">
   <WorkEditor v-if="draft" :key="draft.id || 'manual'" :fields="draft.fields" :source="draft.source_text" :source-excerpt="draft.source_excerpt" :busy="blocked" :manual="!draft.id || !!draft.editing || !!draft.source_entry_id" :loading="operation" :voice-progress="voiceProgress('revise')" :voice-transcript="task?.status==='running'?task.transcript:''" :saved-entry="!!draft.editing || !!draft.source_entry_id" :revisions="draft.revisions || []" :revision="draft.revision || 0" :assistant-message="draft.assistant_message" :allow-agent="draft.editing || draft.source_entry_id ? entryAgentEnabled : agentEnabled" @save="saveWork" @cancel="dismissDraft" @revise="reviseDraft" @error="error=$event" />
   <template v-else>
    <view class="project-heading">
     <text class="page-title">{{ project.name }}</text>
     <view class="project-meta"><text class="muted">{{ project.boss }}</text><view v-if="busy || syncing" class="sync-status" role="status" aria-live="polite"><view class="sync-spinner" aria-hidden="true" /><text>{{ busy || '正在同步最新账本…' }}</text></view></view>
     <view v-if="syncError && !busy && !syncing" class="sync-error" role="status"><text>同步未完成，当前显示上次记录。{{ syncError }}</text><button hover-class="none" class="text-button" @click="syncProject">重试同步</button></view>
    </view>
    <view v-for="pendingReport in workspace.pending_reports.filter(value=>section!=='check'||value.id!==report?.id)" :key="pendingReport.id" class="notice"><text>截图里有款项等待确认是否到账，账本暂时没有增加这笔收款。</text><button hover-class="none" class="text-button" :disabled="blocked" @click="resumeReport(pendingReport)">继续确认到账</button></view>
    <button hover-class="none" v-if="workspace.active_task && section!=='check'" class="secondary" :disabled="blocked" @click="resumeTask">继续上次核账</button>
    <ProjectOverview v-if="section==='home'" :ledger="ledger" :busy="blocked" :loading="operation" :voice-progress="voiceProgress('work')" :voice-transcript="task?.status==='running'?task.transcript:''" @text="startText" @recorded="recorded" @error="error=$event" @manual="newDraft" @ledger="changeTab('ledger')" @source="viewSource" />
    <ProjectLedger v-if="section==='ledger'" :project="project" :ledger="ledger" :busy="blocked" :loading="operation" @new="newDraft" @edit="editEntry" @payment="savePayment" @statement="copyStatement" @source="viewSource" />
    <ProjectReconcile v-if="section==='check'" :project="project" :totals="ledger.totals" :message="wechatMessage" @receipt="decideReceipt" @cancel="cancelReconcile" :chat="chat" :report="report" :busy="blocked" :loading="operation" @upload="chooseScreenshot" @report="makeReport" @copy="copyReport" @view="viewAsset" />
    <ProjectMaterials @source="viewSource" :archive="exported" @open="openArchive" @save="saveArchive" @report="openReport" v-if="section==='files'" :events="events" :busy="blocked" :loading="operation" :playing="playing" @view="viewAsset" @export="exportProject" />
    <AppNav project :active="section" @change="changeTab" />
   </template>
  </template>
 </view>
</template>
<script setup>
import { ref,computed,watch,nextTick,onUnmounted } from 'vue';
import { onLoad,onUnload,onHide,onShow,onBackPress } from '@dcloudio/uni-app';
import AppNav from '../../components/AppNav.vue';
import WorkEditor from '../../components/WorkEditor.vue';
import WorkSourceExcerpt from '../../components/WorkSourceExcerpt.vue';
import ProjectOverview from '../../components/ProjectOverview.vue';
import ProjectLedger from '../../components/ProjectLedger.vue';
import ProjectReconcile from '../../components/ProjectReconcile.vue';
import ProjectMaterials from '../../components/ProjectMaterials.vue';
import { api,serviceHealth,currentSession,requestId,upload,download } from '../../services/api';
import { cancelRecording } from '../../services/recorder';
import { createPlayer } from '../../services/player.mjs';
import { archiveFilename,keepDocument,saveAndroidDocument,openDocument,archiveStorageKey } from '../../services/documents.mjs';
const workspace=ref({pending_reports:[],latest_report:null,active_task:null}),workflowEnabled=ref(false),settlementEnabled=ref(false),wechatMessage=ref('');
const exported=ref(null),pdfEnabled=ref(false);
const sourceFull=ref(false);
const operation=ref(''),source=ref(null),sourceEnabled=ref(false),playing=ref(''),player=createPlayer();
function stopAudio(){player.stop();playing.value='';}
const project=ref(null),ledger=ref({totals:{},entries:[],payments:[]}),events=ref([]),section=ref('home');
const busy=ref(''),syncing=ref(false),syncError=ref(''),error=ref(''),draft=ref(null),chat=ref(null),report=ref(null),task=ref(null),failedTask=ref(null),pendingId=ref(''),agentEnabled=ref(false),entryAgentEnabled=ref(false);
const blocked=computed(()=>!!busy.value || (!!pendingId.value && task.value?.status!=='completed'));
let projectId='',alive=true,lastRequest,refreshSequence=0,backgroundSync=null;
watch(()=>draft.value ? (draft.value.id || 'manual')+':'+(draft.value.revision || 0) : '',async value=>{
 if(value){await nextTick();if(alive)uni.pageScrollTo({scrollTop:0,duration:0});}
});
const today=()=>new Date(Date.now()+8*3600000).toISOString().slice(0,10);
async function action(label,fn,key=''){
 if(busy.value)return;
 busy.value=label;operation.value=key;error.value='';
 try{await fn();}catch(e){if(alive&&e.code!=='MEDIA_CANCELLED')error.value=e.message;}finally{if(alive){busy.value='';operation.value='';}}
}
async function refresh(){
 const sequence=++refreshSequence;
 let values;
 try{values=await Promise.all([api('/projects/'+projectId+'/ledger'),api('/projects/'+projectId+'/timeline'),workflowEnabled.value?api('/projects/'+projectId+'/workspace'):Promise.resolve(null)]);}
 catch(e){if(alive && sequence===refreshSequence)throw e;return;}
 const [l,e,w]=values;
 if(alive && sequence===refreshSequence){
  syncError.value='';
  if(JSON.stringify([ledger.value.entries,ledger.value.payments])!==JSON.stringify([l.entries,l.payments]))wechatMessage.value='';
  ledger.value=l;events.value=e;
  if(w){workspace.value=w;if(report.value){const fresh=[...w.pending_reports,w.latest_report].find(value=>value?.id===report.value.id);report.value=fresh||{...report.value,totals:l.totals};}}
 }
}
function syncProject(){
 // Navigation uses cached data immediately; only one background read is needed.
 if(!alive || !project.value || busy.value)return;
 if(backgroundSync)return backgroundSync;
 syncing.value=true;syncError.value='';
 const sequence=refreshSequence+1;
 backgroundSync=refresh().catch(e=>{if(alive && sequence===refreshSequence)syncError.value=e.message;})
  .finally(()=>{backgroundSync=null;if(alive)syncing.value=false;});
 return backgroundSync;
}
function remember(id){
 const values=uni.getStorageSync('pending_tasks')||{};
 if(id)values[projectId]=id;else delete values[projectId];
 uni.setStorageSync('pending_tasks',values);pendingId.value=id||'';
}
async function init(){
 if(!currentSession()){uni.reLaunch({url:'/pages/index/index'});return;}
 restoreArchive();
 const health=await serviceHealth();pdfEnabled.value=health.capabilities?.includes('evidence_pdf')||false;agentEnabled.value=health.capabilities?.includes('draft_revision')||false;
 entryAgentEnabled.value=health.capabilities?.includes('entry_revision')||false;
 sourceEnabled.value=health.capabilities?.includes('material_sources')||false;
 workflowEnabled.value=health.capabilities?.includes('project_agent_workflow')||false;
 settlementEnabled.value=health.capabilities?.includes('work_settlement')||false;
 const projects=await api('/projects');
 project.value=projects.find(p=>p.id===projectId)||null;
 if(!project.value)throw new Error('这个项目不存在或无权访问，请返回项目列表。');
 await refresh();
 report.value=workspace.value.pending_reports[0]||workspace.value.latest_report;
 let pending=(uni.getStorageSync('pending_tasks')||{})[projectId];
 const legacy=uni.getStorageSync('pending_task');
 if(!pending&&legacy){
  try{const previous=await api('/tasks/'+legacy);if(previous.project_id===projectId){pending=legacy;remember(pending);uni.removeStorageSync('pending_task');}}catch{}
 }
 if(!pending&&section.value==='check'&&workspace.value.active_task)pending=workspace.value.active_task.id;
 if(pending){pendingId.value=pending;await poll(pending);}
}
onLoad(query=>{
 projectId=String(query.id||'');
 section.value=['home','ledger','check','files'].includes(query.section)?query.section:'home';
 action('正在读取项目…',init);
});
onUnload(()=>{alive=false;cancelRecording();stopAudio();releaseArchive();});
onHide(()=>{cancelRecording();stopAudio();});
onShow(syncProject);
function expired(){uni.reLaunch({url:'/pages/index/index'});}
uni.$on('session-expired',expired);onUnmounted(()=>uni.$off('session-expired',expired));
onBackPress(()=>{if(draft.value&&!busy.value){dismissDraft();return true;}return false;});
function back(){
 if(draft.value){dismissDraft();return;}
 if(getCurrentPages().length>1)uni.navigateBack();else uni.reLaunch({url:'/pages/index/index'});
}
function changeTab(value){
 if(!['home','ledger','check','files'].includes(value))return;
 if(section.value!==value){section.value=value;nextTick(()=>{if(alive)uni.pageScrollTo({scrollTop:0,duration:0});});}
 syncProject();
}
function resumeReport(value){report.value=value;chat.value=null;wechatMessage.value='';section.value='check';uni.pageScrollTo({scrollTop:0,duration:0});}
function resumeTask(){section.value='check';const id=workspace.value.active_task.id;remember(id);action('正在恢复核账…',()=>poll(id));}
function openReport(id){action('正在读取核账记录…',async()=>{resumeReport(await api('/reports/'+id));},'report:'+id);}
function newDraft(){if(!blocked.value)draft.value={fields:{date:today(),days:'1',overtime_hours:'0',advance:'0'}};}
function voiceProgress(type){
 if(operation.value===type+'_voice')return busy.value;
 if(pendingId.value && task.value?.type===type && task.value.asset_id && !['completed','failed'].includes(task.value.status))return busy.value || '仍在处理，可点击继续查看结果';
 return '';
}
function dismissDraft(){draft.value=null;remember(null);task.value=null;failedTask.value=null;}
function dismissTask(){failedTask.value=null;task.value=null;remember(null);}
async function poll(id){
 for(let i=0;i<120&&alive;i++){
  const value=await api('/tasks/'+id);
  if(value.project_id!==projectId)throw new Error('处理结果所属项目不同');
  if(!alive)return;
  task.value=value;busy.value=value.stage;
  if(value.status==='failed'){failedTask.value=value;throw new Error(value.error||'处理失败，请重试');}
  if(value.status==='completed'){
   failedTask.value=null;
   if(value.type==='work'||value.type==='revise'){
    if(value.result.confirmed){draft.value=null;remember(null);await refresh();}
    else draft.value=value.result;
   }else{
    section.value='check';
    const saved=value.result.existing_report||workspace.value.pending_reports.find(r=>r.asset_id===value.asset_id)||(workspace.value.latest_report?.asset_id===value.asset_id?workspace.value.latest_report:null);
    if(saved){report.value=saved;chat.value=null;remember(null);return;}
    chat.value={...value.result.extracted};wechatMessage.value='';
    report.value=null;
   }
   return;
  }
  await new Promise(resolve=>setTimeout(resolve,1250));
 }
 if(alive)throw new Error('处理尚未完成，请点击“继续查看处理结果”，不必重复提交。');
}
async function launch(type,values){
 const body={project_id:projectId,type,text:'',asset_id:null,...values};
 const signature=JSON.stringify(body);
 if(lastRequest?.signature!==signature)lastRequest={signature,id:requestId()};
 const value=await api('/tasks','POST',{...body,request_id:lastRequest.id});
 lastRequest=null;remember(value.id);task.value=value;
 await poll(value.id);
}
function startText(text){action('正在整理记工…',async()=>{if(!text.trim())throw new Error('请先说说今天的工作');await launch('work',{text});},'work');}
function recorded(result){action('正在上传录音…',async()=>{const asset=await upload(projectId,result.tempFilePath);busy.value='录音已上传，正在提交处理…';await launch('work',{asset_id:asset.id});},'work_voice');}
function reviseDraft(value){action('正在修改草稿…',async()=>{
 const editingEntry=!!draft.value.editing || !!draft.value.source_entry_id;
 if(!(editingEntry?entryAgentEnabled.value:agentEnabled.value))throw new Error('AI修改暂不可用，可先手动修改。');
 if(draft.value.editing){
  draft.value=await api('/drafts','POST',{project_id:projectId,entry_id:draft.value.id,
   expected_entry_version:draft.value.entry_version,fields:value.fields});
 }
 let assetId=null;
 if(value.tempFilePath){busy.value='正在上传修改录音…';const asset=await upload(projectId,value.tempFilePath);assetId=asset.id;busy.value='修改录音已上传，正在提交处理…';}
 if(!assetId&&!value.text?.trim())throw new Error('请告诉我哪里需要修改');
 await launch('revise',{text:value.text||'',asset_id:assetId,draft_id:draft.value.id||null,
  fields:value.fields,expected_revision:draft.value.revision||0});
},value.tempFilePath?'revise_voice':'revise');}
function retryTask(){action('正在重试…',async()=>{await api('/tasks/'+failedTask.value.id+'/retry','POST',{});await poll(failedTask.value.id);});}
function continueTask(){action('正在查看处理结果…',()=>poll(pendingId.value));}
function editEntry(entry){draft.value={fields:entry.fields,id:entry.id,editing:true,
 entry_version:entry.updated_at||entry.created_at,source_text:entry.source_text||'',source_excerpt:entry.source_excerpt,revisions:entry.revision_history||[]};}
function saveWork(fields){action('正在核对保存…',async()=>{
 if((fields.settled||Number(fields.received)>0)&&!settlementEnabled.value)throw new Error('请先更新后端，才能同时保存已结清记工与收款。');
 const body={...fields,day_rate:fields.day_rate||null,overtime_rate:fields.overtime_rate||null,
  days:String(fields.days),overtime_hours:String(fields.overtime_hours||'0'),advance:String(fields.advance||'0')};
 if(draft.value.editing)await api('/entries/'+draft.value.id,'PATCH',{...body,expected_entry_version:draft.value.entry_version});
 else{
  if(!draft.value.id)draft.value=await api('/drafts','POST',{project_id:projectId,fields:body});
  await api('/drafts/'+draft.value.id+'/confirm','POST',{...body,expected_revision:draft.value.revision||0});
 }
 dismissDraft();await refresh();uni.showToast({title:'已核对保存',icon:'success'});
},'save');}
function savePayment(value){action('正在保存收款…',async()=>{await api('/payments','POST',{project_id:projectId,date:today(),...value});await refresh();},'payment');}
function copyStatement(){action('正在生成…',async()=>{const value=await api('/projects/'+projectId+'/statement');uni.setClipboardData({data:value.text});},'statement');}
function chooseScreenshot(){
 uni.chooseImage({count:1,sourceType:['album'],success:result=>action('正在上传截图…',async()=>{
  if(!workflowEnabled.value)throw new Error('请先更新后端，再使用完整核账流程');const asset=await upload(projectId,result.tempFilePaths[0],'reconcile');await launch('reconcile',{asset_id:asset.id});
 },'upload')});
}
function makeReport(fields){action('正在核对金额…',async()=>{
 report.value=await api('/reports','POST',{task_id:task.value.id,date:fields.date||null,wage:fields.wage||null,
  advance:fields.advance||null,balance:fields.balance||null,excerpt:fields.excerpt||''});
 chat.value=null;remember(null);await refresh();
},'report');}
function copyReport(){action('正在整理跟进话术…',async()=>{const value=await api('/reports/'+report.value.id+'/message');if(value.totals)ledger.value={...ledger.value,totals:value.totals};wechatMessage.value=value.text;},'message');}
function decideReceipt(value){action('正在核对收款…',async()=>{
 const body={received:value.received,confirmed:value.received,amount:value.amount||null,date:value.date||null,confirm_duplicate:!!value.confirm_duplicate};
 try{report.value=await api('/reports/'+report.value.id+'/receipts/'+value.id,'POST',body);ledger.value={...ledger.value,totals:report.value.totals};}
 catch(e){
  if(e.status===409&&value.received){uni.showModal({title:'可能已经记过',content:e.message+'。请检查账本，只有确定是另一笔收款才继续。',confirmText:'是另一笔',cancelText:'返回核对',success:r=>{if(r.confirm)decideReceipt({...value,confirm_duplicate:true});}});return;}
  throw e;
 }
 wechatMessage.value='';await refresh();
 uni.showToast({title:value.received?'已核对并更新账本':'已记录尚未收到',icon:'success'});
},'receipt:'+value.id);}
function cancelReconcile(){action('正在取消这次核账…',async()=>{if(task.value&&workflowEnabled.value)await api('/tasks/'+task.value.id+'/dismiss','POST',{});chat.value=null;remember(null);task.value=null;await refresh();report.value=workspace.value.latest_report;});}

function viewSource(id){action('正在读取原话…',async()=>{
 if(!sourceEnabled.value)throw new Error('原话查看暂不可用，请先更新后端再试');
 sourceFull.value=false;source.value=await api('/drafts/'+id+'/source');
},'source:'+id);}
function viewAsset(id){if(playing.value===id){stopAudio();return;}action('正在读取原件…',async()=>{
 stopAudio();
 const meta=await api('/assets/'+id+'/meta');const path=await download('/assets/'+id);
 if(!alive)return;
 if(meta.mime.startsWith('audio/'))await player.play(path,{onPlaying:()=>{playing.value=id;uni.showToast({title:'正在播放录音',icon:'none'});},onStopped:()=>{playing.value='';},onError:e=>{if(alive)error.value=e.message;}});
 else await new Promise((resolve,reject)=>uni.previewImage({urls:[path],success:resolve,fail:()=>reject(new Error('图片预览失败，请重试'))}));
},'asset:'+id);}
function archiveKey(){return archiveStorageKey(currentSession()?.user?.id||'guest',projectId);}
function rememberArchive(){
 // #ifndef H5
 if(exported.value)uni.setStorageSync(archiveKey(),exported.value);
 // #endif
}
function restoreArchive(){
 // #ifndef H5
 const saved=uni.getStorageSync(archiveKey());
 if(saved?.path&&saved?.filename&&!saved.path.startsWith('blob:'))exported.value=saved;
 // #endif
}
function releaseArchive(){
 // #ifdef H5
 if(exported.value?.path?.startsWith('blob:'))URL.revokeObjectURL(exported.value.path);
 // #endif
}
async function saveArchiveFile(record){
 // #ifdef H5
 const link=document.createElement('a');link.href=record.path;link.download=record.filename;
 document.body.appendChild(link);link.click();link.remove();
 record.feedback='已发起下载，请在浏览器的“下载记录”中查看。实际保存位置由浏览器决定。';
 uni.showToast({title:'已发起下载',icon:'none'});
 return;
 // #endif
 // #ifndef H5
 busy.value='请在系统窗口选择保存位置…';
 record.feedback='文件已在应用内生成，请在系统窗口选择文件夹并保存。';rememberArchive();
 try{
  const result=await saveAndroidDocument(record);
  if(result.status==='saved'){
   record.feedback='已保存到你刚才选择的位置，可在系统文件管理器中按文件名查找。';
   record.saved_uri=result.uri;uni.showToast({title:'已保存到所选位置',icon:'success'});
  }else record.feedback='已取消保存到手机；文件仍在应用内，可打开预览或重新选择保存位置。';
 }catch(e){record.feedback=e.message;throw e;}finally{rememberArchive();}
 // #endif
}
function exportProject(format='pdf'){action(format==='zip'?'正在打包原始文件…':'正在生成PDF档案…',async()=>{
 format=format==='zip'?'zip':'pdf';
 if(format==='pdf'&&!pdfEnabled.value)throw new Error('请先更新后端，再导出PDF档案；原始ZIP仍可备份。');
 const filePath=await download('/projects/'+projectId+(format==='pdf'?'/archive.pdf':'/export'));
 const filename=archiveFilename(project.value.name,format);
 let path=filePath;
 // #ifndef H5
 path=await keepDocument(filePath,filename);
 // #endif
 releaseArchive();
 exported.value={path,filename,format,mime:format==='pdf'?'application/pdf':'application/zip',created_at:new Date().toISOString(),feedback:'文件已生成，尚未保存到手机。'};
 rememberArchive();await saveArchiveFile(exported.value);
},format==='zip'?'export_zip':'export');}
function saveArchive(){action('正在打开保存窗口…',()=>saveArchiveFile(exported.value),'save_archive');}
function openArchive(){
 if(!exported.value)return;
 // #ifdef H5
 const opened=window.open(exported.value.path,'_blank');
 if(!opened)exported.value.feedback='浏览器阻止了预览，请保存文件后从下载记录中打开。';
 // #endif
 // #ifndef H5
 openDocument(exported.value,message=>{if(alive){exported.value.feedback=message;rememberArchive();}});
 // #endif
}

</script>
<style scoped>
.source-text{white-space:pre-wrap;overflow-wrap:anywhere}
.project-meta{display:flex;align-items:center;flex-wrap:wrap;column-gap:14px;row-gap:4px;margin-top:6px}
.project-meta .muted{margin-top:0}
.sync-status{display:flex;align-items:center;gap:6px;color:#476078;font-size:14px;line-height:1.6}
.sync-spinner{width:14px;height:14px;flex:none;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:sync-spin .9s linear infinite}
.sync-error{display:flex;align-items:center;flex-wrap:wrap;gap:4px 10px;margin-top:8px;color:#a32c1c;font-size:14px;line-height:1.6}
.sync-error .text-button{font-size:14px;margin:0;min-height:36px;padding:4px 0;flex:none}
@keyframes sync-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.sync-spinner{animation:none}}
</style>


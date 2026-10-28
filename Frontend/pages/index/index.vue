<template>
 <view class="app-shell">
  <view class="top"><text class="brand">工明白</text><button hover-class="none" class="text-button" @click="settings = !settings">设置</button></view>
  <view v-if="settings" class="panel settings-panel">
   <text class="section-title">连接设置</text>
   <text class="muted">后端服务地址</text><input aria-label="后端服务地址" v-model="server" placeholder="https://你的服务地址" />
   <button hover-class="none" class="primary" :disabled="!!busy" @click="connect">连接服务</button>
   <view v-if="!showAuth" class="settings-account"><text class="muted">{{ accountName }}</text><button hover-class="none" class="text-button" :disabled="!!busy" @click="signOut">退出登录</button></view>
  </view>
  <view v-if="error" class="error" role="alert">{{ error }}<button hover-class="none" class="text-button" @click="error = ''">收起</button></view>
  <view v-if="busy" class="processing">{{ busy }}</view>
  <AccountPanel v-if="showAuth" :guest-enabled="guestEnabled" @success="signedIn" />
  <template v-else>
   <text class="page-title">{{ titles[section] }}</text>
   <text v-if="section !== 'home'" class="muted selection-hint">选择一个项目，{{ hints[section] }}。</text>
   <button hover-class="none" v-if="section === 'home'" class="primary create-project" :disabled="!!busy" @click="showCreate = true">＋ 创建项目</button>
   <ProjectCards v-if="!busy || projects.length" :projects="projects" :section="section" :disabled="!!busy || confirmingDelete" @open="openProject" @delete="confirmDelete" />
   <AppNav :active="section" @change="section = $event" />
  </template>
  <view v-if="showCreate" class="sheet-mask" @click="showCreate = false">
   <view class="sheet" @click.stop>
    <text class="section-title">创建项目</text>
    <text class="muted">每个项目单独记工、核账和整理务工档案。</text>
    <view class="form-field"><text>项目名称</text><input aria-label="项目名称" v-model="projectName" maxlength="100" placeholder="例如：万达三期装修" /></view>
    <view class="form-field"><text>老板称呼</text><input aria-label="老板称呼" v-model="bossName" maxlength="100" placeholder="例如：王师傅" /></view>
    <text v-if="createError" class="warning">{{ createError }}</text>
    <button hover-class="none" class="primary" :disabled="!!busy" @click="createProject">保存项目</button>
    <button hover-class="none" class="secondary" :disabled="!!busy" @click="showCreate = false">取消</button>
   </view>
  </view>
 </view>
</template>
<script setup>
import { ref, onUnmounted } from 'vue';
import { onLoad, onShow } from '@dcloudio/uni-app';
import AccountPanel from '../../components/AccountPanel.vue';
import ProjectCards from '../../components/ProjectCards.vue';
import AppNav from '../../components/AppNav.vue';
import { api, baseURL, currentSession, logout, serviceHealth } from '../../services/api';
const titles = { home:'我的项目', ledger:'项目账本', check:'项目核账', files:'务工档案证据线' };
const hints = { ledger:'查看它的账本', check:'核对它的微信记录', files:'查看它的务工档案与证据时间线' };
const section=ref('home'),projects=ref([]),showAuth=ref(!currentSession()),guestEnabled=ref(false);
const settings=ref(false),server=ref(baseURL()),busy=ref(''),error=ref(''),accountName=ref('');
const showCreate=ref(false),projectName=ref(''),bossName=ref(''),createError=ref('');
const confirmingDelete=ref(false);
let loaded=false;
async function action(label,fn){
 if(busy.value)return;
 busy.value=label;error.value='';
 try{await fn();}catch(e){error.value=e.message;}finally{busy.value='';}
}
async function init(){
 const health=await serviceHealth();guestEnabled.value=health.guest_enabled!==false;
 showAuth.value=!currentSession();
 if(showAuth.value){projects.value=[];return;}
 const me=await api('/auth/me');
 accountName.value=me.phone?me.phone.slice(0,3)+'****'+me.phone.slice(-4):'体验账号';
 projects.value=await api('/projects');
}
onLoad(()=>action('正在连接…',async()=>{await init();loaded=true;}));
onShow(()=>{if(loaded&&currentSession())action('正在读取项目…',init);});
function expired(){showAuth.value=true;projects.value=[];}
uni.$on('session-expired',expired);onUnmounted(()=>uni.$off('session-expired',expired));
function signedIn(){action('正在读取项目…',async()=>{section.value='home';await init();loaded=true;});}
function signOut(){action('正在退出…',async()=>{await logout();expired();settings.value=false;});}
function connect(){action('正在连接…',async()=>{
 const url=server.value.trim().replace(/\/+$/,'');
 if(!/^https?:\/\//.test(url))throw new Error('请输入http或https服务地址');
 if(url!==baseURL()){
  ['session','project_id','pending_task','pending_tasks'].forEach(k=>uni.removeStorageSync(k));
  projects.value=[];showAuth.value=true;
 }
 uni.setStorageSync('api_url',url);server.value=url;await init();loaded=true;settings.value=false;
});}
function createProject(){
 createError.value='';
 if(!projectName.value.trim()){createError.value='请填写项目名称';return;}
 action('正在创建项目…',async()=>{
  try{
   await api('/projects','POST',{name:projectName.value.trim(),boss:bossName.value.trim()||'老板'});
   projects.value=await api('/projects');showCreate.value=false;projectName.value='';bossName.value='';
  }catch(e){createError.value=e.message;}
 });
}
function openProject(project){uni.navigateTo({url:'/pages/project/index?id='+encodeURIComponent(project.id)+'&section='+section.value});}
function confirmDelete(project){
 if(busy.value||confirmingDelete.value)return;
 confirmingDelete.value=true;
 uni.showModal({title:'删除项目',content:'确认删除“'+project.name+'”？删除后，该项目及账本、核账记录和材料将不再显示。',
  confirmText:'删除',confirmColor:'#a32c1c',cancelText:'取消',
  success:result=>{if(result.confirm)action('正在删除项目…',async()=>{
   try{await api('/projects/'+encodeURIComponent(project.id)+'?confirmed=true','DELETE');}
   catch(e){if(e.status===405)throw new Error('删除功能暂不可用，请稍后再试');throw e;}
   projects.value=projects.value.filter(value=>value.id!==project.id);
   const tasks=uni.getStorageSync('pending_tasks')||{};delete tasks[project.id];uni.setStorageSync('pending_tasks',tasks);
   if(uni.getStorageSync('project_id')===project.id)uni.removeStorageSync('project_id');
   uni.showToast({title:'项目已删除',icon:'success'});
  });},
  complete:()=>{confirmingDelete.value=false;}
 });
}
</script>

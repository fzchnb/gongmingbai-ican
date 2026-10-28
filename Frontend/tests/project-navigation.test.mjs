import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const source=(await readFile(new URL('../pages/project/index.vue',import.meta.url),'utf8'))
 .split('<script setup>')[1].split('</script>')[0].replace(/import [\s\S]*?;\r?\n/g,'');
const ledger=balance=>({totals:{balance_fen:balance},entries:[],payments:[]});
function page(){
 const reads=[],hooks={},scrolls=[],events=[];
 const context={ref:value=>({value}),computed:fn=>({get value(){return fn();}}),watch:()=>{},
  nextTick:fn=>Promise.resolve().then(fn),onLoad:fn=>hooks.load=fn,onShow:fn=>hooks.show=fn,
  onUnload:fn=>hooks.unload=fn,onHide:()=>{},onBackPress:()=>{},onUnmounted:()=>{},
  createPlayer:()=>({stop:()=>{}}),cancelRecording:()=>{},
  uni:{$on:()=>{},getStorageSync:()=>({}),setStorageSync:()=>{},pageScrollTo:value=>scrolls.push(value),showToast:value=>events.push(value)},
  api:(path,method='GET',body)=>new Promise((resolve,reject)=>reads.push({path,method,body,resolve,reject})),
 };
 vm.runInNewContext(source+`;projectId='demo';project.value={id:'demo'};workflowEnabled.value=true;
 globalThis.page={changeTab,syncProject,refresh,savePayment,newDraft,busy,operation,section,ledger,syncing,syncError,draft};`,context);
 const finish=(start,balance)=>{
  for(const r of reads.slice(start,start+3))r.resolve(r.path.endsWith('/ledger')?ledger(balance):r.path.endsWith('/timeline')?[]:{pending_reports:[],latest_report:null});
 };
 return {...context.page,reads,hooks,scrolls,events,finish};
}

test('rapid tab changes and foreground resume respond while sharing one slow background read',async()=>{
 const p=page();p.changeTab('ledger');
 assert.equal(p.section.value,'ledger');assert.equal(p.busy.value,'');assert.equal(p.syncing.value,true);
 p.changeTab('check');p.changeTab('files');p.changeTab('home');p.hooks.show();
 assert.equal(p.section.value,'home');assert.equal(p.reads.length,3);
 const done=p.syncProject();p.finish(0,28400);await done;
 assert.equal(p.syncing.value,false);assert.equal(p.ledger.value.totals.balance_fen,28400);assert.equal(p.scrolls.length,4);
});

test('failed background read leaves navigation usable and retry updates the cached ledger',async()=>{
 const p=page();p.changeTab('ledger');const failed=p.syncProject();
 p.reads[0].reject(new Error('网络暂时不可用'));p.finish(0,28400);await failed;
 assert.equal(p.syncing.value,false);assert.match(p.syncError.value,/网络/);assert.equal(p.busy.value,'');
 p.changeTab('check');assert.equal(p.section.value,'check');
 const retry=p.syncProject();p.finish(3,0);await retry;
 assert.equal(p.syncError.value,'');assert.equal(p.ledger.value.totals.balance_fen,0);
});

test('save stays protected while navigation works and an old read cannot restore an unpaid balance',async()=>{
 const p=page();p.changeTab('ledger');const old=p.syncProject();
 p.savePayment({amount:'284'});assert.equal(p.busy.value,'正在保存收款…');
 p.changeTab('check');p.changeTab('home');p.newDraft();
 assert.equal(p.section.value,'home');assert.equal(p.draft.value,null);assert.equal(p.reads.length,4);
 p.savePayment({amount:'284'});assert.equal(p.reads.filter(r=>r.method==='POST').length,1);
 p.reads[3].resolve({});await new Promise(setImmediate);
 assert.equal(p.reads.length,7);p.finish(4,0);
 await new Promise(setImmediate);
 assert.equal(p.ledger.value.totals.balance_fen,0);assert.equal(p.busy.value,'');
 p.finish(0,28400);await old;
 assert.equal(p.ledger.value.totals.balance_fen,0);assert.equal(p.syncing.value,false);
});

test('superseded failures and responses after leaving cannot publish stale state',async()=>{
 const p=page();const old=p.syncProject(),newer=p.refresh();
 p.finish(3,0);await newer;p.reads[0].reject(new Error('旧请求失败'));p.finish(0,28400);await old;
 assert.equal(p.syncError.value,'');assert.equal(p.ledger.value.totals.balance_fen,0);
 const final=p.syncProject();p.hooks.unload();p.finish(6,28400);await final;
 assert.equal(p.ledger.value.totals.balance_fen,0);
});

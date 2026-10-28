import test from 'node:test';
import assert from 'node:assert/strict';
import {archiveFilename,archiveStorageKey,keepDocument,saveAndroidDocument,openDocument} from '../services/documents.mjs';

function android(){
 const calls=[],objects={input:{},source:{},target:{},output:{},uri:{}};
 const previous=(...args)=>calls.push(['previous',...args]);
 const activity={onActivityResult:previous,startActivityForResult:(intent,code)=>calls.push(['picker',intent,code])};
 class Intent{constructor(action){this.action=action;}addCategory(value){this.category=value;}setType(value){this.mime=value;}putExtra(key,value){this.filename=value;}}
 let transferred=0;
 const native={os:{name:'Android'},io:{convertLocalFileSystemURL:()=>'/private/archive.pdf'},android:{
  runtimeMainActivity:()=>activity,importClass:()=>Intent,newObject:()=>objects.input,
  invoke:(object,method,...args)=>{
   calls.push([method,...args]);
   if(method==='getData')return objects.uri;if(method==='getContentResolver')return {};
   if(method==='openOutputStream')return objects.output;if(method==='getChannel')return objects.source;
   if(method==='newChannel')return objects.target;if(method==='size')return 8;
   if(method==='transferTo'){const n=Math.min(3,args[1]);transferred+=n;return n;}
   if(method==='toString')return 'content://downloads/archive.pdf';
  }
 }};
 return {native,activity,previous,calls,objects,result:(code=-1)=>activity.onActivityResult(0x4d42,code,{}),get transferred(){return transferred;}};
}
const record={path:'_doc/archives/a.pdf',filename:'档案.pdf',mime:'application/pdf'};

test('system save succeeds only after all bytes and streams have been written and closed',async()=>{
 const x=android();const promise=saveAndroidDocument(record,x.native);
 assert.equal(x.calls[0][0],'picker');assert.equal(x.calls[0][1].action,'android.intent.action.CREATE_DOCUMENT');
 assert.equal(x.calls[0][1].mime,'application/pdf');assert.equal(x.calls[0][1].filename,'档案.pdf');
 x.result();const result=await promise;
 assert.equal(result.status,'saved');assert.equal(x.transferred,8);assert.equal(x.activity.onActivityResult,x.previous);
 assert.ok(x.calls.find(c=>c[0]==='flush'));assert.equal(x.calls.filter(c=>c[0]==='close').length,2);
});

test('cancelling the system picker is not reported as saved; repeated saves do not replace its callback',async()=>{
 const x=android();const promise=saveAndroidDocument(record,x.native);
 await assert.rejects(saveAndroidDocument(record,x.native),/先完成/);
 x.activity.onActivityResult(999,0,null);assert.equal(x.calls.at(-1)[0],'previous');
 x.result(0);assert.equal((await promise).status,'cancelled');
 assert.equal(x.transferred,0);assert.equal(x.activity.onActivityResult,x.previous);
});

test('write, flush and picker failures reject, restore callbacks and permit retry',async()=>{
 for(const failed of ['transferTo','flush']){
  const x=android(),invoke=x.native.android.invoke;
  x.native.android.invoke=(o,m,...args)=>{if(m===failed)throw Error('disk-full');return invoke(o,m,...args);};
  const promise=saveAndroidDocument(record,x.native);x.result();await assert.rejects(promise,/未能保存/);
  assert.equal(x.activity.onActivityResult,x.previous);
 }
 const x=android();x.activity.startActivityForResult=()=>{throw Error('no picker');};
 await assert.rejects(saveAndroidDocument(record,x.native),/无法打开系统保存窗口/);
 assert.equal(x.activity.onActivityResult,x.previous);
 const retry=android();const promise=saveAndroidDocument(record,retry.native);retry.result();assert.equal((await promise).status,'saved');
});

test('private copy failure cannot masquerade as public saving; opening failures remain visible',async()=>{
 const native={io:{resolveLocalFileSystemURL:(path,success)=>success(path==='_doc/'?{getDirectory:(name,opt,ok)=>ok({})}:{copyTo:(folder,name,ok,fail)=>fail()})}};
 await assert.rejects(keepDocument('temp','a.pdf',native),/保存失败/);
 let message='';openDocument(record,value=>message=value,{runtime:{openFile:(path,options,fail)=>fail()}});
 assert.match(message,/未能打开/);
});

test('an optional saved-URI label failure cannot leave a completed file waiting forever',async()=>{
 const x=android(),invoke=x.native.android.invoke;
 x.native.android.invoke=(o,m,...args)=>{if(m==='toString')throw Error('URI label unavailable');return invoke(o,m,...args);};
 const promise=saveAndroidDocument(record,x.native);x.result();assert.equal((await promise).status,'saved');
});

test('archive names are safe, descriptive and records are scoped to account and project',()=>{
 const name=archiveFilename('../项目:*?','pdf',new Date('2026-10-24T23:30:00Z'));
 assert.match(name,/务工档案证据线-.*20261025-073000-000.pdf/);assert.doesNotMatch(name,/[\\/:*?"<>|]/);
 assert.notEqual(archiveStorageKey('owner1','p'),archiveStorageKey('owner2','p'));
 assert.notEqual(archiveStorageKey('owner1','p'),archiveStorageKey('owner1','q'));
});

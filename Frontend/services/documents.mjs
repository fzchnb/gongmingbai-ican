// Document files are kept in-app for reopening. Android's system picker creates
// a separate copy in the location selected by the user; no broad storage access.
export function archiveFilename(project,format='pdf',now=new Date()){
 const name=String(project||'项目').replace(/[\\/:*?"<>|\u0000-\u001f]/g,'').trim().slice(0,36)||'项目';
 const stamp=new Date(now.getTime()+8*3600000).toISOString().replace(/[-:]/g,'').slice(0,15).replace('T','-')+'-'+String(now.getUTCMilliseconds()).padStart(3,'0');
 return `${format==='zip'?'原始凭据备份':'务工档案证据线'}-${name}-${stamp}.${format}`;
}

export function keepDocument(path,filename,native=globalThis.plus){
 return new Promise((resolve,reject)=>{
  if(!native?.io)return reject(new Error('请在手机App中保存文件'));
  native.io.resolveLocalFileSystemURL('_doc/',root=>root.getDirectory('archives',{create:true},folder=>{
   native.io.resolveLocalFileSystemURL(path,entry=>entry.copyTo(folder,filename,saved=>resolve(saved.toLocalURL()),
    ()=>reject(new Error('文件已下载，但应用内保存失败，请重新导出'))),()=>reject(new Error('下载文件已失效，请重新导出')));
  },()=>reject(new Error('无法创建档案目录，请检查手机存储空间'))),()=>reject(new Error('无法读取应用档案目录')));
 });
}

let saving=false;
const REQUEST_CODE=0x4d42;
export function saveAndroidDocument(record,native=globalThis.plus){
 if(saving)return Promise.reject(new Error('请先完成当前的保存选择'));
 if(!native?.android||native.os?.name!=='Android')return Promise.reject(new Error('系统另存为目前支持Android手机，请使用文件阅读器的存储功能'));
 saving=true;
 return new Promise((resolve,reject)=>{
  const android=native.android;
  let activity,previous,handler;
  const cleanup=()=>{if(activity&&activity.onActivityResult===handler)activity.onActivityResult=previous;saving=false;};
  const fail=message=>{cleanup();reject(new Error(message));};
  try{
   activity=android.runtimeMainActivity();previous=activity.onActivityResult;
   handler=(requestCode,resultCode,data)=>{
    if(Number(requestCode)!==REQUEST_CODE){if(typeof previous==='function')previous.call(activity,requestCode,resultCode,data);return;}
    if(Number(resultCode)!==-1){cleanup();resolve({status:'cancelled'});return;}
    let input,output,source,target,uri,failure;
    try{
     uri=data&&android.invoke(data,'getData');
     if(!uri)throw new Error('系统没有返回保存位置');
     const resolver=android.invoke(activity,'getContentResolver');
     output=android.invoke(resolver,'openOutputStream',uri,'w');
     if(!output)throw new Error('无法写入所选位置');
     const path=native.io.convertLocalFileSystemURL(record.path).replace(/^file:\/\//,'');
     input=android.newObject('java.io.FileInputStream',path);
     source=android.invoke(input,'getChannel');
     target=android.invoke('java.nio.channels.Channels','newChannel',output);
     const size=Number(android.invoke(source,'size'));
     if(!size)throw new Error('导出文件为空，请重新生成');
     let offset=0;
     while(offset<size){
      const count=Number(android.invoke(source,'transferTo',offset,size-offset,target));
      if(!Number.isFinite(count)||count<=0)throw new Error('文件没有完整写入');
      offset+=count;
     }
     android.invoke(output,'flush');
    }catch(e){failure=e;}
    finally{
     for(const stream of [target||output,input])if(stream)try{android.invoke(stream,'close');}catch(e){failure ||= e;}
    }
    cleanup();
    if(failure){reject(new Error('未能保存到所选位置，请重试。应用内文件仍可打开。'));return;}
    let uriText='';try{uriText=String(android.invoke(uri,'toString'));}catch{}
    resolve({status:'saved',uri:uriText});
   };
   activity.onActivityResult=handler;
   const Intent=android.importClass('android.content.Intent');
   const intent=new Intent('android.intent.action.CREATE_DOCUMENT');
   intent.addCategory('android.intent.category.OPENABLE');
   intent.setType(record.mime);intent.putExtra('android.intent.extra.TITLE',record.filename);
   activity.startActivityForResult(intent,REQUEST_CODE);
  }catch(e){fail('无法打开系统保存窗口，请确认手机文件管理器可用后重试。');}
 });
}

export function openDocument(record,onError,native=globalThis.plus){
 if(!native?.runtime){onError('请在浏览器下载记录中打开这个文件');return;}
 native.runtime.openFile(record.path,{},()=>onError('未能打开文件，请先安装可查看PDF或ZIP的应用，也可选择“保存到手机”后打开。'));
}

export function archiveStorageKey(owner,project){return 'archive_export:'+owner+':'+project;}

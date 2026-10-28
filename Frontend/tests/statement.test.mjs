import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
function component(){
 let album,canvas;const toasts=[],modals=[];
 const source=readFileSync(new URL('../components/StatementImage.vue',import.meta.url),'utf8')
 .split('<script setup>')[1].split('</script>')[0].replace(/import .*?;\r?\n/g,'').replace(/\/\/ #ifdef H5[\s\S]*?\/\/ #endif/g,'');
 const context={ref:value=>({value}),getCurrentInstance:()=>({proxy:{}}),defineProps:()=>({project:{name:'验收',boss:'师傅'},totals:{}}),money:()=>0,
 uni:{createCanvasContext:()=>new Proxy({draw:(_,done)=>done()},{get:(target,key)=>target[key]||(()=>{})}),
 canvasToTempFilePath:options=>{canvas=options;},saveImageToPhotosAlbum:options=>{album=options;},showToast:o=>toasts.push(o),showModal:o=>modals.push(o)}};
 vm.runInNewContext(source+';globalThis.api={save,saving,feedback};',context);
 return {api:context.api,toasts,modals,get canvas(){return canvas;},get album(){return album;}};
}
test('album success reports saved only after success callback; repeated tap is blocked',()=>{
 const c=component();c.api.save();assert.equal(c.api.saving.value,true);
 const pending=c.canvas;c.api.save();assert.equal(c.canvas,pending);
 c.canvas.success({tempFilePath:'test.png'});assert.equal(c.toasts.length,0);
 c.album.success();assert.equal(c.api.saving.value,false);assert.match(c.api.feedback.value,/已保存到相册/);
 assert.equal(c.toasts[0].icon,'success');
});
test('denied album permission and failed rendering never show success',()=>{
 const c=component();c.api.save();c.canvas.success({tempFilePath:'test.png'});c.album.fail();
 assert.equal(c.api.saving.value,false);assert.match(c.api.feedback.value,/权限/);assert.equal(c.modals.length,1);
 const d=component();d.api.save();d.canvas.fail();assert.equal(d.api.saving.value,false);
 assert.equal(d.toasts[0].icon,'none');assert.match(d.api.feedback.value,/生成图片失败/);
});

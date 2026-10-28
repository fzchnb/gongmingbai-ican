import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const recorderSource=await readFile(new URL('../services/recorder.js',import.meta.url),'utf8');
const {createRecordingController}=await import('data:text/javascript;base64,'+Buffer.from(recorderSource).toString('base64'));
const source=(await readFile(new URL('../components/VoiceInput.vue',import.meta.url),'utf8')).split('<script setup>')[1].split('</script>')[0]
 .replace(/import .*?;\r?\n/g,'').replace(/\/\/ #ifdef H5[\s\S]*?\/\/ #endif/g,'');
function component(){
 const props={disabled:false,compact:false,label:'按住说话，松开发送',processing:'',transcript:''},events={},emitted=[],calls={start:0,stop:0};
 const manager={onStart:fn=>events.start=fn,onStop:fn=>events.stop=fn,onError:fn=>events.error=fn,start:()=>calls.start++,stop:()=>calls.stop++};
 const controller=createRecordingController(()=>manager);
 const context={ref:value=>({value}),computed:fn=>({get value(){return fn();}}),defineProps:()=>props,
  defineEmits:()=>((name,value)=>emitted.push({name,value})),onUnmounted:()=>{},startRecording:callbacks=>controller.start(callbacks),
  Date,setInterval:()=>1,clearInterval:()=>{}};
 vm.runInNewContext(source+';globalThis.api={begin,release,move,processingText,buttonText,localError};',context);
 return {api:context.api,props,events,emitted,calls};
}
test('voice has uninterrupted visible stopping, uploading and recognition states',()=>{
 const x=component();x.api.begin({touches:[{clientY:200}]});
 assert.match(x.api.buttonText.value,/打开麦克风/);
 x.events.start();assert.match(x.api.buttonText.value,/正在录音/);
 x.api.release();assert.match(x.api.processingText.value,/生成录音/);
 x.events.stop({tempFilePath:'demo.mp3',duration:1400});
 assert.equal(x.emitted[0].name,'recorded');
 x.props.processing='正在上传录音…';assert.equal(x.api.buttonText.value,x.props.processing);
 x.api.begin({touches:[{clientY:200}]});assert.equal(x.calls.start,1);
 x.props.processing='正在把录音转成文字…';assert.match(x.api.buttonText.value,/转成文字/);
 x.props.processing='正在整理记工草稿…';assert.match(x.api.buttonText.value,/整理/);
 x.props.processing='';assert.equal(x.api.buttonText.value,'按住说话，松开发送');
});
test('slide cancellation and microphone errors restore the control without submitting',()=>{
 const x=component();x.api.begin({touches:[{clientY:200}]});x.events.start();
 x.api.move({touches:[{clientY:100}]});x.api.release();assert.match(x.api.processingText.value,/取消录音/);
 x.events.stop({tempFilePath:'cancel.mp3',duration:1400});assert.equal(x.emitted.length,0);
 x.api.begin({touches:[{clientY:200}]});x.events.error();
 assert.equal(x.api.processingText.value,'');assert.match(x.api.localError.value,/录音失败/);
 assert.equal(x.emitted[0].name,'error');
});
test('compact voice correction presents its own processing stage',()=>{
 const x=component();x.props.compact=true;x.props.processing='正在上传修改录音…';
 assert.match(x.api.buttonText.value,/上传修改录音/);
 x.props.processing='';assert.equal(x.api.buttonText.value,'按住说话');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source=await readFile(new URL('../services/recorder.js',import.meta.url),'utf8');
const {createRecordingController}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
function setup(){
 const events={},calls={start:0,stop:0},results=[],errors=[];
 const manager={onStart:fn=>events.start=fn,onStop:fn=>events.stop=fn,onError:fn=>events.error=fn,
  start:()=>calls.start++,stop:()=>calls.stop++};
 const controller=createRecordingController(()=>manager);
 const callbacks={onResult:value=>results.push(value),onError:value=>errors.push(value)};
 return {controller,callbacks,events,calls,results,errors};
}
test('releasing sends exactly one completed recording',()=>{
 const x=setup(),handle=x.controller.start(x.callbacks);x.events.start();handle.release();
 assert.equal(x.calls.stop,1);assert.equal(x.results.length,0);
 x.events.stop({tempFilePath:'recording.mp3',duration:1400});
 x.events.stop({tempFilePath:'duplicate.mp3',duration:1400});
 assert.deepEqual(x.results,[{tempFilePath:'recording.mp3',duration:1400}]);
});
test('sliding away cancels without submitting a file',()=>{
 const x=setup(),handle=x.controller.start(x.callbacks);x.events.start();handle.cancel();
 x.events.stop({tempFilePath:'cancelled.mp3',duration:2000});
 assert.equal(x.results.length,0);assert.equal(x.errors.length,0);
});
test('a release before permission/start waits then stops safely',()=>{
 const x=setup(),handle=x.controller.start(x.callbacks);handle.cancel();
 assert.equal(x.calls.stop,0);x.events.start();assert.equal(x.calls.stop,1);
 x.events.stop({tempFilePath:'late-permission.mp3',duration:900});assert.equal(x.results.length,0);
});
test('a short tap does not send unusable audio',()=>{
 const x=setup(),handle=x.controller.start(x.callbacks);x.events.start();handle.release();
 x.events.stop({tempFilePath:'tap.mp3',duration:120});
 assert.equal(x.results.length,0);assert.match(x.errors[0],/录音太短/);
});
test('only one recorder owns a callback and errors release the lock',()=>{
 const x=setup();x.controller.start(x.callbacks);
 assert.equal(x.controller.start(x.callbacks),null);assert.equal(x.calls.start,1);
 x.events.error();assert.ok(x.controller.start(x.callbacks));assert.equal(x.calls.start,2);
});
test('leaving the page cancels the active recording',()=>{
 const x=setup();x.controller.start(x.callbacks);x.events.start();x.controller.cancel();
 x.events.stop({tempFilePath:'background.mp3',duration:2000});assert.equal(x.results.length,0);
});

test('release exposes stopping immediately and repeated release stops only once',()=>{
 const x=setup(),stopping=[];
 const handle=x.controller.start({...x.callbacks,onStopping:value=>stopping.push(value)});
 x.events.start();handle.release();handle.release();
 assert.deepEqual(stopping,[{cancelled:false}]);assert.equal(x.calls.stop,1);
 assert.equal(x.results.length,0);
 x.events.stop({tempFilePath:'ready.mp3',duration:1200});assert.equal(x.results.length,1);
});

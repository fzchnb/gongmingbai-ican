import test from 'node:test';
import assert from 'node:assert/strict';
import {chinaTime} from '../services/display.mjs';
import {createPlayer} from '../services/player.mjs';
test('Chinese timestamps use Beijing time, cross midnight and reject missing dates',()=>{
 assert.equal(chinaTime('2026-10-24T18:04:02Z'),'2026年10月25日 02:04');
 assert.equal(chinaTime('2026-10-25T02:04:02+08:00'),'2026年10月25日 02:04');
 for(const value of [null,'',undefined,'invalid'])assert.equal(chinaTime(value),'时间待确认');
});
function harness(){
 const events={};let destroyed=0;
 const audio={onPlay:f=>events.play=f,onEnded:f=>events.end=f,onError:f=>events.error=f,
 play(){},destroy(){destroyed++;}};
 return {events,audio,get destroyed(){return destroyed;}};
}
test('play stays pending until playback starts; ending releases player once',async()=>{
 const h=harness(),p=createPlayer(()=>h.audio);let settled=false,playing=0,stopped=0;
 const result=p.play('record.mp3',{onPlaying:()=>playing++,onStopped:()=>stopped++}).then(()=>settled=true);
 await Promise.resolve();assert.equal(settled,false);
 h.events.play();await result;assert.equal(playing,1);
 h.events.end();p.stop();assert.equal(h.destroyed,1);assert.equal(stopped,1);
});
test('decoding failure rejects loading and destroys audio; later failure is reported',async()=>{
 const h=harness(),p=createPlayer(()=>h.audio);
 const first=p.play('broken.mp3');h.events.error();await assert.rejects(first,/播放失败/);assert.equal(h.destroyed,1);
 let errors=0;const second=p.play('valid.mp3',{onError:()=>errors++});h.events.play();await second;
 h.events.error();assert.equal(errors,1);assert.equal(h.destroyed,2);
});
test('leaving while preparing audio cancels pending playback safely',async()=>{
 const h=harness(),p=createPlayer(()=>h.audio),result=p.play('record.mp3');p.stop();
 await assert.rejects(result,/取消/);assert.equal(h.destroyed,1);
});

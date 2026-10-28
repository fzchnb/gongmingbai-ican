<template>
 <view class="voice-control" :class="{ compact, held: pressing && !processingText, cancelling }" :aria-busy="!!processingText">
  <button hover-class="none" :class="compact ? 'voice-compact' : 'voice-disc'" :disabled="disabled || !!processingText" :aria-label="buttonText" @touchstart.stop.prevent="begin" @touchmove.stop.prevent="move" @touchend.stop.prevent="release" @touchcancel.stop.prevent="cancel" @contextmenu.prevent @click="webClick">
   <view v-if="processingText" class="voice-spinner" aria-hidden="true" /><image v-else :src="compact?'/static/nav-work.svg':'/static/mic.svg'" />
   <text v-if="compact" aria-live="polite">{{ buttonText }}</text>
  </button>
  <template v-if="!compact">
   <text class="voice-label" aria-live="polite">{{ buttonText }}</text>
   <text class="muted voice-hint">{{ processingText ? '请稍等，处理好后会打开核对页面' : pressing && !cancelling ? '向上滑动可取消' : '上滑取消' }}</text>
  </template>
  <view v-if="processing && transcript" class="voice-transcript" role="status"><text class="muted block">刚才说的是</text><text>{{ transcript }}</text></view>
  <text v-if="localError" class="voice-error" role="alert">{{ localError }}</text>
 </view>
</template>
<script setup>
import { ref, computed, onUnmounted } from 'vue';
import { startRecording } from '../services/recorder';
const props = defineProps({ disabled: Boolean, compact: Boolean, processing:String, transcript:String, label: { type: String, default: '按住说话，松开发送' } });
const emit = defineEmits(['recorded', 'error']);
const pressing=ref(false),recording=ref(false),cancelling=ref(false),seconds=ref(0),finishing=ref(false),localError=ref('');
const processingText=computed(()=>props.processing || (finishing.value ? (cancelling.value?'正在取消录音…':'正在生成录音…') : ''));
const buttonText=computed(()=>processingText.value || (pressing.value ? (cancelling.value?'松开取消录音':recording.value?'正在录音 '+seconds.value+'秒，松开发送':'正在打开麦克风…') : props.compact?'按住说话':props.label));
let handle,originY=0,timer,started=0;
function reset(){clearInterval(timer);pressing.value=false;recording.value=false;cancelling.value=false;finishing.value=false;handle=null;}
function fail(message){reset();localError.value=message;emit('error',message);}
function begin(event){
 if(props.disabled||pressing.value||processingText.value)return;
 localError.value='';
 // #ifdef H5
 fail('网页可使用文字输入；长按录音请在手机App中体验。');
 return;
 // #endif
 // #ifndef H5
 pressing.value=true;cancelling.value=false;seconds.value=0;
 originY=event.touches?.[0]?.clientY ?? 0;
 handle=startRecording({
  onStart(){recording.value=true;started=Date.now();timer=setInterval(()=>{seconds.value=Math.floor((Date.now()-started)/1000);},250);},
  onStopping(){finishing.value=true;clearInterval(timer);},
  onFinish:reset,
  onResult:result=>emit('recorded',result),
  onError:fail,
 });
 if(!handle)reset();
 // #endif
}
function move(event){if(pressing.value)cancelling.value=originY-(event.touches?.[0]?.clientY ?? originY)>65;}
function release(){if(!handle)return;if(cancelling.value)handle.cancel();else handle.release();}
function cancel(){handle?.cancel();}
function webClick(){
 // #ifdef H5
 if(!props.disabled&&!processingText.value)fail('网页可使用文字输入；长按录音请在手机App中体验。');
 // #endif
}
onUnmounted(()=>{handle?.cancel();clearInterval(timer);});
</script>
<style scoped>
.voice-control{display:flex;align-items:center;flex-direction:column;user-select:none;-webkit-user-select:none;touch-action:pan-y}
.voice-disc{--button-background:#117c0d;--button-color:#fff;touch-action:none;width:96px;height:96px;border-radius:50%;padding:23px;margin:16px auto 10px;background:#117c0d;display:flex;align-items:center;justify-content:center;transition:transform .15s,background .15s}
.voice-disc image{width:45px;height:45px}
.voice-disc{color:#fff}
.voice-spinner{width:32px;height:32px;flex:none;border:3px solid currentColor;border-right-color:transparent;border-radius:50%;animation:voice-spin .9s linear infinite}
.voice-compact .voice-spinner{width:18px;height:18px;border-width:2px}
.voice-transcript{width:100%;padding:12px;margin-top:14px;background:#eae6dd;border-radius:10px;text-align:left;font-size:16px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}
.voice-error{display:block;color:#a32c1c;font-size:16px;line-height:1.6;margin-top:12px}
@keyframes voice-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.voice-spinner{animation:none}}
.voice-label{font-size:17px;font-weight:650;text-align:center;line-height:1.6;display:block}
.voice-hint{font-size:14px;margin-top:3px}
.held .voice-disc{background:#095d08;transform:scale(1.05)}
.cancelling .voice-disc,.cancelling .voice-compact{background:#a32c1c;color:#fff}
.compact{display:block;min-width:0}
.voice-compact{--button-background:#f7f5ec;--button-color:#117c0d;touch-action:none;margin:0;min-height:48px;padding:10px 12px;border:1px solid #117c0d;border-radius:10px;color:#117c0d;background:#f7f5ec;display:flex;align-items:center;justify-content:center;gap:6px;font-size:16px;line-height:1.5}
.voice-compact image{width:20px;height:23px}
</style>

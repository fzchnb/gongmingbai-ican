export function createPlayer(create=()=>uni.createInnerAudioContext()){
 let current;
 function stop(){current?.close();current=null;}
 return {stop,play(path,{onPlaying=()=>{},onStopped=()=>{},onError=()=>{}}={}){
  stop();
  return new Promise((resolve,reject)=>{
   const audio=create();let ready=false,closed=false,timer;
   const close=()=>{if(closed)return;closed=true;clearTimeout(timer);audio.destroy();if(current?.audio===audio)current=null;onStopped();if(!ready)reject(Object.assign(new Error('播放已取消'),{code:'MEDIA_CANCELLED'}));};
   const fail=()=>{if(closed)return;const error=new Error('录音播放失败，请检查媒体音量或重试');if(ready)onError(error);else{ready=true;reject(error);}close();};
   current={audio,close};
   audio.onPlay(()=>{if(closed)return;clearTimeout(timer);ready=true;onPlaying();resolve();});
   audio.onEnded(close);audio.onError(fail);
   timer=setTimeout(fail,20000);
   try{audio.src=path;audio.play();}catch{fail();}
  });
 }};
}

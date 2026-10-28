// uni-app 的原生录音管理器是单例。只注册一次监听，避免多个页面重复收到录音。
export function createRecordingController(getManager = () => uni.getRecorderManager()) {
 let manager, active = null, sequence = 0;
 function finish(result, failure) {
  const current = active;
  if (!current) return;
  active = null;
  current.onFinish?.();
  if (current.cancelled) return;
  if (failure) { current.onError?.('录音失败，请检查麦克风权限后重试'); return; }
  const duration = result?.duration > 0 ? result.duration : Date.now() - (current.startedAt || Date.now());
  if (!result?.tempFilePath || duration < 600) { current.onError?.('录音太短，请按住说完整一句'); return; }
  current.onResult?.({ tempFilePath: result.tempFilePath, duration });
 }
 function ensureManager() {
  if (manager) return;
  manager = getManager();
  manager.onStart(() => {
   if (!active) return;
   active.startedAt = Date.now();
   active.onStart?.();
   if (active?.released) manager.stop();
  });
  manager.onStop(result => finish(result));
  manager.onError(() => finish(null, true));
 }
 function release(id, cancelled) {
  if (!active || active.id !== id) return;
  active.cancelled ||= cancelled;
  if (active.released) return;
  active.released = true;
  active.onStopping?.({cancelled: active.cancelled});
  if (active.startedAt) {
   try { manager.stop(); } catch { finish(null, true); }
  }
 }
 return {
  start(callbacks) {
   if (active) { callbacks.onError?.('上一段录音正在结束，请稍后再试'); return null; }
   try { ensureManager(); } catch { callbacks.onError?.('当前设备暂不能录音，请使用文字记工'); return null; }
   const id = ++sequence;
   active = { ...callbacks, id, released: false, cancelled: false, startedAt: null };
   try { manager.start({ format: 'mp3', duration: 60000, sampleRate: 16000 }); }
   catch { finish(null, true); return null; }
   return { release: () => release(id, false), cancel: () => release(id, true) };
  },
  cancel() { if (active) release(active.id, true); },
 };
}
const controller = createRecordingController();
export const startRecording = callbacks => controller.start(callbacks);
export const cancelRecording = () => controller.cancel();

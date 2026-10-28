<script>
export default { onLaunch() {
 // #ifdef APP-PLUS
 if(typeof plus!=='undefined' && plus.nativeUI?.setUIStyle)plus.nativeUI.setUIStyle('light');
 // #endif
} };
</script>
<style>
@font-face{font-family:GongmingbaiBrand;src:url('/static/fonts/gongmingbai-brand.woff2') format('woff2');font-style:normal;font-weight:400;font-display:swap}
page,html,body{color-scheme:only light;background:#f1ece0!important;color:#17232c;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif;font-size:18px}
uni-page,uni-page-wrapper,uni-page-body{background-color:#f1ece0!important;color-scheme:only light}
view,text,button,input,textarea{box-sizing:border-box}
button{--button-background:transparent;--button-color:#17232c;display:flex;align-items:center;justify-content:center;text-align:center;font-family:inherit;font-size:18px;line-height:1.5;border-radius:12px;margin:12px 0;padding:14px 16px;color:inherit}
button:after,uni-button:after{border:none}
button[disabled],button.button-hover{background-color:var(--button-background)!important;color:var(--button-color)!important;opacity:1!important}
.primary:after,.secondary:after,.text-button:after,.back-button:after,.project-card:after,.project-delete:after,.entry-button:after,.bottom-nav uni-button:after,.voice-disc:after,.voice-compact:after,.outline-button:after{border:none!important}
input{min-height:50px;padding:10px 0;font-size:18px}
textarea{width:100%;min-height:120px;font-size:18px;line-height:1.6}
.app-shell{min-height:100vh;max-width:520px;background:#f1ece0;color:#17232c;color-scheme:only light;margin:0 auto;padding:calc(24px + var(--status-bar-height,0px)) 20px calc(110px + env(safe-area-inset-bottom))}
.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:32px;min-height:46px}
.brand{font-family:GongmingbaiBrand,"KaiTi",serif;font-size:40px;font-weight:700;line-height:1.2;color:#117c0d;letter-spacing:1px}
.page-title{display:block;font-size:30px;font-weight:750;line-height:1.4;overflow-wrap:anywhere}
.section-title{display:block;font-size:22px;font-weight:700;line-height:1.5}
.text-button{--button-color:#476078;display:inline-flex;align-items:center;min-height:44px;padding:5px 0;margin:0;background:transparent;color:#476078;font-size:16px;border-radius:0;border:0;line-height:1.5}
.primary,.secondary{display:flex;align-items:center;justify-content:center;text-align:center;width:100%;padding:14px 16px;line-height:1.5;font-size:18px;border-radius:12px;margin:12px 0}
.primary{--button-background:#117c0d;--button-color:#fff;background:#117c0d;color:white;font-weight:650}
.secondary{--button-background:#e8e9e3;--button-color:#253945;background:#e8e9e3;color:#253945;border:1px solid #dce5e5}
.create-project{margin:20px 0 22px;min-height:50px}
.muted{color:#657587;font-size:16px;line-height:1.6}.block{display:block}.warning{color:#a45c0a}
.selection-hint{display:block;margin:12px 0 22px}
.panel{margin:18px 0;padding:18px;background:#f5f0e5;border-radius:12px}
.settings-panel input{width:100%;font-size:15px}.settings-account{display:flex;align-items:center;justify-content:space-between;margin-top:12px}
.empty{padding:30px 0;display:flex;flex-direction:column;gap:12px}
.processing{color:#476078;background:transparent;padding:8px 0;font-size:16px;line-height:1.6;margin:10px 0 16px}
.error{background:#fff0ed;color:#a32c1c;padding:14px;line-height:1.6;margin:12px 0;border-radius:10px;font-size:16px}
.error .text-button{display:flex}
.sheet-mask{position:fixed;inset:0;background:rgba(18,35,40,.32);z-index:100;display:flex;align-items:flex-end;justify-content:center}
.sheet{width:100%;max-width:520px;background:#faf7ef;padding:24px 22px calc(20px + env(safe-area-inset-bottom));border-radius:22px 22px 0 0;max-height:90vh;overflow-y:auto}
.sheet .section-title{margin-bottom:8px}
.form-field{margin-top:18px}.form-field>text{display:block;font-size:16px;font-weight:600}.form-field input{width:100%;border-bottom:1px solid #dce5e5}
.balance-card{background:#f5f0e5;border-radius:12px;padding:16px 18px}
.balance-card .section-title{font-size:19px;color:#43515d}
.balance{display:block;font-size:44px;font-weight:750;color:#a45c0a;line-height:1.3;margin:4px 0 9px;overflow-wrap:anywhere}
.balance-card>.muted{display:block;border-top:1px solid #d3e2df;padding-top:10px;font-size:16px}
.project-heading{margin:22px 0 18px}.project-heading .muted{display:block;margin-top:6px;font-size:18px}
.back-button{--button-color:#43515d;display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0;margin:0;background:transparent;font-size:17px;line-height:1.5;color:#43515d;border-radius:0}
.back-button image{width:17px;height:21px;transform:rotate(180deg);filter:grayscale(1)}
.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:24px 0 8px}
.record-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:17px 0;border-bottom:1px solid #e8edef;font-size:17px}
.record-card{background:#f5f0e5;border:1px solid #a9b29f;border-radius:12px;margin:12px 0;overflow:hidden}
.record-card.record-row,.record-card .record-row{padding:16px;line-height:1.6}
.record-card .record-row{border:0}
.record-card .record-row>view,.record-card.record-row>view,.record-card.record-row>text:first-child{min-width:0;overflow-wrap:anywhere}
.record-card.record-row>text:last-child{flex:none}
.record-actions{display:flex;align-items:center;margin:0 16px;padding:4px 0 6px;border-top:1px solid #dedacf}
.record-card,.balance-card,.recording-card,.project-card-item,.panel{box-shadow:0 2px 6px rgba(65,70,43,.07),0 5px 14px rgba(65,70,43,.035)}
.amount{font-size:22px;color:#a45c0a;font-weight:700;white-space:nowrap}
.quote{padding:16px;background:#eae6dd;border-radius:12px;margin:16px 0;font-size:16px;line-height:1.7}
.field{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e3e8ec;padding:8px 0}
.field input{width:48%;text-align:right;min-width:0;font-size:17px}.field>text{font-size:16px;min-width:0}
.notice{padding:14px;background:#fff4e7;color:#965015;font-size:16px;line-height:1.6;margin:16px 0;border-radius:10px}
.intro{margin:14px 0 22px;display:block}.report{margin-top:26px}
.comparison{border:1px solid #dce3e8;border-radius:12px;margin-top:18px;overflow:hidden}
.compare-row{display:flex;padding:14px 10px;border-bottom:1px solid #e6eaed;gap:4px;font-size:16px}
.compare-row>text{flex:1;text-align:right;min-width:0}.compare-row>text:first-child{text-align:left}
.timeline-item{border-left:2px solid #117c0d;padding:0 0 24px 18px;margin:22px 0 0 6px}
.event-title{display:block;font-size:19px;font-weight:650;margin:8px 0;line-height:1.6}
.bottom-nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:100%;max-width:520px;display:flex;background:#f1ece0;border-top:1px solid #d2d2ce;border-radius:8px 8px 0 0;padding:7px 8px calc(7px + env(safe-area-inset-bottom));z-index:20}
.bottom-nav button,.bottom-nav uni-button{--button-color:#657587;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border-radius:0;background:transparent;color:#657587;margin:0;padding:6px 0;font-size:15px;line-height:1.5}
.bottom-nav .active{--button-color:#117c0d;color:#117c0d;font-weight:650}
.nav-icon{width:24px;height:24px;margin:0 auto 4px;display:block;filter:grayscale(1);opacity:.75}
.active .nav-icon{filter:none;opacity:1}
.money-summary{padding:18px 16px;background:#fff8ee;border-radius:12px;margin:18px 0}
.money-summary view{display:flex;justify-content:space-between;font-size:22px;font-weight:700;line-height:1.7}
@media(max-width:360px){.app-shell{padding-left:16px;padding-right:16px}.page-title{font-size:28px}.brand{font-size:38px}.field>text{font-size:15px}.balance-card>.muted{font-size:15px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

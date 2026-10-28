// Avoid Intl/locales: older Android WebViews may silently ignore zh-CN.
export function chinaTime(value) {
 if(!value)return '时间待确认';
 const time=new Date(value).getTime();
 if(!Number.isFinite(time))return '时间待确认';
 const d=new Date(time+8*3600000),pad=n=>String(n).padStart(2,'0');
 return `${d.getUTCFullYear()}年${d.getUTCMonth()+1}月${d.getUTCDate()}日 ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

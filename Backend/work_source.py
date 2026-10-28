"""Select verbatim work-related phrases. No model call, paraphrase or amount inference."""
import re

KEYWORDS=re.compile(r'(?:还没有|还没|没有|尚未|未|没)(?:收到|到账|结清)|工资已经全部收到|工资已收到|已结清|结好了|收到了|已收到|到账|借支|预支|加班|单价|工钱|工资|每小时|每天|一天|半天|小时|日期|备注|吊顶|搬运|安装|装修|水电|木工|砌墙|铺砖|工地|干活|点工|今天|昨天|前天|明天|后天|(?:\d{4}[-年/.])?\d{1,2}[-月/.]\d{1,2}[日号]?|\d+(?:\.\d+)?\s*(?:元|块|天|小时)|[零一二三四五六七八九十百千万两半]+\s*(?:元|块|天|小时)|不是|改成|改为|改到')
MANUAL={'','手动填写','修改已保存的记工','修改已保存的记工，历史版本将保留。'}
HIGHLIGHTS=re.compile(KEYWORDS.pattern+r'|\d+(?:\.\d+)?')
WORK_FACT=re.compile(r'工资|工钱|单价|加班|借支|预支|到账|收到|结清|结好了|不是|改成|改为|改到|吊顶|搬运|安装|装修|水电|木工|砌墙|铺砖|工地|干活|点工|备注|上班|休息|(?:\d+(?:\.\d+)?|[零一二三四五六七八九十百千万两半]+)\s*(?:元|块|天|小时)')
DATE_ONLY=re.compile(r'(?:今天|昨天|前天|明天|后天|(?:\d{4}[-年/.])?\d{1,2}[-月/.]\d{1,2}[日号]?)')


def selected(text,max_fragments=6):
    if str(text or '').strip() in MANUAL:return [],False
    fragments=[];shortened=False
    # Commas stay inside each sentence so negation and corrected amounts remain together.
    for match in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;]?',str(text)):
        sentence=match.group().strip()
        hits=list(KEYWORDS.finditer(sentence))
        if not hits or not (WORK_FACT.search(sentence) or DATE_ONLY.fullmatch(sentence.rstrip('。！？!?；;'))):continue
        windows=[]
        if len(sentence)<=180:windows=[(0,len(sentence))]
        else:
            shortened=True
            for hit in hits:
                start=max(0,hit.start()-55);end=min(len(sentence),hit.end()+70)
                if windows and start<=windows[-1][1] and end-windows[-1][0]<=180:
                    windows[-1]=(windows[-1][0],end)
                else:windows.append((start,end))
        for start,end in windows:
            value=sentence[start:end];parts=[];offset=0
            for hit in HIGHLIGHTS.finditer(value):
                if hit.start()>offset:parts.append({'text':value[offset:hit.start()],'important':False})
                parts.append({'text':hit.group(),'important':True});offset=hit.end()
            if offset<len(value):parts.append({'text':value[offset:],'important':False})
            fragments.append({'text':value,'parts':parts})
    if len(fragments)>max_fragments:shortened=True
    return fragments[:max_fragments],shortened


def work_source(text,history=()):
    fragments,shortened=selected(text)
    corrections=[]
    for index,change in enumerate(history):
        chosen,trimmed=selected(change.get('instruction',''),2)
        if chosen:corrections.append({'number':index+1,'fragments':chosen,'shortened':trimmed})
    limited=len(corrections)>3
    corrections=corrections[-3:]
    keywords=[]
    for fragment in fragments+[f for c in corrections for f in c['fragments']]:
        for part in fragment['parts']:
            if part['important'] and part['text'] not in keywords and len(part['text'])<=18:
                keywords.append(part['text'])
    return {'fragments':fragments,'corrections':corrections,'keywords':keywords[:12],
            'shortened':shortened,'corrections_shortened':limited,'has_source':bool(fragments or corrections),
            'notice':'以下为输入或语音识别的原句选摘，可能包含已纠正的旧说法；金额和日期以最终确认账目为准。'}

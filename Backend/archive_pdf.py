"""Readable project archive. PDF generation is local; no model or external renderer."""
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import hashlib
import threading

from PIL import Image as PILImage, ImageOps, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, Image, PageBreak, KeepTogether

FONT='GongmingbaiArchive'
FONT_LOCK=threading.Lock()
INK=colors.HexColor('#17232c')
BLUE_HEX='#173b65'
ACCENT=colors.HexColor(BLUE_HEX)
MUTED=colors.HexColor('#657587')
LINE=colors.HexColor('#d2d2ce')
CREAM=colors.HexColor('#f5f0e5')
BEIJING=timezone(timedelta(hours=8))


def register_font():
    with FONT_LOCK:
        if FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT,str(Path(__file__).parent/'fonts'/'ArchiveSans.ttf')))


def china_time(value):
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BEIJING).strftime('%Y年%m月%d日 %H:%M')
    except (ValueError,TypeError):
        return '时间待确认'


def amount(value):
    return f'{int(value or 0)/100:,.2f}'


def render_archive(project, ledger, events, reports, assets, read_asset, generated_at=None):
    register_font()
    output=BytesIO()
    doc=SimpleDocTemplate(output,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=52,bottomMargin=44,
        title='务工档案证据线 - '+project['name'],author='工明白',pageCompression=1)
    styles={
        'title':ParagraphStyle('title',fontName=FONT,fontSize=24,leading=34,textColor=ACCENT,spaceAfter=12,wordWrap='CJK'),
        'heading':ParagraphStyle('heading',fontName=FONT,fontSize=15,leading=23,textColor=ACCENT,spaceBefore=16,spaceAfter=9,keepWithNext=True,wordWrap='CJK'),
        'body':ParagraphStyle('body',fontName=FONT,fontSize=10,leading=16,textColor=INK,spaceAfter=7,wordWrap='CJK',splitLongWords=True),
        'small':ParagraphStyle('small',fontName=FONT,fontSize=8,leading=12,textColor=MUTED,spaceAfter=5,wordWrap='CJK',splitLongWords=True),
        'cell':ParagraphStyle('cell',fontName=FONT,fontSize=9,leading=14,textColor=INK,wordWrap='CJK',splitLongWords=True),
        'tablehead':ParagraphStyle('tablehead',fontName=FONT,fontSize=9,leading=14,textColor=ACCENT,wordWrap='CJK'),
    }
    def p(value,style='body'):
        text=''.join(c for c in str(value if value is not None else '') if ord(c)>=32 or c=='\n')
        return Paragraph(escape(text).replace('\n','<br/>'),styles[style])
    def original(fragment):
        values=[]
        for part in fragment['parts']:
            value=escape(''.join(c for c in part['text'] if ord(c)>=32))
            values.append('<font color="'+BLUE_HEX+'">'+value+'</font>' if part['important'] else value)
        return Paragraph('“'+''.join(values)+'”',styles['small'])
    def table(headers, rows, widths):
        values=[[p(x,'tablehead') for x in headers]]+[[p(x,'cell') for x in row] for row in rows]
        t=LongTable(values,colWidths=widths,repeatRows=1,hAlign='LEFT',splitInRow=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),CREAM),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('GRID',(0,0),(-1,-1),.5,LINE),('LEFTPADDING',(0,0),(-1,-1),8),
            ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        return t
    width=A4[0]-84
    generated_at=generated_at or datetime.now(timezone.utc).isoformat()
    totals=ledger['totals']
    story=[p('务工档案证据线','title'),p(project['name'],'heading'),
        p('老板称呼：'+(project.get('boss') or '未填写')),p('导出时间：'+china_time(generated_at)),
        p('按导出时的已确认账本整理；尚未确认到账的金额不计入已收。'),
        table(['累计工钱（元）','已收 / 借支（元）','当前待收（元）'],[[amount(totals['wage_fen']),amount(totals['advance_fen']),amount(totals['balance_fen'])]],[width/3]*3)]
    pending=sum(r.get('status')=='awaiting_receipt' for r in reports)
    if pending:story.append(p(f'另有{pending}次核账尚待确认，未作为已完成的证据档案收入本文件。','small'))
    story.extend([Spacer(1,8),p('一、已确认记工','heading')])
    entries=sorted(ledger['entries'],key=lambda e:(e.get('date',''),e.get('created_at','')))
    if entries:
        rows=[]
        for entry in entries:
            f=entry['fields']
            detail=f"{f.get('days','')}天 × {f.get('day_rate') or '待核实'}元 / 天"
            if float(f.get('overtime_hours') or 0):detail+=f"\n加班{f['overtime_hours']}小时 × {f.get('overtime_rate') or '待核实'}元 / 小时"
            if f.get('note'):detail+='\n备注：'+f['note']
            rows.append([entry.get('date',''),detail,amount(entry['wage_fen'])])
        story.append(table(['记工日期','工作及备注','工钱（元）'],rows,[86,width-170,84]))
    else:story.append(p('目前没有已确认的记工。'))
    story.append(p('二、已确认收款与借支','heading'))
    payments=sorted(ledger['payments'],key=lambda v:(v.get('date',''),v.get('created_at','')))
    if payments:
        story.append(table(['到账 / 借支日期','类型','金额（元）'],[[v.get('date',''),'借支' if v.get('type')=='advance' else '已收款',amount(v['amount_fen'])] for v in payments],[140,width-224,84]))
    else:story.append(p('目前没有已确认的收款或借支。'))
    # Same original image referenced by more than one event has one appendix number.
    originals=[];by_hash={};refs={}
    for asset in sorted(assets,key=lambda a:(a.get('created_at',''),a['id'])):
        key=asset.get('sha256') or asset['id']
        if key not in by_hash:
            by_hash[key]=f'E{len(originals)+1:03d}';originals.append(asset)
        refs[asset['id']]=by_hash[key]
    story.append(p('三、务工证据时间线','heading'))
    if any(event.get('work_source') for event in events):story.append(p('记工原话仅为当时输入或语音识别的原句选摘；纠正会分开展示，最终金额和日期以已确认账本为准。','small'))
    if events:
        for event in sorted(events,key=lambda v:v.get('created_at','')):
            ref=refs.get(event.get('asset_id'))
            block=[p(china_time(event.get('created_at'))+'  '+event.get('title','记录'))]
            if event.get('summary'):block.append(p(event['summary'],'small'))
            source=event.get('work_source')
            if source:
                if event.get('work_date'):block.append(p('记工日期：'+event['work_date'],'small'))
                if source['has_source']:
                    if source['fragments']:block.append(p('记工原话精选','small'))
                    block.extend(original(fragment) for fragment in source['fragments'])
                    for change in source['corrections']:
                        block.append(p(f"第{change['number']}次纠正精选",'small'))
                        block.extend(original(fragment) for fragment in change['fragments'])
                    if source['shortened'] or source['corrections_shortened']:block.append(p('此处仅列重点选摘，完整原话与纠正记录可在App查看。','small'))
                else:block.append(p('本笔为表单记工，没有可选摘原话。','small'))
            if ref:block.append(p('关联凭据：'+ref,'small'))
            story.append(KeepTogether(block))
    else:story.append(p('目前没有可归档的时间线记录。'))
    story.append(p('四、已完成核账','heading'))
    completed=[r for r in reports if r.get('status','completed')=='completed']
    if completed:
        for i,report in enumerate(sorted(completed,key=lambda r:r.get('created_at','')),1):
            ref=refs.get(report.get('asset_id'))
            story.append(p(f"核账{i} · {china_time(report.get('created_at'))}"+(' · 凭据'+ref if ref else '')))
            if report.get('summary'):story.append(p(report['summary']))
            if report.get('excerpt'):story.append(p('核对摘录：'+report['excerpt']))
            if report.get('rows'):
                story.append(p('以下为当时的核对快照，当前总额以首页汇总为准。','small'))
                story.append(table(['项目','当时账本（元）','对方说明（元）','差额（元）'],[[row['label'],amount(row.get('mine_fen')),'未明确' if row.get('chat_fen') is None else amount(row['chat_fen']),'待核实' if row.get('difference_fen') is None else amount(row['difference_fen'])] for row in report['rows']],[80,(width-80)/3,(width-80)/3,(width-80)/3]))
            for receipt in report.get('receipts',[]):
                status={'confirmed':'本人已确认到账','already_recorded':'已关联账本收款，未重复入账','not_received':'本人确认尚未收到','pending':'待本人核实'}.get(receipt.get('status'),'待核实')
                story.append(p(f"付款信息：{amount(receipt.get('amount_fen'))}元，{receipt.get('date') or '日期待确认'}，{status}。",'small'))
    else:story.append(p('目前没有已完成的核账。'))
    story.append(p('五、归档凭据','heading'))
    story.append(p('截图按原始比例排版，长图分段显示；SHA256对应上传原文件。PDF便于阅读，原文件可另导出ZIP备份。给AI的语音及纠正指令不作为凭据收入。','small'))
    if originals:
        for asset in originals:
            ref=refs[asset['id']]
            raw=read_asset(asset)
            digest=hashlib.sha256(raw).hexdigest()
            if asset.get('sha256') and asset['sha256']!=digest:
                raise ValueError('凭据校验不一致，请稍后重新导出')
            metadata=[p(ref+' · '+asset.get('name','凭据')),
                      p(china_time(asset.get('created_at'))+' · '+asset.get('mime',''),'small'),
                      p('SHA256：'+digest,'small')]
            if not asset.get('mime','').startswith('image/'):
                story.append(KeepTogether(metadata+[p('该类型原件未嵌入PDF，请在应用查看原件或使用ZIP备份。','small')]))
                continue
            try:
                with PILImage.open(BytesIO(raw)) as original:
                    if original.width*original.height>30_000_000:raise ValueError('图片像素过大')
                    image=ImageOps.exif_transpose(original).convert('RGB')
                    if image.width>1600:image=image.resize((1600,max(1,round(image.height*1600/image.width))))
                    # Budget the first image page for its filename, timestamp
                    # and hash, so no metadata-only page is emitted before it.
                    meta_height=sum(value.wrap(width,10000)[1]+value.getSpaceAfter() for value in metadata)
                    page_image_height=max(120,min(620,A4[1]-52-44-48-meta_height))
                    max_height=max(1,int(image.width*page_image_height/width))
                    parts=(image.height+max_height-1)//max_height
                    part_height=(image.height+parts-1)//parts
                    for n,top in enumerate(range(0,image.height,part_height),1):
                        header=[p(ref+f' · 原件图片（{n}/{parts}）','heading')]
                        header += metadata if n==1 else [p(asset.get('name','凭据'),'small')]
                        part=image.crop((0,top,image.width,min(top+part_height,image.height)))
                        data=BytesIO();part.save(data,format='JPEG',quality=90);data.seek(0)
                        draw_width=min(width,part.width)
                        story.extend([PageBreak(),KeepTogether(header+[Image(data,width=draw_width,height=part.height*draw_width/part.width,hAlign='LEFT')])])
            except (UnidentifiedImageError,OSError,ValueError,PILImage.DecompressionBombError):
                story.append(KeepTogether(metadata+[p('这份图片暂无法排入PDF，请在应用查看原件或导出ZIP备份。','small')]))
    else:story.append(p('目前没有已归档的原始凭据。'))
    story.extend([Spacer(1,12),p('整理说明：本档案由工明白按项目现有记录生成，用于查看和核对，不代表对凭据真实性的额外认证。','small')])
    def decorate(canvas,document):
        canvas.saveState();canvas.setStrokeColor(LINE);canvas.line(42,A4[1]-31,A4[0]-42,A4[1]-31)
        canvas.setFont(FONT,8);canvas.setFillColor(MUTED);canvas.drawString(42,A4[1]-23,'工明白 · 务工档案证据线')
        canvas.drawRightString(A4[0]-42,25,f'第 {document.page} 页');canvas.restoreState()
    doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
    return output.getvalue()

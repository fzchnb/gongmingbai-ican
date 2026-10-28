from io import BytesIO
import hashlib
from PIL import Image
from pypdf import PdfReader
import main
from archive_pdf import render_archive
from test_projects import client, setup, FIELDS
from test_workflows import recognize, decision, ledger_setup


def png(height=180):
    buffer=BytesIO();Image.new('RGB',(600,height),'#f1ece0').save(buffer,format='PNG');return buffer.getvalue()


def text(data):
    return '\n'.join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)


def test_pdf_exports_readable_confirmed_ledger_archived_screenshot_and_no_ai_input(client,monkeypatch):
    c=client;h,owner,p=ledger_setup(c)
    image=png();asset,task,report,_=recognize(c,h,p,monkeypatch,image=image)
    assert decision(c,h,report).status_code==200
    c.post('/api/v1/assets?project_id='+p+'&purpose=ai_input',headers=h,files={'file':('不作为证据的语音.mp3',b'private-voice','audio/mpeg')})
    c.post('/api/v1/assets?project_id='+p+'&purpose=reconcile',headers=h,files={'file':('未完成的截图.png',png(181),'image/png')})
    response=c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h)
    assert response.status_code==200,response.text[:200] if response.status_code!=200 else ''
    assert response.headers['content-type']=='application/pdf'
    assert "filename*=UTF-8''" in response.headers['content-disposition']
    assert response.headers['cache-control']=='private, no-store'
    assert response.content.startswith(b'%PDF-')
    content=text(response.content)
    for expected in ['务工档案证据线','务工证据时间线','350.00','140.00','210.00','本人已确认到账',hashlib.sha256(image).hexdigest(),'E001']:
        assert expected in content
    assert '不作为证据的语音' not in content and '未完成的截图' not in content
    reader=PdfReader(BytesIO(response.content))
    assert any(page.images for page in reader.pages)
    # Source metadata must travel with its image, not consume a separate page.
    source_pages=[page for page in reader.pages if 'SHA256：' in page.extract_text()]
    assert source_pages and all(page.images for page in source_pages)
    descriptors=[font.get_object().get('/FontDescriptor') for page in reader.pages for font in page['/Resources']['/Font'].values()]
    assert any(desc and '/FontFile2' in desc.get_object() for desc in descriptors)


def test_pdf_empty_project_and_cross_owner_deleted_project_protection(client):
    c=client;h,owner,p=setup(c)
    own=c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h)
    assert own.status_code==200
    assert '目前没有已确认的记工' in text(own.content)
    other,_,_=setup(c)
    assert c.get('/api/v1/projects/'+p+'/archive.pdf',headers=other).status_code==404
    assert c.get('/api/v1/projects/'+p+'/archive.pdf').status_code==401
    c.delete('/api/v1/projects/'+p+'?confirmed=true',headers=h)
    assert c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h).status_code==404


def test_pdf_wraps_long_notes_names_dates_and_splits_long_images_without_duplicate_originals():
    project={'name':'演示<&>长项目名称'*7,'boss':'张师傅'}
    entries=[{'id':str(i),'date':'2026-10-25','wage_fen':35000,'fields':{**FIELDS,'note':('工作备注与核对事项，'*12)+f'完整记录终点{i}'}} for i in range(35)]
    data=png(4000);digest=hashlib.sha256(data).hexdigest()
    asset={'id':'image','name':'长截图.png','mime':'image/png','created_at':'2026-10-25T01:00:00Z','sha256':digest}
    loaded=[]
    pdf=render_archive(project,{'entries':entries,'payments':[],'totals':{'wage_fen':1225000,'advance_fen':0,'balance_fen':1225000}},
        [{'created_at':'2026-10-24T23:30:00Z','title':'完成核账','asset_id':'image'}],[],[asset,{**asset,'id':'same'}],lambda a:(loaded.append(a['id']) or data))
    reader=PdfReader(BytesIO(pdf));content=text(pdf)
    assert '完整记录终点34' in content and '2026年10月25日 07:30' in content
    assert '演示<&>长项目名称' in content.replace('\n','')
    assert len(reader.pages)>5 and loaded==['image']
    assert 'E002' not in content
    assert all('第 ' in page.extract_text() for page in reader.pages)


def test_pdf_pending_receipt_cannot_become_confirmed_evidence(client,monkeypatch):
    c=client;h,owner,p=ledger_setup(c);recognize(c,h,p,monkeypatch,image=png())
    response=c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h)
    assert response.status_code==200
    content=text(response.content)
    assert '250.00' in content and '1次核账尚待确认' in content
    assert 'transfer.png' not in content and 'E001' not in content


def test_pdf_invalid_legacy_image_has_explicit_placeholder_and_raw_zip_remains_available(client):
    c=client;h,owner,p=setup(c)
    c.post('/api/v1/assets?project_id='+p+'&purpose=evidence',headers=h,files={'file':('旧版图片.png',b'not-a-decodable-image','image/png')})
    response=c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h)
    assert response.status_code==200 and '暂无法排入PDF' in text(response.content)
    assert c.get('/api/v1/projects/'+p+'/export',headers=h).headers['content-type']=='application/zip'


def test_pdf_missing_or_hash_mismatched_original_cannot_return_a_successful_file(client,monkeypatch):
    c=client;h,owner,p=setup(c)
    a=c.post('/api/v1/assets?project_id='+p+'&purpose=evidence',headers=h,files={'file':('photo.png',png(),'image/png')}).json()
    def missing(*args):raise FileNotFoundError('private internal path')
    monkeypatch.setattr(main,'asset_bytes',missing)
    response=c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h)
    assert response.status_code==409 and 'private internal path' not in response.text
    monkeypatch.setattr(main,'asset_bytes',lambda *args:(a,b'changed-content'))
    response=c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h)
    assert response.status_code==409 and '校验不一致' in response.text

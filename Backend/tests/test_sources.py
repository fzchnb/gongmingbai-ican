from test_projects import client, setup, FIELDS
import main


def test_source_text_and_corrections_remain_private_and_deleted_parent_is_closed(client):
    h, owner, project = setup(client)
    draft=client.post('/api/v1/drafts',headers=h,json={'project_id':project,'fields':FIELDS}).json()
    draft.update(source_text='今天做一天350，借支100',revisions=[{'instruction':'借支改80','reply':'已修改','asset_id':None}])
    main.store.put(owner,'drafts',draft)
    path='/api/v1/drafts/'+draft['id']+'/source'
    value=client.get(path,headers=h).json()
    assert value['text']==draft['source_text'] and value['corrections']==draft['revisions']
    assert value['excerpt']['has_source'] and value['excerpt']['fragments'][0]['text']==draft['source_text']
    other,_,_=setup(client)
    assert client.get(path,headers=other).status_code==404
    assert client.get(path).status_code==401
    client.delete('/api/v1/projects/'+project+'?confirmed=true',headers=h)
    assert client.get(path,headers=h).status_code==404

import json
import ai


def test_perception_is_separate_from_history_and_reasoning_cannot_change_money(monkeypatch):
    calls=[]
    def call(model,messages):
        calls.append(messages)
        if len(calls)==1:
            return json.dumps({'visible_text':'2026年10月25日 王师傅：转你40元',
                'wage':'350','advance':'100','balance':'250','field_evidence':{},
                'payments':[{'amount':'40','date':'2026-10-25','kind':'transfer','evidence':'转你40元'}]})
        return json.dumps({'explanation':'本项目已记一天工，本次转账请你确认到账。','balance':'999'})
    monkeypatch.setattr(ai,'call',call)
    result=ai.vision(b'image','image/png',{'project':{'id':'only-this-project'},'totals':{'balance_fen':25000}})
    assert len(calls)==2
    assert '25000' not in json.dumps(calls[0]) and '25000' in json.dumps(calls[1])
    assert all(result[k] is None for k in ('wage','advance','balance'))
    assert result['payments'][0]['amount']=='40' and '本项目' in result['explanation']


def test_message_style_allows_colloquial_yixia_but_rejects_invented_money(monkeypatch):
    monkeypatch.setattr(ai,'call',lambda *_:json.dumps({'opening':'想跟您对一下工钱。','closing':'咱们有空一起看看。'}))
    assert ai.message_style({})['opening']=='想跟您对一下工钱。'
    monkeypatch.setattr(ai,'call',lambda *_:json.dumps({'opening':'还差四十元。','closing':'谢谢。'}))
    import pytest
    with pytest.raises(ValueError):
        ai.message_style({})

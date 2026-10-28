import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from test_api import env,login,submit
from backend.engine import ComfyEngine,EngineError
from backend.config import Settings

@pytest.mark.parametrize('ratio,size',[('1:1',(512,512)),('16:9',(768,432)),('9:16',(432,768))])
def test_job_aspect_persisted_and_forwarded(env,ratio,size):
    app,c=env;h=login(c);r=submit(c,h,aspect_ratio=ratio)
    assert r.status_code==201,r.text
    j=r.json();assert (j['width'],j['height'])==size;assert j['aspect_ratio']==ratio
    stored=app.state.db.one('SELECT * FROM jobs WHERE id=?',(j['id'],))
    assert (stored['width'],stored['height'])==size
    graph=ComfyEngine(app.state.settings).workflow(stored)
    assert (graph['6']['inputs']['width'],graph['6']['inputs']['height'])==size
    assert c.get('/api/jobs/'+j['id']).json()['aspect_ratio']==ratio


def test_unsupported_aspect_rejected_and_default_compatible(env):
    _,c=env;h=login(c)
    assert submit(c,h,aspect_ratio='4:3').status_code==422
    assert submit(c,h,aspect_ratio='auto').status_code==422
    assert submit(c,h,width=4096,height=4096).status_code==422
    assert submit(c,h).json()['aspect_ratio']=='1:1'

@pytest.mark.parametrize('size',[(768,432),(432,768)])
def test_engine_checks_actual_png_dimensions(tmp_path,size):
    import shutil
    from PIL import Image
    root=tmp_path/'inference';(root/'output').mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[2]/'workflow-api-8steps.json',root/'workflow-api-8steps.json')
    engine=ComfyEngine(Settings(root=root,data_dir=tmp_path/'private',worker_enabled=False))
    job={'id':'aspect-check','steps':8,'seed':42,'prompt':'red teapot','width':size[0],'height':size[1]}
    Image.new('RGB',size,'red').save(root/'output/result.png')
    history={'status':{'status_str':'success','completed':True},'outputs':{'10':{'images':[{'filename':'result.png','subfolder':'','type':'output'}]}}}
    result=engine.save_result(job,history,1)
    with Image.open(tmp_path/'private'/result['image_path']) as im:assert im.size==size
    Image.new('RGB',(512,512),'red').save(root/'output/result.png')
    with pytest.raises(EngineError):engine.save_result(job,history,1)


def test_engine_rejects_unapproved_dimensions(env):
    app,_=env;engine=ComfyEngine(app.state.settings)
    with pytest.raises(ValueError):engine.workflow({'id':'bad-size','steps':8,'seed':42,'prompt':'teapot','width':4096,'height':4096})

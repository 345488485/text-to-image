"""Generate two real aspect-ratio images through the production queue using a disabled-after-test fixture account."""
import sys,json,secrets,time,io,hashlib,http.cookiejar,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.db import Database
from backend.security import create_user
from PIL import Image
R=Path(__file__).resolve().parents[2]
s=Settings();db=Database(s.db_path);name='verify_shapes_'+secrets.token_hex(4);password=secrets.token_urlsafe(24);uid=create_user(db,name,password)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path,payload=None,csrf=None):
 data=None if payload is None else json.dumps(payload).encode();headers={'Content-Type':'application/json'}
 if csrf:headers['X-CSRF-Token']=csrf
 req=urllib.request.Request('http://127.0.0.1:8000'+path,data=data,headers=headers)
 with opener.open(req,timeout=20) as res:
  b=res.read();return json.loads(b) if res.headers.get('Content-Type','').startswith('application/json') else b
results=[]
try:
 session=call('/api/auth/login',{'username':name,'password':password});csrf=session['csrf_token']
 for ratio,size,label in [('16:9',(768,432),'desktop'),('9:16',(432,768),'mobile')]:
  job=call('/api/jobs',{'prompt':'A red ceramic teapot on a wooden table, soft daylight, product photography, clean background.','steps':8,'seed':42,'aspect_ratio':ratio},csrf)
  print('QUEUED',ratio,job['id'],flush=True);deadline=time.monotonic()+900
  while time.monotonic()<deadline:
   job=call('/api/jobs/'+job['id'])
   if job['status']=='failed':raise RuntimeError(json.dumps(job,ensure_ascii=False))
   if job['status']=='succeeded':break
   time.sleep(2)
  else:raise TimeoutError('Aspect test timed out')
  raw=call(job['image_url'])
  with Image.open(io.BytesIO(raw)) as im:assert im.size==size;im.verify()
  assert (job['width'],job['height'])==size and job['aspect_ratio']==ratio
  path=R/'platform/logs'/('aspect-'+label+'.png');path.write_bytes(raw)
  results.append({'ratio':ratio,'width':size[0],'height':size[1],'job_id':job['id'],'seconds':job['elapsed_seconds'],'image':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
  print('SUCCESS',ratio,job['elapsed_seconds'],flush=True)
finally:
 db.execute('UPDATE users SET is_active=0 WHERE id=?',(uid,));db.execute('DELETE FROM sessions WHERE user_id=?',(uid,));db.execute("UPDATE jobs SET status='cancelled' WHERE owner_id=? AND status='queued'",(uid,))
report={'status':'success','results':results,'fixture_user_disabled':True,'real_account_password_untouched':True};(R/'platform/logs/aspect-live.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2),flush=True)

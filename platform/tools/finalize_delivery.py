"""Finalize source-only delivery evidence; never modify models or user data."""
from pathlib import Path
import base64,difflib,hashlib,json,os,subprocess,time,zipfile
R=Path(__file__).resolve().parents[2]; D=R/'.runtime/transfer-fix'
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):
 return subprocess.check_output(['git','-C',str(R/'platform/frontend'),*args])
# Existing transaction remains authoritative; add only a new platform entrypoint mode.
rb=D/'ROLLBACK.sh';s=rb.read_text(encoding='utf-8')
if 'platform-entry' not in s:
 s=s.replace('#!/bin/sh\n','#!/bin/sh\nif [ "${2:-}" = "platform-entry" ]; then\n    : > "$1"\n    exit 0\nfi\n',1)
 rb.write_text(s,encoding='utf-8',newline='\n')
T=D/'platform-entry';T.mkdir(exist_ok=True)
(T/'baseline.py').write_bytes(b'');(T/'modified.py').write_bytes((R/'platform/serve.py').read_bytes());(T/'rollback.py').write_bytes((R/'platform/serve.py').read_bytes())
probe=T/'probe.py';probe.write_text('import runpy,sys\nm=runpy.run_path(sys.argv[1],run_name="transaction_probe")\nprint("platform_entrypoint="+str(callable(m.get("main"))))\n',encoding='utf-8')
# Coherent patch includes the previous nine-file transaction and new platform changes.
pairs=[]
def pair(name,before,after=None):
 pairs.append((name,before,(R/name).read_bytes() if after is None else after))
pair('download_models_resumable.py',(R/'download_models.py').read_bytes())
pair('.venv/Lib/site-packages/sitecustomize.py',b'')
pair('.runtime/requirements-minimal.txt',(R/'.runtime/source/ComfyUI-master/requirements.txt').read_bytes())
pair('start-moss-compatible.ps1',(R/'start-moss.ps1').read_bytes())
for name in ['run_moss_compatible.py','workflow-api-16steps.json','smoke_test_steps16.py','workflow-api-8steps.json','smoke_test_steps8.py']:pair(name,None)
custom=[R/'start-platform.ps1',R/'start.bat',R/'.gitignore']
custom += [p for p in (R/'platform/backend').glob('*.py')]
custom += [p for p in (R/'platform/tests').iterdir() if p.suffix in ('.py','.cjs')]
custom += [p for p in (R/'platform/tools').glob('*.py')]
custom += [R/'platform'/n for n in ['serve.py','start-frontend.ps1','README.md','.env.example','requirements.txt','requirements-lock.txt']]
custom += [p for p in (R/'platform/frontend/apps/moss').rglob('*') if p.is_file() and not {'node_modules','dist','.vite','__pycache__'}.intersection(p.relative_to(R/'platform/frontend/apps/moss').parts)]
custom += [R/'platform/frontend'/n for n in ['MOSS-UPSTREAM.md','UPSTREAM.package.json','FRONTEND-VERIFICATION.json']]
for p in sorted(set(custom)):pair(p.relative_to(R).as_posix(),None)
for name in git('diff','--name-only','HEAD').decode().splitlines():pair('platform/frontend/'+name,git('show','HEAD:'+name))
stage=D/('delivery-replay-'+str(int(time.time())));stage.mkdir()
chunks=[];manifest=[]
for name,before,after in pairs:
 if before is not None:
  p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(before)
 chunks.append(''.join(difflib.unified_diff((before or b'').decode('utf-8').splitlines(True),after.decode('utf-8').splitlines(True),fromfile='a/'+name if before is not None else '/dev/null',tofile='b/'+name)))
 manifest.append({'path':name,'sha256':sha(after),'bytes':len(after)})
(D/'DIFF.patch').write_text(''.join(chunks),encoding='utf-8',newline='\n')
(D/'delivery-replay.json').write_text(json.dumps({'stage':str(stage),'files':manifest},indent=2),encoding='utf-8')
# Source bundle contains upstream MIT sources + custom app, never DBs, credentials, logs or node_modules.
archive_files={p for p in custom if p.is_file()}
for name in git('ls-files').decode().splitlines():
 p=R/'platform/frontend'/name
 if p.is_file():archive_files.add(p)
for p in (R/'platform/frontend/apps/moss/dist').rglob('*'):
 if p.is_file():archive_files.add(p)
for name in ['run_moss_compatible.py','start-moss-compatible.ps1','extra_model_paths.yaml','workflow-api.json','workflow-api-8steps.json','workflow-api-16steps.json']:archive_files.add(R/name)
archive=R/'platform/moss-studio-source.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(archive_files):z.write(p,p.relative_to(R).as_posix())
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
report={'archive':str(archive),'archive_sha256':sha(archive.read_bytes()),'archive_bytes':archive.stat().st_size,'source_files':len(archive_files),'patch_files':len(manifest),'patch_sha256':sha((D/'DIFF.patch').read_bytes()),'replay':str(stage),'upstream_commit':git('rev-parse','HEAD').decode().strip(),'scope':'Source and frontend dist only; no model weights, environments, databases, logs or production credentials'}
(R/'platform/DELIVERY.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))

"""Recreate local inference DLL isolation from installed files; never replace global DLLs."""
from pathlib import Path
import os,shutil,sys,json
r=Path(__file__).resolve().parents[2];t=r/'.runtime/inference-python';t.mkdir(exist_ok=True)
base=Path(sys.base_prefix)
for name in ['python.exe',f'python{sys.version_info.major}{sys.version_info.minor}.dll','python3.dll']:
    shutil.copy2(base/name,t/name)
for name in ['VCRUNTIME140.dll','VCRUNTIME140_1.dll']:
    shutil.copy2(Path(os.environ['SystemRoot'])/'System32'/name,t/name)
(t/'pyvenv.cfg').write_text(f'home = {base}\ninclude-system-site-packages = false\n',encoding='utf-8')
b=t/'bootstrap';b.mkdir(exist_ok=True)
dirs=[str(base),str(base/'DLLs'),str(base/'Library/bin')]
source='import os\n_dll_dirs=[os.add_dll_directory(p) for p in '+repr(dirs)+' if os.path.isdir(p)]\nimport ctypes\n_msvc=ctypes.WinDLL(os.path.join(os.environ["SystemRoot"],"System32","msvcp140.dll"))\n'
(b/'sitecustomize.py').write_text(source,encoding='utf-8')
print(str(t))

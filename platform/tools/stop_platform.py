"""Stop verified platform process trees without CIM/WMI or taskkill."""
import argparse,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.winprocess import windows_command_line,watch_windows_tree

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--listener',type=int,action='append',default=[]);p.add_argument('--recorded',type=int,action='append',default=[]);a=p.parse_args()
    base=re.escape(str(Path(a.root).resolve()).replace('\\','/'))
    pattern=base+r'/platform/(?:serve\.py|start-frontend\.ps1|frontend/.*?/vite/bin/vite\.js)(?:["\s]|$)'
    verified=[]
    for pid in dict.fromkeys(a.listener+a.recorded):
        command=windows_command_line(pid)
        valid=command and re.search(pattern,command.replace('\\','/'),re.I)
        if not valid:
            if pid in a.listener: raise SystemExit('Refusing unrelated listener PID '+str(pid))
            continue
        verified.append(pid)
    for pid in verified:
        if windows_command_line(pid) is None: continue
        with watch_windows_tree(pid) as stopped:
            stopped.terminate()
            if not stopped(): raise SystemExit('Owned tree exit unconfirmed: '+str(pid))
        print('Stopped verified platform tree PID='+str(pid),flush=True)
if __name__=='__main__': main()

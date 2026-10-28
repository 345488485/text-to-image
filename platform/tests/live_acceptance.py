"""Real GPU acceptance against a separate QA database. Never used as production credentials."""
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request
import http.cookiejar

ROOT = Path(__file__).resolve().parents[2]
HOST = 'http://127.0.0.1:8000'
QA_PASSWORD = 'QA-only-local-fixture-42!'


def client(name):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
    def call(path, payload=None, method=None, csrf=None):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {'Content-Type': 'application/json'}
        if csrf:
            headers['X-CSRF-Token'] = csrf
        req = urllib.request.Request(HOST+path, data=body, method=method, headers=headers)
        with opener.open(req, timeout=20) as response:
            data = response.read()
            return json.loads(data) if response.headers.get('Content-Type','').startswith('application/json') else data
    session = call('/api/auth/login', {'username':name, 'password':QA_PASSWORD})
    return call, session['csrf_token']


def main():
    alice, a = client('qa_alice')
    bravo, b = client('qa_bravo')
    initial_counts = [alice('/api/jobs')['total'], bravo('/api/jobs')['total']]
    jobs = []
    for call, csrf, owner, prompt in [(alice,a,'qa_alice','A red ceramic teapot on a wooden table, soft daylight, product photography.'),
                                     (bravo,b,'qa_bravo','A blue ceramic coffee cup on a wooden table, soft daylight, product photography.')]:
        j = call('/api/jobs', {'prompt':prompt, 'steps':8, 'seed':42}, csrf=csrf)
        jobs.append((call,j['id'],owner))
        print('QUEUED',owner,j['id'],flush=True)
    assert alice('/api/jobs')['total'] == initial_counts[0] + 1
    assert bravo('/api/jobs')['total'] == initial_counts[1] + 1
    try:
        alice('/api/jobs/'+jobs[1][1])
        raise AssertionError('Cross-user access allowed')
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    deadline = time.monotonic()+900
    results = {}
    while time.monotonic() < deadline:
        states=[]
        for call,jid,owner in jobs:
            job=call('/api/jobs/'+jid)
            states.append(job['status'])
            if job['status'] == 'failed':
                raise RuntimeError(json.dumps(job,ensure_ascii=False))
            if job['status']=='succeeded' and jid not in results:
                raw=call(job['image_url'])
                downloaded=call(job['image_url']+'?download=true')
                assert raw==downloaded and raw.startswith(b'\x89PNG\r\n\x1a\n')
                results[jid]={'owner':owner,'job':job,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                print('SUCCEEDED',owner,job['elapsed_seconds'],flush=True)
        assert states.count('running') <= 1,states
        if len(results)==2:
            first,second=(results[j[1]]['job'] for j in jobs)
            assert first['finished_at'] <= second['started_at'], 'GPU jobs overlapped'
            result={'status':'success','cross_user_access':404,'max_running':1,'consecutive_real_generations':2,'jobs':list(results.values())}
            path=ROOT/'platform/logs/live-acceptance.json'
            path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
            print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)
            return
        time.sleep(3)
    raise TimeoutError('Real GPU acceptance did not finish in15minutes')


if __name__=='__main__':
    main()

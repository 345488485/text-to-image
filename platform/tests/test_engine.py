import hashlib
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.db import Database


def engine_class():
    from backend.engine import ComfyEngine
    return ComfyEngine


@pytest.fixture
def env(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    original = Path(__file__).resolve().parents[2] / 'workflow-api-8steps.json'
    (root / 'workflow-api-8steps.json').write_bytes(original.read_bytes())
    (root / 'output').mkdir()
    return Settings(root=root, data_dir=tmp_path / 'private')


def job(**changes):
    return dict(id='abc123', prompt='red teapot', negative_prompt='blur', steps=16, seed=42, **changes)


def test_fixed_workflow_rejects_arbitrary_parameters(env):
    engine = engine_class()(env)
    graph = engine.workflow(job())
    assert graph['4']['inputs']['text'] == 'red teapot'
    assert graph['5']['inputs']['text'] == 'blur'
    assert graph['8']['inputs']['steps'] == 16
    assert graph['6']['inputs'] == {'width': 512, 'height': 512, 'batch_size': 1}
    invalid = job(); invalid['steps'] = 7
    with pytest.raises(ValueError):
        engine.workflow(invalid)
    invalid = job(); invalid['id'] = '../escape'
    with pytest.raises(ValueError):
        engine.workflow(invalid)


def test_png_copy_only_trusted_save_node_and_output_directory(env):
    engine = engine_class()(env)
    source = env.root / 'output' / 'good.png'
    Image.new('RGB', (512, 512), 'red').save(source)
    history = {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {'10': {'images': [{'filename': 'good.png', 'subfolder': '', 'type': 'output'}]}}}
    result = engine.save_result(job(), history, 1.5)
    assert result['image_path'] == 'images/abc123.png'
    assert (env.data_dir / result['image_path']).read_bytes() == source.read_bytes()
    assert result['image_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    history['outputs']['10']['images'][0]['filename'] = '../outside.png'
    with pytest.raises(Exception):
        engine.save_result(job(), history, 0)
    history['outputs'] = {'9': {'images': [{'filename': 'good.png', 'type': 'output'}]}}
    with pytest.raises(Exception):
        engine.save_result(job(), history, 0)


def test_generate_records_id_before_submission_and_frees_before_prompt(env):
    engine = engine_class()(env)
    calls = []
    history = {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {'10': {'images': [{'filename': 'ok.png', 'subfolder': '', 'type': 'output'}]}}}
    Image.new('RGB', (512, 512)).save(env.root / 'output' / 'ok.png')
    def request(path, payload=None):
        calls.append((path, payload))
        if path == '/system_stats': return {'system': {}}
        if path == '/queue': return {'queue_running': [], 'queue_pending': []}
        if path == '/prompt':
            assert calls[-2][0] == 'persist'
            return {'prompt_id': payload['prompt_id']}
        if path.startswith('/history/'): return {path.split('/')[-1]: history}
        return {}
    engine._request = request
    engine._cleanup_wait = 0
    result = engine.generate(job(), lambda pid: calls.append(('persist', pid)), threading.Event())
    assert result['image_path'] == 'images/abc123.png'
    paths = [entry[0] for entry in calls]
    assert paths.index('/free') < paths.index('/prompt')


def test_timeout_interrupts_only_own_prompt_and_blocks_when_unconfirmed(env):
    from backend.engine import EngineUnsafe
    engine = engine_class()(env)
    engine._cancel_timeout = 0
    seen = []
    def request(path, payload=None):
        seen.append((path, payload))
        if path == '/queue': return {'queue_running': [[0, 'owned']], 'queue_pending': []}
        return {}
    engine._request = request
    with pytest.raises(EngineUnsafe): engine.cancel('owned')
    assert ('/api/jobs/owned/cancel', {}) in seen
    assert all(path != '/interrupt' for path, _ in seen)
    assert all(payload != {'clear': True} for _, payload in seen)


def test_restart_recovery_adopts_completed_history_without_resubmit(env):
    engine = engine_class()(env)
    history = {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {'10': {'images': [{'filename': 'ok.png', 'subfolder': '', 'type': 'output'}]}}}
    Image.new('RGB', (512, 512)).save(env.root / 'output' / 'ok.png')
    paths = []
    def request(path, payload=None):
        paths.append(path)
        return {'old': history} if path == '/history/old' else {'queue_running': [], 'queue_pending': []}
    engine._request = request
    recovered = job(prompt_id='old')
    result = engine.resume(recovered, threading.Event())
    assert result['image_path'] == 'images/abc123.png'
    assert '/prompt' not in paths


def make_db(env):
    db = Database(env.db_path)
    db.execute("INSERT INTO users(id,username,password_hash,role,is_active,created_at) VALUES ('u','alice','hash','user',1,'now')")
    for ident in ('first', 'second'):
        db.execute("INSERT INTO jobs(id,owner_id,prompt,steps,seed,status,created_at) VALUES (?,'u','test',8,42,'queued',?)", (ident, ident))
    return db


def test_worker_serial_persistence_and_sanitized_failures(env):
    from backend.worker import run_worker
    db = make_db(env)
    stop = threading.Event()
    order = []
    class FakeEngine:
        def __init__(self, settings): pass
        def online(self): return True
        def queue(self): return {'queue_running': [], 'queue_pending': []}
        def generate(self, item, on_prompt, stop_event):
            order.append(item['id'])
            assert db.one("SELECT count(*) AS n FROM jobs WHERE status='running'")['n'] == 1
            on_prompt('prompt-' + item['id'])
            if item['id'] == 'first': raise RuntimeError('secret token C:/private/model traceback')
            stop.set()
            return {'image_path': 'images/second.png', 'image_sha256': 'a'*64, 'elapsed_seconds': 2.0}
        def close(self): pass
    with patch('backend.worker.ComfyEngine', FakeEngine): run_worker(db, env, stop)
    assert order == ['first', 'second']
    first = db.one("SELECT * FROM jobs WHERE id='first'")
    second = db.one("SELECT * FROM jobs WHERE id='second'")
    assert first['status'] == 'failed' and 'secret' not in first['error'] and 'private' not in first['error']
    assert second['status'] == 'succeeded' and second['prompt_id'] == 'prompt-second'


def test_cancelled_queue_job_never_runs(env):
    from backend.worker import claim_next
    db = make_db(env)
    db.execute("UPDATE jobs SET status='cancelled' WHERE id='first'")
    assert claim_next(db)['id'] == 'second'
    assert claim_next(db) is None

@pytest.mark.parametrize('size,format', [((256, 512), 'PNG'), ((512, 512), 'JPEG')])
def test_invalid_png_dimensions_or_format_are_not_published(env, size, format):
    engine = engine_class()(env)
    Image.new('RGB', size).save(env.root / 'output' / 'bad.png', format=format)
    history = {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {'10': {'images': [{'filename': 'bad.png', 'subfolder': '', 'type': 'output'}]}}}
    with pytest.raises(Exception): engine.save_result(job(), history, 0)
    assert not (env.data_dir / 'images' / 'abc123.png').exists()


def test_worker_halts_with_durable_running_id_after_unconfirmed_stop(env):
    from backend.worker import run_worker
    from backend.engine import EngineUnsafe
    db = make_db(env)
    class UnsafeEngine:
        def __init__(self, settings): pass
        def online(self): return True
        def queue(self): return {'queue_running': [], 'queue_pending': []}
        def generate(self, item, on_prompt, stop_event):
            on_prompt('durable-id')
            raise EngineUnsafe('任务停止未确认')
        def close(self): pass
    with patch('backend.worker.ComfyEngine', UnsafeEngine): run_worker(db, env, threading.Event())
    assert db.one("SELECT * FROM jobs WHERE id='first'")['prompt_id'] == 'durable-id'
    assert db.one("SELECT * FROM jobs WHERE id='first'")['status'] == 'running'
    assert db.one("SELECT * FROM jobs WHERE id='second'")['status'] == 'queued'


def test_worker_adopts_running_job_before_claiming_new_work(env):
    from backend.worker import run_worker
    db = make_db(env)
    db.execute("UPDATE jobs SET status='running',prompt_id='old' WHERE id='first'")
    stop = threading.Event()
    operations = []
    class RecoverEngine:
        def __init__(self, settings): pass
        def online(self): return True
        def queue(self): return {'queue_running': [], 'queue_pending': []}
        def resume(self, item, event):
            operations.append(('resume', item['id']))
            return {'image_path': 'images/first.png', 'image_sha256': 'a'*64, 'elapsed_seconds': 2}
        def generate(self, item, on_prompt, event):
            operations.append(('generate', item['id']))
            event.set()
            return {'image_path': 'images/second.png', 'image_sha256': 'b'*64, 'elapsed_seconds': 3}
        def close(self): pass
    with patch('backend.worker.ComfyEngine', RecoverEngine): run_worker(db, env, stop)
    assert operations == [('resume', 'first'), ('generate', 'second')]
    assert db.one("SELECT count(*) AS n FROM jobs WHERE status='succeeded'")['n'] == 2


def test_submission_transport_error_cancels_persisted_id_before_failing(env):
    engine = engine_class()(env)
    engine._cleanup_wait = 0
    events = []
    def request(path, payload=None):
        if path == '/system_stats': return {'system': {}}
        if path == '/queue' and payload is None: return {'queue_running': [], 'queue_pending': []}
        events.append((path, payload))
        if path == '/prompt': raise TimeoutError('Ambiguous HTTP response')
        return {}
    engine._request = request
    with pytest.raises(Exception):
        engine.generate(job(), lambda pid: events.append(('persist', pid)), threading.Event())
    persisted = next(payload for path, payload in events if path == 'persist')
    assert ('/api/jobs/' + persisted + '/cancel', {}) in events
    assert all(path != '/interrupt' for path, _ in events)


def test_shutdown_of_external_service_does_not_kill_any_process(env):
    engine = engine_class()(env)
    with patch('backend.engine.subprocess.Popen') as popen:
        engine.close()
        popen.assert_not_called()


def test_worker_offline_keeps_jobs_queued(env):
    from backend.worker import run_worker
    db = make_db(env)
    stop = threading.Event()
    class OfflineEngine:
        def __init__(self, settings): pass
        def online(self): stop.set(); return False
        def close(self): pass
    with patch('backend.worker.ComfyEngine', OfflineEngine): run_worker(db, env, stop)
    assert db.one("SELECT count(*) AS n FROM jobs WHERE status='queued'")['n'] == 2

@pytest.mark.skipif(sys.platform != 'win32', reason='Windows process-tree ownership')
def test_close_terminates_only_owned_windows_process_tree(env):
    from unittest.mock import Mock
    engine = engine_class()(env)
    owned = Mock(pid=123456)
    owned.poll.return_value = None
    engine._process = owned
    from contextlib import nullcontext
    with patch('backend.engine.watch_windows_tree', return_value=nullcontext(Mock(return_value=True))), patch('backend.engine.subprocess.run') as run:
        run.return_value.returncode = 0
        engine.close()
    run.assert_not_called()
    assert engine._process is None
    owned.wait.assert_called()


def test_claim_tie_uses_insertion_order_matching_queue_position(env):
    from backend.worker import claim_next
    db = make_db(env)
    db.execute("DELETE FROM jobs")
    for ident in ('z-first', 'a-second'):
        db.execute("INSERT INTO jobs(id,owner_id,prompt,steps,seed,status,created_at) VALUES (?,'u','test',8,42,'queued','same')", (ident,))
    assert claim_next(db)['id'] == 'z-first'


def test_owned_service_restarts_before_second_job_without_free_delay(env):
    from unittest.mock import Mock
    engine = engine_class()(env)
    env.engine_autostart = True
    events = []
    process = Mock()
    process.poll.return_value = None
    engine._process = process
    def ready(stop):
        if engine._process is None:
            events.append('start')
            engine._process = process
            engine._has_generated = False
        return True
    def close():
        events.append('close')
        engine._process = None
    def request(path, payload=None):
        events.append(path)
        if path == '/queue': return {'queue_running': [], 'queue_pending': []}
        if path == '/prompt': return {'prompt_id': payload['prompt_id']}
        return {}
    engine.ensure_ready = ready
    engine.close = close
    engine._request = request
    engine._wait_result = lambda *args: {'image_path': 'images/abc123.png'}
    stop = Mock()
    stop.is_set.return_value = False
    stop.wait.return_value = False
    engine.generate(job(), lambda pid: None, stop)
    engine.generate(job(), lambda pid: None, stop)
    assert events.count('close') == 1
    assert events.count('start') == 1
    assert events.index('/prompt') < events.index('close') < events.index('start') < len(events) - 1
    assert events[-1] == '/prompt'
    assert '/free' not in events
    stop.wait.assert_not_called()


def test_reset_used_owned_service_refuses_busy_global_queue(env):
    from backend.engine import EngineUnsafe
    from unittest.mock import Mock
    engine = engine_class()(env)
    engine._process = Mock()
    engine._process.poll.return_value = None
    engine._has_generated = True
    engine.queue = lambda: {'queue_running': [[1, 'someone-else']], 'queue_pending': []}
    engine.close = Mock()
    with pytest.raises(EngineUnsafe): engine.reset_if_used(threading.Event())
    engine.close.assert_not_called()


def test_reset_never_restarts_external_service(env):
    from unittest.mock import Mock
    engine = engine_class()(env)
    engine._has_generated = True
    engine.close = Mock()
    assert engine.reset_if_used(threading.Event()) is False
    engine.close.assert_not_called()


def test_recover_rechecks_history_when_completion_races_queue_snapshot(env):
    engine = engine_class()(env)
    finished = {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {}}
    history_reads = []
    def request(path, payload=None):
        if path == '/history/racing':
            history_reads.append(path)
            return {} if len(history_reads) == 1 else {'racing': finished}
        assert path == '/queue'
        return {'queue_running': [], 'queue_pending': []}
    engine._request = request
    result = engine.recover('racing')
    assert result == {'state': 'completed', 'history': finished}


def test_atomic_cancel_endpoint_missing_fails_closed_without_interrupt_fallback(env):
    from backend.engine import EngineUnsafe
    from urllib.error import HTTPError
    from unittest.mock import Mock
    engine = engine_class()(env)
    engine._process = Mock()
    engine.close = Mock()
    paths = []
    def request(path, payload=None):
        paths.append(path)
        if path == '/api/jobs/owned/cancel':
            raise HTTPError(path, 404, 'Not Found', {}, None)
        return {'queue_running': [], 'queue_pending': []}
    engine._request = request
    with pytest.raises(EngineUnsafe): engine.cancel('owned')
    assert paths == ['/api/jobs/owned/cancel']
    engine.close.assert_not_called()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows process-tree ownership')
def test_close_tolerates_taskkill_race_only_when_entire_owned_tree_exited(env):
    from unittest.mock import Mock
    from contextlib import contextmanager
    engine = engine_class()(env)
    owned = Mock(pid=123456); owned.poll.return_value = None
    engine._process = owned
    @contextmanager
    def watch(pid):
        assert pid == 123456
        yield Mock(return_value=True)
    with patch('backend.engine.watch_windows_tree', watch, create=True), patch('backend.engine.subprocess.run') as run:
        run.return_value.returncode = 128
        engine.close()
    assert engine._process is None
    owned.wait.assert_called()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows process-tree ownership')
def test_close_still_halts_if_owned_descendant_survives(env):
    from unittest.mock import Mock
    from contextlib import contextmanager
    from backend.engine import EngineUnsafe
    engine = engine_class()(env)
    owned = Mock(pid=123456); owned.poll.return_value = None
    engine._process = owned
    @contextmanager
    def watch(pid):
        yield Mock(return_value=False)
    with patch('backend.engine.watch_windows_tree', watch, create=True), patch('backend.engine.subprocess.run') as run:
        run.return_value.returncode = 1
        with pytest.raises(EngineUnsafe): engine.close()
    assert engine._process is owned


def test_result_poll_tolerates_transient_loading_timeouts_without_resubmit(env):
    from unittest.mock import Mock
    engine = engine_class()(env)
    engine.recover = Mock(side_effect=[TimeoutError('model loading'), {'state':'completed','history':{'ok':True}}])
    engine.save_result = Mock(return_value={'image_path':'fixture.png'})
    stop = Mock(); stop.is_set.return_value=False
    result = engine._wait_result(job(), 'persisted-id', stop, __import__('time').monotonic())
    assert result == {'image_path':'fixture.png'}
    assert engine.recover.call_count == 2
    stop.wait.assert_called_once_with(1)

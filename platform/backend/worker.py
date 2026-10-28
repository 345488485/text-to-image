"""One durable SQLite consumer. Unsafe GPU state stops dispatch, never resubmits."""
from datetime import datetime, timezone
import logging

from .engine import ComfyEngine, EngineError, EngineUnsafe

log = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def claim_next(db):
    with db.transaction() as connection:
        if connection.execute("SELECT 1 FROM jobs WHERE status='running' LIMIT 1").fetchone():
            return None
        item = connection.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1").fetchone()
        if item is None:
            return None
        started = now()
        connection.execute("UPDATE jobs SET status='running',started_at=?,error=NULL WHERE id=? AND status='queued'", (started, item['id']))
        result = dict(item)
        result.update(status='running', started_at=started)
        return result


def finish(db, job_id, result):
    finished = now()
    row = db.one('SELECT started_at FROM jobs WHERE id=?', (job_id,))
    elapsed = result['elapsed_seconds']
    if row and row['started_at']:
        elapsed = max(0, (datetime.fromisoformat(finished) - datetime.fromisoformat(row['started_at'])).total_seconds())
    db.execute("UPDATE jobs SET status='succeeded',finished_at=?,error=NULL,image_path=?,image_sha256=?,elapsed_seconds=? WHERE id=? AND status='running'",
               (finished, result['image_path'], result['image_sha256'], round(elapsed, 3), job_id))


def run_worker(db, settings, stop_event):
    engine = ComfyEngine(settings)
    try:
        recovered = False
        while not stop_event.is_set():
            try:
                if hasattr(engine, 'ensure_ready'):
                    ready = engine.ensure_ready(stop_event)
                else:
                    ready = engine.online()
                if not ready:
                    stop_event.wait(1)
                    continue
                if not recovered:
                    for item in db.all("SELECT * FROM jobs WHERE status='running' ORDER BY started_at,id"):
                        execute(db, engine, item, stop_event, resume=True)
                    recovered = True
                if stop_event.is_set():
                    break
                # Other local clients can use ComfyUI; do not overlap or interrupt their jobs.
                queue = engine.queue()
                if queue['queue_running'] or queue['queue_pending']:
                    stop_event.wait(1)
                    continue
                item = claim_next(db)
                if item is None:
                    stop_event.wait(1)
                    continue
                execute(db, engine, item, stop_event)
            except EngineUnsafe as exc:
                log.error('Worker halted safely: %s', exc)
                return
            except Exception:
                log.exception('Worker polling error')
                stop_event.wait(1)
    finally:
        engine.close()


def execute(db, engine, item, stop_event, resume=False):
    def persist(prompt_id):
        db.execute("UPDATE jobs SET prompt_id=? WHERE id=? AND status='running'", (prompt_id, item['id']))
    try:
        result = engine.resume(item, stop_event) if resume else engine.generate(item, persist, stop_event)
        finish(db, item['id'], result)
    except EngineUnsafe as exc:
        # Keep running/prompt_id for reconciliation after an operator restores connectivity.
        db.execute("UPDATE jobs SET error=? WHERE id=?", (str(exc), item['id']))
        raise
    except Exception as exc:
        log.exception('Job %s failed', item['id'])
        message = str(exc) if isinstance(exc, EngineError) else '生成失败，请稍后重试或联系管理员。'
        db.execute("UPDATE jobs SET status='failed',finished_at=?,error=? WHERE id=? AND status='running'", (now(), message, item['id']))

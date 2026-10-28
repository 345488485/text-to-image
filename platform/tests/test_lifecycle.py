import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app import create_app
from backend.config import Settings
from backend.db import Database
from backend.security import create_user, now
from backend.worker import finish


def test_task_duration_includes_cleanup_and_retries(tmp_path):
    db=Database(tmp_path/'test.sqlite3')
    uid=create_user(db,'timing_user','TestingTiming42!')
    started=(datetime.now(timezone.utc)-timedelta(seconds=200)).isoformat()
    db.execute('INSERT INTO jobs(id,owner_id,prompt,steps,seed,status,created_at,started_at) VALUES(?,?,?,?,?,?,?,?)',
               ('timing',uid,'red teapot',8,42,'running',now(),started))
    finish(db,'timing',{'image_path':'images/timing.png','image_sha256':'a'*64,'elapsed_seconds':1})
    result=db.one('SELECT * FROM jobs WHERE id=?',('timing',))
    assert result['status']=='succeeded'
    assert 200 <= result['elapsed_seconds'] < 205


def test_single_worker_lock_rejects_second_app_and_releases(tmp_path):
    settings=Settings(data_dir=tmp_path,worker_enabled=True)
    def fake_worker(db,settings,stop):
        stop.wait(10)
    with patch('backend.worker.run_worker',fake_worker):
        with TestClient(create_app(settings)):
            with pytest.raises(RuntimeError,match='worker'):
                with TestClient(create_app(settings)):
                    pass
        with TestClient(create_app(settings)):
            pass

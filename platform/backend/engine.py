"""Local fixed-workflow ComfyUI adapter; never kills an unowned service."""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import quote, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener
import uuid

from PIL import Image
from .formats import job_dimensions
from .winprocess import watch_windows_tree

log = logging.getLogger(__name__)


class EngineError(RuntimeError):
    """Safe user-visible inference failure."""


class EngineUnsafe(EngineError):
    """Cannot confirm GPU stopped: worker must not dispatch another job."""


class ComfyEngine:
    def __init__(self, settings):
        self.settings = settings
        parsed = urlparse(settings.engine_url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password or parsed.path not in ('', '/'):
            raise ValueError('Inference endpoint must be local HTTP')
        self._http = build_opener(ProxyHandler({}))
        self._process = None
        self._has_generated = False
        self._log_file = None
        self._cleanup_wait = 15.0
        self._cancel_timeout = 60.0

    def _request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        req = Request(self.settings.engine_url.rstrip('/') + path, data=body,
                      headers={'Content-Type': 'application/json'}, method='GET' if body is None else 'POST')
        with self._http.open(req, timeout=10) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}

    def online(self):
        try:
            return isinstance(self._request('/system_stats'), dict)
        except Exception:
            return False

    def queue(self):
        return self._request('/queue')

    @staticmethod
    def _ids(queue):
        return {item[1] for key in ('queue_running', 'queue_pending') for item in queue[key]}

    def ensure_ready(self, stop_event):
        if self.online():
            return True
        if not self.settings.engine_autostart:
            return False
        if self._process is None or self._process.poll() is not None:
            self._start()
        deadline = time.monotonic() + 180
        while not stop_event.is_set() and time.monotonic() < deadline:
            if self.online():
                return True
            if self._process.poll() is not None:
                break
            stop_event.wait(1)
        return False

    def _start(self):
        root = self.settings.root
        env = os.environ.copy()
        env.update(TEMP=str(root / '.runtime/tmp'), TMP=str(root / '.runtime/tmp'),
                   HF_HOME=str(root / '.runtime/hf'), TORCH_HOME=str(root / '.runtime/torch'), PYTHONNOUSERSITE='1')
        if self._log_file:
            self._log_file.close()
        self._log_file = open(self.settings.data_dir / 'engine.log', 'ab', buffering=0)
        port = str(urlparse(self.settings.engine_url).port or 8188)
        executable = root / '.venv/Scripts/python.exe'
        isolated = root / '.runtime/inference-python/python.exe'
        bootstrap = root / '.runtime/inference-python/bootstrap'
        if isolated.is_file() and (bootstrap / 'sitecustomize.py').is_file():
            executable = isolated
            env['PYTHONPATH'] = os.pathsep.join([str(bootstrap), str(root / '.venv/Lib/site-packages')])
            log.info('Using project-local inference runtime: %s', executable)
        args = [str(executable), str(root / 'run_moss_compatible.py'),
                '--listen', '127.0.0.1', '--port', port, '--lowvram', '--disable-dynamic-vram',
                '--disable-mmap', '--cache-none', '--preview-method', 'none', '--extra-model-paths-config',
                str(root / 'extra_model_paths.yaml'), '--output-directory', str(root / 'output'),
                '--temp-directory', str(root / '.runtime/tmp'), '--user-directory', str(root / 'user'), '--disable-auto-launch']
        self._process = subprocess.Popen(args, cwd=root, env=env, stdout=self._log_file,
                                         stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self._has_generated = False

    def reset_if_used(self, stop_event):
        """Cold-start only our idle, previously used child; never restart external services."""
        if self._process is None or not self._has_generated:
            return False
        if self._ids(self.queue()):
            raise EngineUnsafe('推理服务有未协调任务，不能重启，队列已暂停。')
        if stop_event.is_set():
            raise EngineError('任务已停止。')
        # Windows 2GB pagefile: real consecutive jobs still hit 1455 after /free.
        # A cold owned process releases CPU model allocations as well as CUDA caches.
        log.info('Restarting idle owned inference child before next job (Windows paging pressure)')
        self.close()
        if not self.ensure_ready(stop_event):
            raise EngineError('推理服务离线，请联系管理员。')
        return True

    def close(self):
        if self._process is not None:
            if self._process.poll() is None:
                if os.name == 'nt':
                    # venv's Windows launcher owns the real Python/CUDA child.
                    with watch_windows_tree(self._process.pid) as tree_stopped:
                        # Direct handles avoid taskkill/CIM hanging with a broken WMI provider.
                        tree_stopped.terminate()
                        try:
                            self._process.wait(timeout=15)
                        except subprocess.TimeoutExpired as exc:
                            raise EngineUnsafe('推理子进程停止未确认，队列已暂停。') from exc
                        if not tree_stopped():
                            log.error('Owned descendants still alive after native termination')
                            raise EngineUnsafe('推理子进程停止未确认，队列已暂停。')
                else:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=15)
            self._process = None
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def workflow(self, job):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', job['id']):
            raise ValueError('Invalid job id')
        if type(job['steps']) is not int or job['steps'] not in (8, 16, 20):
            raise ValueError('Invalid steps')
        if type(job['seed']) is not int or not 0 <= job['seed'] <= 2**32 - 1:
            raise ValueError('Invalid seed')
        if not isinstance(job['prompt'], str) or not job['prompt'].strip() or len(job['prompt']) > 4000:
            raise ValueError('Invalid prompt')
        if not isinstance(job.get('negative_prompt', ''), str) or len(job.get('negative_prompt', '')) > 4000:
            raise ValueError('Invalid negative prompt')
        graph = json.loads((self.settings.root / 'workflow-api-8steps.json').read_text(encoding='utf-8-sig'))
        graph['4']['inputs']['text'] = job['prompt']
        graph['5']['inputs']['text'] = job.get('negative_prompt', '')
        graph['8']['inputs'].update(seed=job['seed'], steps=job['steps'])
        width, height = job_dimensions(job)
        graph['6']['inputs'].update(width=width, height=height, batch_size=1)
        graph['10']['inputs']['filename_prefix'] = 'platform_' + job['id']
        return graph

    def save_result(self, job, history, elapsed):
        status = history.get('status', {})
        if status.get('status_str') != 'success' or status.get('completed') is not True:
            log.error('Engine execution failed for %s: %r', job['id'], history.get('status'))
            raise EngineError('生成失败，请稍后重试或联系管理员。')
        images = history.get('outputs', {}).get('10', {}).get('images', [])
        if len(images) != 1 or images[0].get('type') != 'output':
            raise EngineError('生成结果无效，请联系管理员。')
        item = images[0]
        filename, subfolder = item['filename'], item.get('subfolder', '')
        if not isinstance(filename, str) or '/' in filename or '\\' in filename or filename in ('.', '..'):
            raise EngineError('生成结果无效，请联系管理员。')
        output = (self.settings.root / 'output').resolve()
        source = (output / subfolder / filename).resolve()
        if not source.is_relative_to(output) or not source.is_file():
            raise EngineError('生成结果无效，请联系管理员。')
        try:
            with Image.open(source) as image:
                if image.format != 'PNG' or image.size != job_dimensions(job):
                    raise ValueError('Unexpected PNG dimensions')
                image.verify()
            self.workflow(job)  # validates id before constructing a private destination
            dest = self.settings.data_dir / 'images' / (job['id'] + '.png')
            temporary = dest.with_suffix('.png.part')
            shutil.copyfile(source, temporary)
            temporary.replace(dest)
            return dict(image_path='images/' + dest.name,
                        image_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), elapsed_seconds=round(elapsed, 3))
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError('生成图片校验失败，请联系管理员。') from exc

    def recover(self, prompt_id):
        history = self._request('/history/' + quote(prompt_id, safe=''))
        if prompt_id in history:
            return {'state': 'completed', 'history': history[prompt_id]}
        if prompt_id in self._ids(self.queue()):
            return {'state': 'running'}
        # Completion can atomically move queue -> history between these HTTP reads.
        history = self._request('/history/' + quote(prompt_id, safe=''))
        if prompt_id in history:
            return {'state': 'completed', 'history': history[prompt_id]}
        return {'state': 'missing'}

    def cancel(self, prompt_id):
        try:
            try:
                # Pinned ComfyUI checks the running id and interrupts under one mutex.
                # Legacy /interrupt has a check/interruption race that can hit the next job.
                self._request('/api/jobs/' + quote(prompt_id, safe='') + '/cancel', {})
            except HTTPError as exc:
                raise EngineUnsafe('推理服务安全取消接口不可用，队列已暂停，请联系管理员。') from exc
            deadline = time.monotonic() + self._cancel_timeout
            while True:
                if prompt_id not in self._ids(self.queue()):
                    return
                if time.monotonic() >= deadline:
                    break
                time.sleep(1)
        except EngineUnsafe:
            raise
        except Exception:
            log.exception('Could not confirm prompt cancellation')
        # Only this owned child can be terminated; external services remain untouched.
        if self._process is not None:
            self.close()
            return
        raise EngineUnsafe('推理任务停止未确认，队列已暂停，请联系管理员。')

    def _wait_result(self, job, prompt_id, stop_event, started):
        while True:
            if stop_event.is_set() or time.monotonic() - started >= self.settings.task_timeout:
                self.cancel(prompt_id)
                raise EngineError('任务已停止。' if stop_event.is_set() else '生成超时，请稍后重试。')
            try:
                state = self.recover(prompt_id)
            except HTTPError:
                raise
            except (OSError, URLError):
                # Loading can stall HTTP responses. Keep the durable prompt id; never resubmit.
                if self._process is not None and self._process.poll() is not None:
                    raise EngineError('推理进程已退出，请查看引擎日志。')
                log.warning('Inference status temporarily unavailable; keeping prompt %s', prompt_id)
                stop_event.wait(1)
                continue
            if state['state'] == 'completed':
                # history is committed when the queue task is removed.
                return self.save_result(job, state['history'], time.monotonic() - started)
            if state['state'] == 'missing':
                raise EngineError('推理任务记录丢失，请重新提交。')
            stop_event.wait(1)

    def resume(self, job, stop_event):
        prompt_id = job.get('prompt_id')
        if not prompt_id:
            # Before submission the UUID is durably stored, so no id means no POST.
            raise EngineError('服务重启前任务未提交，请重新生成。')
        try:
            return self._wait_result(job, prompt_id, stop_event, time.monotonic())
        except EngineUnsafe:
            raise
        except Exception:
            self.cancel(prompt_id)
            raise

    def generate(self, job, on_prompt, stop_event):
        graph = self.workflow(job)
        for attempt in range(2):
            prompt_id = None
            history = None
            try:
                if not self.ensure_ready(stop_event):
                    raise EngineError('推理服务离线，请联系管理员。')
                if self._ids(self.queue()):
                    raise EngineUnsafe('推理服务有未协调任务，队列已暂停。')
                self.reset_if_used(stop_event)
                fresh_owned = self._process is not None and self._process.poll() is None and not self._has_generated
                if not fresh_owned:
                    self._request('/free', {'unload_models': True, 'free_memory': True})
                    # External services remain untouched; /free has no completion acknowledgment.
                    if stop_event.wait(self._cleanup_wait):
                        raise EngineError('任务已停止。')
                if self._ids(self.queue()):
                    raise EngineUnsafe('推理服务忙碌，队列已暂停。')
                if stop_event.is_set():
                    raise EngineError('任务已停止。')
                prompt_id = str(uuid.uuid4())
                on_prompt(prompt_id)  # durable before HTTP POST, including ambiguous transport failure
                started = time.monotonic()
                if self._process is not None:
                    self._has_generated = True  # even a lost response may have loaded models
                accepted = self._request('/prompt', {'prompt': graph, 'prompt_id': prompt_id, 'client_id': 'moss-platform'})
                if accepted.get('prompt_id') != prompt_id:
                    raise EngineUnsafe('推理服务任务标识异常，队列已暂停。')
                return self._wait_result(job, prompt_id, stop_event, started)
            except EngineUnsafe:
                raise
            except Exception as exc:
                if prompt_id:
                    self.cancel(prompt_id)
                    try:
                        history = self._request('/history/' + quote(prompt_id, safe='')).get(prompt_id)
                    except Exception:
                        pass
                memory_error = history and any(word in json.dumps(history.get('status', {})).lower() for word in ('1455', 'out of memory', 'paging file'))
                if attempt == 0 and memory_error and self._process is not None and not stop_event.is_set():
                    log.warning('Restarting owned inference child after memory failure')
                    self.close()
                    continue
                if isinstance(exc, EngineError):
                    raise
                log.exception('Inference request failed')
                raise EngineError('生成失败，请稍后重试或联系管理员。') from exc

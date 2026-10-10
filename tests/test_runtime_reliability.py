import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'computer'))
from control_plane import maintenance, supervisor
from control_plane.log_tail import read_log_tail


class Response(io.BytesIO):
    status = 200


@pytest.mark.parametrize('payload', [
    {'ready': False}, {'ready': True, 'checks': {'gui': False}},
    {'ready': 'true'}, [], {'ok': True},
])
def test_maintenance_rejects_unhealthy_200_response(monkeypatch, payload):
    monkeypatch.setattr(maintenance.urllib.request, 'urlopen', lambda *a, **kw: Response(json.dumps(payload).encode()))
    assert maintenance.MaintenanceManager()._probe_url('http://localhost/ready')['ok'] is False


def test_maintenance_accepts_ready_body(monkeypatch):
    monkeypatch.setattr(maintenance.urllib.request, 'urlopen', lambda *a, **kw: Response(b'{"ready":true,"checks":{"gui":true}}'))
    assert maintenance.MaintenanceManager()._probe_url('http://localhost/ready')['ok'] is True


@pytest.mark.parametrize('level', ['wrong', -1, 0, 6, 1.5, True])
def test_invalid_recovery_level_returns_error(level):
    result = maintenance.MaintenanceManager().recover(level)
    assert result['ok'] is False and '1..5' in result['error']


def test_auto_recovery_of_healthy_system_is_noop(monkeypatch):
    manager = maintenance.MaintenanceManager()
    monkeypatch.setattr(manager, 'run', lambda: {'overall_ok': True})
    assert manager.recover('auto')['noop'] is True


def test_restart_uses_safe_argv_and_custom_workspace(tmp_path, monkeypatch):
    root = tmp_path / 'runtime with spaces; touch INJECTED'
    monkeypatch.setenv('AIRIPC_WORKSPACE_ROOT', str(root))
    monkeypatch.setattr(maintenance, 'save_json', lambda *a: None)
    manager = maintenance.MaintenanceManager()
    monkeypatch.setattr(manager, 'run', lambda: {'overall_ok': False})
    calls = []
    monkeypatch.setattr(maintenance.subprocess, 'Popen', lambda args, **kw: calls.append((args, kw)))
    result = manager.recover(2)
    assert result['ok'] is True
    args, options = calls[0]
    assert args == ['/bin/sh', str(root / 'computer/start.sh')]
    assert options['cwd'] == str(root)
    assert options['env']['AIRI_FORCE_RESTART'] == '1'
    assert options['env']['AIRIPC_WORKSPACE_ROOT'] == str(root)
    assert not (tmp_path / 'INJECTED').exists()


def test_maintenance_uses_custom_port_and_probes_display(tmp_path, monkeypatch):
    monkeypatch.setenv('AIRIPC_WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setenv('AIRI_PORT', '9123')
    monkeypatch.setenv('DISPLAY', ':117')
    monkeypatch.setattr(maintenance, 'save_json', lambda *a: None)
    calls = []
    def run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(maintenance.subprocess, 'run', run)
    manager = maintenance.MaintenanceManager()
    urls = []
    monkeypatch.setattr(manager, '_probe_url', lambda url: urls.append(url) or {'ok': True})
    manager.run()
    assert urls == ['http://127.0.0.1:9123/status', 'http://127.0.0.1:9123/ready']
    assert calls[1] == ['xdpyinfo', '-display', ':117']
    assert '9123' in calls[0][-1]


@pytest.mark.parametrize('payload', ['not json', '{"ready":false}', '{"ready":true,"checks":{"source_match":false}}'])
def test_supervisor_rejects_false_readiness(monkeypatch, tmp_path, payload):
    manager = supervisor.Supervisor(str(tmp_path))
    monkeypatch.setattr(manager, '_run', lambda *a: subprocess.CompletedProcess([], 0, payload, ''))
    assert manager.http_probe('http://localhost/ready')['ok'] is False


def test_supervisor_observes_workspace_and_expected_source(monkeypatch, tmp_path):
    monkeypatch.setenv('AIRIPC_WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setenv('AIRI_EXPECTED_SHA', 'current')
    manager = supervisor.Supervisor()
    assert manager.base == tmp_path
    for sha, expected in [('stale', False), ('current', True)]:
        payload = json.dumps({'ready': True, 'checks': {'source_match': True}, 'source_sha': sha})
        monkeypatch.setattr(manager, '_run', lambda *a: subprocess.CompletedProcess([], 0, payload, ''))
        assert manager.http_probe('http://localhost/ready')['ok'] is expected


def test_log_tail_reads_bounded_suffix_and_handles_utf8(tmp_path):
    log = tmp_path / 'large.log'
    suffix = 'à🙂fine\n' * 10000
    log.write_bytes(b'old output\n' * 500000 + suffix.encode())
    reads = []
    original_open = Path.open
    class TrackingFile:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def seek(self, *args): return self.stream.seek(*args)
        def read(self, size=-1):
            reads.append(size)
            return self.stream.read(size)
    with patch.object(Path, 'open', lambda path, *a, **kw: TrackingFile(original_open(path, *a, **kw))):
        assert read_log_tail(log) == suffix[-20000:]
    assert reads == [80000]
    log.write_bytes(b'prefix\xffinvalid\n')
    assert read_log_tail(log).endswith('\ufffdinvalid\n')


def test_dependency_probe_does_not_import_gui_before_display(tmp_path):
    text = (ROOT / 'computer/start.sh').read_text()
    expression = re.search(r"-c '([^'\n]*pyautogui[^'\n]*)'", text).group(1)
    for name in ('fastapi', 'uvicorn', 'pyautogui', 'pytesseract', 'PIL', 'playwright'):
        (tmp_path / f'{name}.py').write_text('raise RuntimeError("GUI import requires display")\n')
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    env.pop('DISPLAY', None)
    result = subprocess.run([sys.executable, '-c', expression], env=env, cwd=tmp_path,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('observed_display,expected', [(':199', True), (':99', False), (None, False)])
def test_contract_readiness_checks_configured_display(monkeypatch, observed_display, expected):
    import contract_server
    monkeypatch.setenv('DISPLAY', ':199')
    monkeypatch.setenv('AIRI_EXPECTED_SHA', 'source')
    monkeypatch.setenv('AIRI_BOOTSTRAP_SHA', 'source')
    monkeypatch.setattr(contract_server._legacy, 'status', lambda: {
        'ok': True, 'gui_available': True, 'resolution': '1280x800', 'display': observed_display})
    class Browser:
        def status(self): return {'available': True, 'open': True}
    monkeypatch.setattr(contract_server._legacy, 'browser', lambda: Browser())
    ready = contract_server._ready_payload()
    assert ready['checks']['gui'] is expected
    assert ready['ready'] is expected


def test_limited_search_is_deterministic(monkeypatch, tmp_path):
    import coding
    monkeypatch.setattr(coding, 'ROOT', tmp_path)
    monkeypatch.setattr(coding, 'safe_path', lambda path: Path(path))
    # Create z before a to reproduce unsorted filesystem traversal.
    (tmp_path / 'z.py').write_text('VALUE = 1\n')
    (tmp_path / 'a.py').write_text('VALUE = 2\n')
    result = coding.search('VALUE', str(tmp_path), limit=1)
    assert result['matches'] == [{'path': 'a.py', 'line': 1, 'text': 'VALUE = 2'}]
    assert result['truncated'] is True


def test_project_index_excludes_cache_binary_large_files_and_stale_entries(monkeypatch, tmp_path):
    from control_plane import project_index
    monkeypatch.setattr(project_index, 'ROOT', tmp_path)
    monkeypatch.setattr(project_index, 'load_json', lambda name, default: default)
    monkeypatch.setattr(project_index, 'save_json', lambda *a: None)
    (tmp_path / 'app.py').write_text('def useful(): pass\n')
    cache=tmp_path/'.cache/browser'; cache.mkdir(parents=True)
    (cache/'cached.py').write_text('def cached(): pass\n')
    (tmp_path/'binary').write_bytes(b'\0not source')
    (tmp_path/'.mcp_token').write_text('runtime credential')
    (tmp_path/'.env.local').write_text('runtime configuration')
    with (tmp_path/'large.txt').open('wb') as stream: stream.truncate(project_index.MAX_INDEX_FILE_BYTES+1)
    index=project_index.ProjectIndex()
    for key in ('files','symbols','dependencies'):
        index.state[key]['.cache/browser/stale.py'] = {} if key=='files' else []
    result=index.refresh()
    assert result['files']==1
    assert set(index.state['files'])=={'app.py'}
    assert set(index.state['symbols'])=={'app.py'}
    assert index.search('useful')==[{'path':'app.py','symbol':'useful'}]


def test_context_pack_reads_only_budget_and_bounds_invalid_utf8(monkeypatch, tmp_path):
    from control_plane import project_index
    monkeypatch.setattr(project_index, 'ROOT', tmp_path)
    monkeypatch.setattr(project_index, 'load_json', lambda name, default: default)
    monkeypatch.setattr(project_index, 'save_json', lambda *a: None)
    target=tmp_path/'large.txt'
    target.write_bytes(b'\xff'*100)
    index=project_index.ProjectIndex()
    index.state['files']={'large.txt':{}}
    index.state['symbols']={'large.txt':[]}
    reads=[]
    original_open=Path.open
    class TrackingFile:
        def __init__(self,stream): self.stream=stream
        def __enter__(self): return self
        def __exit__(self,*a): self.stream.close()
        def read(self,size=-1): reads.append(size); return self.stream.read(size)
    with patch.object(Path,'open',lambda path,*a,**kw: TrackingFile(original_open(path,*a,**kw))):
        pack=index.context_pack('large',max_bytes=3)
    assert reads==[3]
    assert pack['bytes']==3 and pack['files'][0]['content']=='\ufffd'


def test_project_index_does_not_follow_symlinks_outside_workspace(monkeypatch, tmp_path):
    from control_plane import project_index
    root=tmp_path/'workspace'; root.mkdir()
    outside=tmp_path/'outside.py'; outside.write_text('def secret(): pass\n')
    (root/'link.py').symlink_to(outside)
    monkeypatch.setattr(project_index,'ROOT',root)
    monkeypatch.setattr(project_index,'load_json',lambda name,default: default)
    monkeypatch.setattr(project_index,'save_json',lambda *a: None)
    index=project_index.ProjectIndex()
    assert index.refresh()['files']==0
    index.state['files']={'link.py':{}}
    assert index.context_pack('link')['files']==[]


def test_desktop_selftest_reuses_bootstrap_browser_cache(monkeypatch, tmp_path):
    import runpy
    import subprocess
    monkeypatch.setenv('AIRIPC_WORKSPACE_ROOT',str(tmp_path))
    monkeypatch.delenv('PLAYWRIGHT_BROWSERS_PATH',raising=False)
    binary=tmp_path/'.cache/ms-playwright/chromium-123/chrome-linux64/chrome'
    binary.parent.mkdir(parents=True); binary.write_text('browser fixture')
    def unexpected_install(*args,**kwargs):
        raise AssertionError('Existing bootstrap cache must avoid a browser download')
    monkeypatch.setattr(subprocess,'run',unexpected_install)
    script=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/airi-selftest'))
    assert script['ensure_browser']() is True


def test_desktop_selftest_install_honors_configured_cache(monkeypatch, tmp_path):
    import runpy
    import subprocess
    cache=tmp_path/'custom browser cache'
    monkeypatch.setenv('AIRIPC_WORKSPACE_ROOT',str(tmp_path))
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH',str(cache))
    calls=[]
    def install(args,**kwargs):
        calls.append((args,kwargs)); return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(subprocess,'run',install)
    script=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/airi-selftest'))
    assert script['ensure_browser']() is True
    assert len(calls)==1
    args,kwargs=calls[0]
    assert args==[str(tmp_path/'.venv/bin/python'),'-m','playwright','install','chromium']
    assert kwargs['env']['PLAYWRIGHT_BROWSERS_PATH']==str(cache)
    assert kwargs['cwd']==str(tmp_path)


def test_coding_selftest_preserves_existing_operational_state(tmp_path):
    workspace = tmp_path / 'live workspace'
    sentinels = {
        '.ai/task_state.json': '{"goal":"real task","active":true}',
        '.ai/state/recovery.json': '{"status":"active","goal":"real recovery"}',
        '.ai/PROJECT_MEMORY.md': '# Real memory\n',
        '.ai/coding-selftest-project/user-file.txt': 'existing user data',
    }
    for name, content in sentinels.items():
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/airi-coding-selftest')],
                            env=dict(os.environ, AIRIPC_WORKSPACE_ROOT=str(workspace)),
                            text=True, capture_output=True, timeout=160)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['ALL'] is True
    assert {name: (workspace / name).read_text() for name in sentinels} == sentinels


def test_coding_selftest_propagates_failure_and_removes_owned_workspace(monkeypatch):
    import runpy
    script = runpy.run_path(str(ROOT / 'scripts/airi-coding-selftest'))
    owned = []
    def fail(args, **kwargs):
        isolated = Path(kwargs['env']['AIRIPC_WORKSPACE_ROOT'])
        assert isolated.is_dir()
        owned.append(isolated)
        assert args[-1] == '--isolated'
        return subprocess.CompletedProcess(args, 2)
    monkeypatch.setattr(subprocess, 'run', fail)
    assert script['main']() == 2
    assert owned and not owned[0].exists()

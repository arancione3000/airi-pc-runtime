from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

from .store import load_json, save_json, now
from .reliability import REGISTRY


class MaintenanceManager:
    LEVELS = {1: 'retry', 2: 'component_restart', 3: 'component_repair',
              4: 'runtime_rebuild', 5: 'escalation'}

    def _root(self):
        return os.environ.get('AIRIPC_WORKSPACE_ROOT', '/home/user/airi')

    def _port(self):
        return os.environ.get('AIRI_PORT', os.environ.get('AIRIPC_PORT', '9010'))

    def _probe_url(self, url):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                payload = json.loads(response.read(65537))
                field = 'ready' if url.endswith('/ready') else 'ok'
                ok = response.status == 200 and isinstance(payload, dict) and payload.get(field) is True
                if field == 'ready' and isinstance(payload, dict):
                    checks = payload.get('checks', {})
                    ok = ok and isinstance(checks, dict) and all(value is True for value in checks.values())
                return {'ok': ok, **({} if ok else {'error': 'unhealthy_response'})}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def run(self):
        checks = {}
        base = Path(self._root()).resolve()
        port = self._port()
        try:
            usage = shutil.disk_usage(base.parent)
            checks['disk'] = {'ok': usage.free > 512 * 1024 * 1024,
                              'free_gb': round(usage.free / 1e9, 3),
                              'used_percent': round(100 * (usage.total - usage.free) / usage.total, 2)}
        except Exception as exc:
            checks['disk'] = {'ok': False, 'error': str(exc)}
        try:
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError('invalid runtime port')
            process = subprocess.run(['pgrep', '-f', rf'[u]vicorn.*--port {port}(\s|$)'],
                                     capture_output=True, timeout=3)
            checks['processes'] = {'ok': process.returncode == 0}
        except Exception as exc:
            checks['processes'] = {'ok': False, 'error': str(exc)}
        display = os.environ.get('DISPLAY', ':99')
        try:
            probe = subprocess.run(['xdpyinfo', '-display', display], capture_output=True, timeout=3)
            checks['display'] = {'ok': probe.returncode == 0, 'display': display}
        except Exception as exc:
            checks['display'] = {'ok': False, 'display': display, 'error': str(exc)}
        for name, endpoint in (('mcp', 'status'), ('ready', 'ready')):
            checks[name] = self._probe_url(f'http://127.0.0.1:{port}/{endpoint}')
            REGISTRY.record(name, checks[name]['ok'], error=checks[name].get('error', ''))
        overall = all(bool(value.get('ok')) for value in checks.values())
        row = {'timestamp': now(), 'overall_ok': overall, 'checks': checks,
               'recommended_level': 1 if overall else 2, 'reliability': REGISTRY.summary()}
        save_json('maintenance.json', row)
        return row

    def recover(self, level='auto', confirm=None):
        if level in ('auto', None):
            lvl = None
        elif isinstance(level, bool) or str(level) not in {str(key) for key in self.LEVELS}:
            return {'ok': False, 'error': 'level must be auto or 1..5'}
        else:
            lvl = int(level)
        current = self.run()
        base = Path(self._root()).resolve()
        if lvl is None:
            if current['overall_ok']:
                return {'ok': True, 'level': 1, 'action': 'retry', 'result': current, 'noop': True}
            lvl = 2
        if current['overall_ok'] and lvl == 1:
            return {'ok': True, 'level': 1, 'action': 'retry', 'result': current}
        record = {'timestamp': now(), 'requested_level': lvl, 'current': current, 'action': self.LEVELS[lvl]}
        try:
            if lvl == 1:
                result = self.run()
                record.update(ok=result['overall_ok'], result=result)
            elif lvl == 2:
                log = base / 'logs/maintenance-restart.log'
                log.parent.mkdir(parents=True, exist_ok=True)
                env = dict(os.environ, AIRIPC_WORKSPACE_ROOT=str(base), AIRI_FORCE_RESTART='1')
                with log.open('ab') as output:
                    subprocess.Popen(['/bin/sh', str(base / 'computer/start.sh')], cwd=str(base), env=env,
                                     stdout=output, stderr=output, stdin=subprocess.DEVNULL, start_new_session=True)
                record.update(ok=True, started=True, detail='component restart delegated to start.sh', log=str(log))
            elif lvl == 3:
                venv = Path(os.environ.get('AIRIPC_VENV', str(base / '.venv')))
                result = subprocess.run([str(venv / 'bin/python'), '-m', 'pip', 'install',
                                         '--disable-pip-version-check', '-r', str(base / 'computer/requirements.txt')],
                                        text=True, capture_output=True, timeout=120)
                record.update(ok=result.returncode == 0, returncode=result.returncode,
                              stdout=result.stdout[-3000:], stderr=result.stderr[-3000:])
            elif lvl == 4 and confirm == 'REBUILD':
                log = base / 'logs/maintenance-rebuild.log'
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open('ab') as output:
                    subprocess.Popen(['/bin/sh', str(base / 'scripts/airi-rebuild')], cwd=str(base),
                                     stdout=output, stderr=output, stdin=subprocess.DEVNULL, start_new_session=True)
                record.update(ok=True, started=True, log=str(log))
            elif lvl == 4:
                record.update(ok=False, needs_confirmation=True, required_confirmation='REBUILD')
            else:
                record.update(ok=False, escalation={'reason': 'automatic recovery exhausted or explicitly requested',
                                                   'recommendation': 'inspect maintenance.json and logs'})
        except Exception as exc:
            record.update(ok=False, error=str(exc))
        save_json('maintenance-last-recovery.json', record)
        return record

    def history(self):
        return load_json('maintenance.json', {})

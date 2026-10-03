import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'linux_setup', Path(__file__).parent.parent / 'scripts/configure-linux.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_desktop_service_and_autostart(tmp_path):
    root = tmp_path / 'Portal mit Leerzeichen %'
    home = tmp_path / 'home'
    setup.configure(root, home, 18080)
    unit = (home / '.config/systemd/user/dartfreunde-portal.service').read_text()
    desktop = (home / '.config/autostart/dartfreunde-portal.desktop').read_text()
    assert '--host 0.0.0.0 --port 18080' in unit
    working_directory = next(line.split('=', 1)[1] for line in unit.splitlines()
                             if line.startswith('WorkingDirectory='))
    assert working_directory.startswith('/')
    assert working_directory == root.as_posix().replace('%', '%%')
    assert 'DATA_DIR=' in unit and 'PLAYWRIGHT_BROWSERS_PATH=' in unit
    assert 'PartOf=graphical-session.target' in unit
    assert '[Install]' not in unit  # Started only with a real desktop session.
    assert 'Exec=/bin/bash "' in desktop
    assert 'start-linux-desktop.sh"' in desktop
    assert '%%' in desktop


@pytest.mark.skipif(not shutil.which('systemd-analyze'), reason='Linux systemd required')
def test_generated_unit_with_systemd_parser(tmp_path):
    root = tmp_path / 'Portal mit Leerzeichen %'
    executable = root / '.venv/bin/uvicorn'
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/bin/sh\nexit 0\n')
    executable.chmod(0o755)
    home = tmp_path / 'home'
    setup.configure(root, home, 18080)
    unit = home / '.config/systemd/user/dartfreunde-portal.service'
    env = dict(os.environ, SYSTEMD_UNIT_PATH='/usr/lib/systemd/user:/usr/lib/systemd/system')
    result = subprocess.run(['systemd-analyze', 'verify', '--man=no', str(unit)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

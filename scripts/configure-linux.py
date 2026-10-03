"""Install a per-user service and a desktop-login autostart entry."""
import argparse
from pathlib import Path


def systemd_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def desktop_quote(value):
    # Desktop Exec parsing processes both entry escapes and quoted arguments.
    value = str(value).replace('\\', '\\\\\\\\')
    for char in ('"', '`', '$'):
        value = value.replace(char, '\\\\' + char)
    return '"' + value.replace('%', '%%') + '"'


def configure(root, home, port):
    service_dir = home / '.config/systemd/user'
    autostart_dir = home / '.config/autostart'
    service_dir.mkdir(parents=True, exist_ok=True)
    autostart_dir.mkdir(parents=True, exist_ok=True)
    unit = f'''[Unit]
Description=Dartfreunde Platten Account-Portal
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory={str(root).replace('%', '%%')}
Environment={systemd_quote('DATA_DIR=' + str(root / 'data'))}
Environment={systemd_quote('PLAYWRIGHT_BROWSERS_PATH=' + str(root / 'data/browsers'))}
ExecStart={systemd_quote(root / '.venv/bin/uvicorn')} app.main:app --host 0.0.0.0 --port {port}
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
'''
    (service_dir / 'dartfreunde-portal.service').write_text(unit)
    desktop = f'''[Desktop Entry]
Type=Application
Name=Dartfreunde Platten Portal
Comment=Startet das Portal mit Zugriff auf die Chrome-Anmeldefenster
Exec=/bin/bash {desktop_quote(root / 'scripts/start-linux-desktop.sh')}
Terminal=false
X-GNOME-Autostart-enabled=true
'''
    (autostart_dir / 'dartfreunde-portal.desktop').write_text(desktop)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18080)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port muss zwischen 1024 und 65535 liegen')
    configure(Path(__file__).resolve().parent.parent, Path.home(), args.port)

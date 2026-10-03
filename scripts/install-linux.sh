#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Linux || "$(id -u)" == 0 ]]; then
  echo "Im Terminal des Linux-Desktops als normaler Benutzer ausführen (ohne sudo)." >&2
  exit 1
fi
if [[ "$(uname -m)" != x86_64 ]]; then
  echo "Diese Installation benötigt eine Linux-VM mit AMD64/x86_64 für Google Chrome." >&2
  exit 1
fi
if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  echo "Bitte im Terminal der angemeldeten Desktop-Sitzung starten, nicht über SSH." >&2
  exit 1
fi
portal_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
portal_port="${1:-18080}"
if ! [[ "$portal_port" =~ ^[0-9]+$ ]] || (( portal_port < 1024 || portal_port > 65535 )); then
  echo "Port muss zwischen 1024 und 65535 liegen." >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip curl ca-certificates
if ! command -v google-chrome >/dev/null && ! command -v google-chrome-stable >/dev/null; then
  portal_download="$(mktemp -d)"
  trap 'rm -rf -- "$portal_download"' EXIT
  curl --fail --location --output "$portal_download/google-chrome.deb" \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo apt-get install -y "$portal_download/google-chrome.deb"
fi
cd -- "$portal_root"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sudo "$portal_root/.venv/bin/python" -m playwright install-deps chromium
PLAYWRIGHT_BROWSERS_PATH="$portal_root/data/browsers" .venv/bin/python -m playwright install chromium
.venv/bin/python scripts/configure-linux.py --port "$portal_port"
bash scripts/start-linux-desktop.sh
curl --fail --silent --retry 15 --retry-connrefused --retry-delay 1 \
  "http://127.0.0.1:$portal_port/health"
printf '\nPortal bereit: http://VM-IP:%s\n' "$portal_port"

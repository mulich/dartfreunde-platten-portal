#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  echo "Eine angemeldete Linux-Desktop-Sitzung wird benötigt." >&2
  exit 1
fi
# Import only session variables, never the full shell environment.
portal_session_vars=()
for portal_var in DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS XDG_SESSION_TYPE; do
  if [[ -n "${!portal_var:-}" ]]; then
    portal_session_vars+=("$portal_var")
  fi
done
systemctl --user import-environment "${portal_session_vars[@]}"
systemctl --user daemon-reload
systemctl --user restart dartfreunde-portal.service

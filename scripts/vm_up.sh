#!/usr/bin/env bash
# Run on the laptop from this checkout. Only committed source and Rahul state travel.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null
command -v git >/dev/null
command -v ssh >/dev/null
uv run python - "${1:-om@hermes.<tailnet>.ts.net}" <<'PY'
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from scripts.switch_users import read_env

host = sys.argv[1]
if host.startswith('-'):
    raise SystemExit('Invalid SSH destination')
# Refuse a simultaneous local registration consumer; bounded probes must finish first.
processes = subprocess.check_output(['ps', '-axo', 'command='], text=True)
for line in processes.splitlines():
    if ('python' in line and any(name in line for name in
            ('trustnet.gate', 'scripts.dm_live_probe', 'scripts.gate_live_probe',
             'scripts.e2e_scene1'))):
        raise SystemExit('Stop the local gate/probe before deploying Rahul')
env = read_env(Path('.env'))
for key in ('SWITCH_URL', 'RAHUL_GATE_KEY'):
    if not env.get(key) or any(c in env[key] for c in '\n\r\x00'):
        raise SystemExit('Missing or invalid required VM environment value')
state = json.loads(Path('data/day0-state.json').read_text())
if 'rahul' not in state:
    raise SystemExit('Retained Rahul registration required')
archive = subprocess.check_output(['git', 'archive', 'HEAD'])
with tempfile.TemporaryDirectory(prefix='tn-vm-') as temporary:
    os.chmod(temporary, 0o700)
    payload = Path(temporary) / 'payload.tar'
    with tarfile.open(fileobj=io.BytesIO(archive)) as source, tarfile.open(payload, 'w') as target:
        for member in source:
            if member.name.startswith(('examples/om/', 'examples/priya/')):
                continue
            target.addfile(member, source.extractfile(member) if member.isfile() else None)
        # Fixed destinations, not arbitrary .env contents. Never copy other credentials.
        files = {
            '.vm/rahul.env': ''.join(k + '=' + '"' + env[k].replace('\\', '\\\\').replace('"', '\\"') + '"\n'
                                   for k in ('SWITCH_URL', 'RAHUL_GATE_KEY')),
            '.vm/state.json': json.dumps({'rahul': state['rahul']}),
            '.vm/identities.json': Path('data/gate-identities.json').read_text(),
        }
        for name, value in files.items():
            raw = value.encode()
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(raw), 0o600
            target.addfile(info, io.BytesIO(raw))
    os.chmod(payload, 0o600)
    setup = r'''
set -eu
umask 077
export PATH="$HOME/.local/bin:$PATH"
if ! command -v git >/dev/null; then sudo apt-get update -qq; sudo apt-get install -y git; fi
if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
mkdir -p "$HOME/trust-network" "$HOME/.config/trust-network" "$HOME/.config/systemd/user"
cd "$HOME/trust-network"
# Stop before replacing source or credentials, including on a repeated deployment.
systemctl --user stop rahul-gate.service 2>/dev/null || true
tar xf -
install -m 600 .vm/rahul.env "$HOME/.config/trust-network/rahul.env"
mkdir -p data/profiles/rahul
if [ ! -f data/rahul-state.json ]; then install -m 600 .vm/state.json data/rahul-state.json; fi
install -m 600 .vm/identities.json data/gate-identities.json
rm -rf .vm
for file in facts.yaml calendar.ics trust.yaml; do
    if [ ! -f "data/profiles/rahul/$file" ]; then
        install -m 600 "examples/rahul/$file" "data/profiles/rahul/$file"
    fi
done
uv sync --locked --python 3.12
cat > "$HOME/.config/systemd/user/rahul-gate.service" <<EOF
[Unit]
Description=Rahul trust-network gate
After=network-online.target
[Service]
WorkingDirectory=$HOME/trust-network
EnvironmentFile=$HOME/.config/trust-network/rahul.env
Environment=TN_DATA_DIR=$HOME/trust-network/data/profiles
ExecStart=$HOME/trust-network/.venv/bin/python -m trustnet.gate --person rahul --key-env RAHUL_GATE_KEY --state data/rahul-state.json --identity-map data/gate-identities.json
Restart=on-failure
RestartSec=5
UMask=0077
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now rahul-gate.service
systemctl --user is-active rahul-gate.service
uv run tn --help >/dev/null
'''
    # Script is the SSH command; stdin carries the archive, never secret arguments.
    import shlex
    with payload.open('rb') as stream:
        subprocess.run(['ssh', '-o', 'BatchMode=yes', host, 'bash -c ' + shlex.quote(setup)],
                       stdin=stream, check=True)
print('VM deployed; verify addressed commands before claiming readiness.')
PY

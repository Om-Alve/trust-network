#!/usr/bin/env bash
# Reset the two-machine Hermes demo between takes (laptop: om/priya gates, Om's
# Hermes; VM: rahul-gate, Rahul's Hermes). Pauses both watchers, stops all three
# gates, runs demo_reset, restarts the gates, marks old home-room history as read
# (so the first watch doesn't flood either Hermes), then resumes the watchers.
#   scripts/hermes/scene_reset.sh            # reset
#   scripts/hermes/scene_reset.sh --deploy   # also deploy HEAD to the VM first
set -euo pipefail
cd "$(dirname "$0")/../.."
VM=${VM:-om@hermes.<tailnet>.ts.net}
OM_JOB=${OM_JOB:-7439654a54cb}
RAHUL_JOB=${RAHUL_JOB:-6160bdf6868e}
SU=$(grep -E '^SWITCH_URL=' .env | cut -d= -f2-)
VM_ENV="SWITCH_URL=$SU TN_STATE_DIR=/home/om/.config/trust-network/state TN_DATA_DIR=/home/om/trust-network/data/profiles"

hermes -p om cron pause "$OM_JOB" >/dev/null
ssh "$VM" "export PATH=\$HOME/.local/bin:\$PATH; hermes -p rahul cron pause $RAHUL_JOB >/dev/null"
pkill -f "trustnet.gate --person (om|priya)" || true
if [[ "${1:-}" == "--deploy" ]]; then
  sleep 1
  ./scripts/vm_up.sh "$VM" | tail -1
  scp -q skills/trust-network/SKILL.md "$VM":.hermes/profiles/rahul/skills/trust-network/SKILL.md
  cp skills/trust-network/SKILL.md ~/.hermes/profiles/om/skills/trust-network/SKILL.md
fi
ssh "$VM" 'systemctl --user stop rahul-gate'
sleep 1
uv run python -m scripts.demo_reset --data-dir data/profiles 2>&1 | grep -vE "httpx" | grep -E "Archive|Reset VM" || true

for p in om priya; do
  key=$(echo "$p" | tr a-z A-Z)_GATE_KEY
  nohup uv run --env-file .env env SWITCH_URL="$SU" TN_DATA_DIR="$PWD/data/profiles" \
    python -m trustnet.gate --person "$p" --key-env "$key" >> "data/gate-$p.log" 2>&1 &
done
ssh "$VM" 'systemctl --user start rahul-gate'
sleep 8

for p in om priya; do
  for step in inbox watch; do
    env SWITCH_URL="$SU" TN_DATA_DIR="$PWD/data/profiles" TN_STATE_DIR="$PWD/data" \
      .venv/bin/tn --as "$p" --json "$step" >/dev/null
  done
done
ssh "$VM" "cd ~/trust-network && env $VM_ENV .venv/bin/tn --as rahul --json inbox >/dev/null && env $VM_ENV .venv/bin/tn --as rahul --json watch >/dev/null"

hermes -p om cron resume "$OM_JOB" >/dev/null
ssh "$VM" "export PATH=\$HOME/.local/bin:\$PATH; hermes -p rahul cron resume $RAHUL_JOB >/dev/null; systemctl --user is-active rahul-gate"
pgrep -f "python -m trustnet.gate --person (om|priya)" >/dev/null && echo "laptop gates up"
echo "reset done"

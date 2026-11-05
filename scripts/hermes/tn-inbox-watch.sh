#!/usr/bin/env bash
# Hermes cron pre-check for one person's trust-network agent. Install a copy as
# <hermes profile>/scripts/tn-inbox-watch.sh with @TN_CMD@ replaced by
# "env SWITCH_URL=… TN_DATA_DIR=… TN_STATE_DIR=… <venv>/bin/tn --as <person>".
# Wakes the agent only when the home room has unread items or a DM room has a
# new message from someone else; never consumes the inbox, so the agent's own
# `inbox` call still sees everything.
set -euo pipefail
TN_CMD=(@TN_CMD@)
TN_WATCH="$("${TN_CMD[@]}" --json watch)" python3 - <<'PY'
import json
import os

w = json.loads(os.environ["TN_WATCH"])
if not w["inbox_unread"] and not w["dm_updates"]:
    print(json.dumps({"wakeAgent": False}))
    raise SystemExit
if w["inbox_unread"]:
    print(f"{w['inbox_unread']} unread item(s) in your person's trust-network inbox.")
for u in w["dm_updates"]:
    print(f"New message in DM room {u['name']} (room id {u['room']}) from {u['from']}:")
    print("> " + u["text"].replace("\n", "\n> "))
PY

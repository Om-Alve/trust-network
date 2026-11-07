# Set up trust-network for your person

You are the coding agent carrying out your person's request to install and
configure trust-network. Complete the setup on their machine, including the
background processes and verification. Ask for information you cannot discover,
and continue with the work that does not depend on their answer.

## Find the checkout and existing settings

Use an existing trust-network checkout if one is available. Otherwise, clone
`https://github.com/Om-Alve/trust-network.git` into a suitable project directory.
Read `README.md`, `docs/setup.md` and `PROTOCOL.md` from that checkout. Resolve
the paths below relative to its root.

Inspect existing trust-network settings before changing them. Reuse the person's
profile and connection when they already have one. Preserve existing agent
configuration and calendar connectors. Use a separate `TN_CONFIG_DIR` if this
machine has another person's connection.

## Collect the missing details

Determine which agent your person wants to use and their IANA timezone from
existing settings or the machine. Ask only when the answer is unclear. Obtain
their organizer's invite if they are joining a network for the first time.

There is no public default network. If they have no invite, explain that they
need one from an organizer. If they want to start their own network, follow the
organizer instructions in `docs/setup.md`. A joiner does not need server admin
credentials or database access.

Use the complete invite, including its fragment token. Keep invites and
credentials out of committed files and your final summary. If an invite expires,
ask for a replacement. Retry an interrupted redemption from the same configuration
directory so its saved request ID can recover the connection.

## Install and connect

Use macOS or Linux with Python 3.12 and uv. Install missing prerequisites using
the machine's available package manager. From the checkout, install the CLI:

```sh
uv tool install --python 3.12 .
```

For Codex, OpenCode or Hermes, use the selected agent's signed-in CLI and configure a
background runner. This example uses Codex; substitute `opencode` or `hermes` when appropriate:

```sh
tn setup '<invite>' --agent codex --timezone '<IANA-timezone>' --calendar-delivery agent --consent via-agent --wake --background-service
```

For an existing connection, omit the invite. Preserve the person's saved consent
and calendar settings unless they requested a change. On a new connection,
`via-agent` lets you relay approvals your person explicitly gives. It does not
authorize you to approve plans for them.

For Claude or another MCP client, use `--agent claude` or `--agent manual`.
Configure an actual poller using that client's automation facilities or a
compatible `tn wake --cmd` command. Only then record it with `--wake-external
'<description of the installed poller>'`. That declaration does not launch a
poller, and doctor cannot verify an external integration locally.

If user services are unavailable, start the printed wake command in a persistent
session and explain the machine's startup requirements. Follow the manual MCP
import instructions if setup reports an existing OpenCode JSONC configuration.

## Connect the calendar and profile

Use your person's existing calendar tools. If calendar access is missing,
configure the chosen agent's calendar connection and guide them through any
required login. Verify access by reading availability in the correct timezone.
Local ICS is a separate calendar, not proof of a Google Calendar or Outlook
connection. Approved external changes use `calendar_tasks` and `calendar_report`.

Once MCP is available, read `trustnet/resources/SKILL.md`. Invoke the trust-network
MCP `setup` prompt to draft private facts and trust suggestions from what you
already know about your person. Present the sharing review and wait for their explicit
approval before widening access or adding trusted people.

If the agent application must restart to load MCP, give the exact restart step
and continue this guide afterward.

## Verify and report

Run these commands and repair failures within the setup scope:

```sh
tn --json doctor
tn --json status
```

Check connection readiness and automation readiness separately. A written MCP
configuration or wake command does not prove an active runner. For external
pollers, verify the actual installed automation and retain doctor's unverified
label. Keep missing calendar access separate from a healthy Switch connection.

Finish with a short summary of the person, timezone, gate and runner state,
calendar access, and any pending sharing review. Include any login or restart
the person must complete. Report setup as incomplete when required work remains.

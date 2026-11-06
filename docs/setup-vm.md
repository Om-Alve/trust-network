# Run a gate on a remote machine

The one-machine layout in [setup-laptop.md](setup-laptop.md) is sufficient for a
local demo. Use a remote gate when the person's data must remain on that machine.

For the existing demonstration deployment, run from the laptop checkout:

```sh
scripts/vm_up.sh om@hermes.<tailnet>.ts.net
```

The script transfers committed source, configures the retained registration and
installs the user service. The Switch address must be reachable from the remote
machine. Tailscale Serve can expose the switch-core port within a tailnet.

A remote gate needs `SWITCH_URL`, its own registration key, `TN_DATA_DIR`,
`TN_IDENTITY_URL` and `TN_IDENTITY_TOKEN`. Identity requests require HTTPS and a
bearer token. The publisher must derive identities from trusted server records.
A failed refresh clears the mapping and the gate refuses disclosures.

Check or restart the existing service with:

```sh
ssh om@hermes.<tailnet>.ts.net systemctl --user is-active rahul-gate.service
ssh om@hermes.<tailnet>.ts.net systemctl --user restart rahul-gate.service
```

Run one gate process per person. Stop the remote service before reusing its
registration locally. Discord and managed-agent controllers are optional.

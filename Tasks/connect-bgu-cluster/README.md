# Connect to the BGU cluster through the Master VM

This task connects a local terminal or Copilot session to the BGU Slurm cluster
through the Azure VM named `Master` in resource group `Master`.

## Contents

- `connect_bgu_cluster.sh`: VM startup, VPN login, interactive cluster shells, and
  remote command execution.
- `tests/test_connect_bgu_cluster.py`: isolated tests using mocked Azure and SSH
  commands; no cloud resources or cluster jobs are created.

## Requirements

On the local computer:

- Bash, OpenSSH, and Azure CLI, signed in with `az login`.
- The VM's private key, normally `~/Downloads/Master-VM.pem`, readable only by
  its owner (`chmod 600`).
- Network access to the VM's public SSH port.

On the Ubuntu VM:

- The BGU-provided SNX client and its prerequisites, installed in advance.
- OpenSSH, `ip`, `timeout`, and Bash.
- Network access to `vpn.bgu.ac.il` and, through the VPN, `slurm.bgu.ac.il`.

The script does not install SNX or change firewall rules. Its cluster username
and VPN username can differ. The VPN username must include the `@vpn` suffix.

## Local configuration and alias

Keep personal configuration outside the repository. Create `~/scripts/bgu-cluster`
with the following contents, substituting your own usernames and repository path:

```bash
#!/bin/bash
set -euo pipefail
export BGU_CLUSTER_USER="your-cluster-user"
export BGU_VPN_USER="your-vpn-user@vpn"
export BGU_AZURE_SUBSCRIPTION="your-subscription-id-or-name"
exec "$HOME/code/Master/Tasks/connect-bgu-cluster/connect_bgu_cluster.sh" "$@"
```

`BGU_AZURE_SUBSCRIPTION` is optional; when omitted, Azure CLI uses its current
subscription. `BGU_VM_SSH_KEY` optionally overrides the default private-key path.
An authenticated, running VM can also be accessed using the currently cached
cluster connection without invoking Azure CLI again.

Make the launcher executable:

```bash
chmod 700 ~/scripts/bgu-cluster
```

Add this alias to `~/.zshrc`, then reload the file:

```bash
alias Connect-BGU-Cluster-Master='$HOME/scripts/bgu-cluster'
source ~/.zshrc
```

In shells without this alias, use `~/scripts/bgu-cluster` directly. Copilot
commands generally run in fresh noninteractive shells, where interactive
aliases are not loaded.

## Connect and run commands

Authenticate from your terminal:

```bash
Connect-BGU-Cluster-Master connect
```

The script starts the VM only when necessary, retrieves its current public IP,
and waits for SSH. It connects SNX only if the `tunsnx` interface has no IPv4
address. Enter a fresh VPN token at the SNX password prompt when requested.
The script checks that the cluster SSH service is reachable before opening the
cluster connection. Enter the cluster password at the separate SSH prompt.
Verify any new host-key fingerprint before accepting it.

Without a subcommand, the alias opens an interactive cluster shell:

```bash
Connect-BGU-Cluster-Master
```

Upload a job from the local computer, submit it, and inspect the queue:

```bash
Connect-BGU-Cluster-Master run 'cat > ~/job.sh' < ./job.sh
Connect-BGU-Cluster-Master run 'sbatch ~/job.sh'
Connect-BGU-Cluster-Master run 'squeue -u "$USER"'
```

For an existing cluster-side checkout, submit one of Master's existing tasks:

```bash
Connect-BGU-Cluster-Master run 'cd ~/Master && bash Tasks/run_cluster_task.sh --list'
Connect-BGU-Cluster-Master run 'cd ~/Master && bash Tasks/run_cluster_task.sh TASK_NAME'
```

The command string runs in the cluster account's shell. Quote it as shown so
local variables and paths are not expanded accidentally. Standard input, standard
output, standard error, and the remote exit status are preserved in `run` mode.
Successful `sbatch` output contains the submitted job ID; the connection script
does not create job files or submit jobs on its own.

## Connection lifetime and security

SSH authentication is reused for up to one idle hour through a local control
socket under `~/.ssh/bgu-cluster/`, isolated by cluster host and username.
This lets Copilot run subsequent commands without storing your password or
token. The private key remains on the local computer; SSH agent forwarding is
disabled and normal host-key verification remains enabled.

When authentication expires, run `Connect-BGU-Cluster-Master connect` in a
terminal again. A noninteractive invocation will not wait for a VPN token or
cluster password. If SNX has a stale connection, inspect it on the VM and
reconnect there before retrying; the script does not disconnect an existing VPN.

Close the cached SSH connection:

```bash
Connect-BGU-Cluster-Master disconnect
```

This leaves the VPN and VM running. No credentials, connection sockets, or
runtime outputs should be committed to this task directory.

## Validation

From the repository root:

```bash
bash -n Tasks/connect-bgu-cluster/connect_bgu_cluster.sh
python3 -m unittest discover -s Tasks/connect-bgu-cluster/tests -v
```

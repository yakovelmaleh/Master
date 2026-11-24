#!/bin/bash
set -euo pipefail

subscription="${BGU_AZURE_SUBSCRIPTION:-}"
resource_group="Master"
vm_name="Master"
key="${BGU_VM_SSH_KEY:-$HOME/Downloads/Master-VM.pem}"
cluster_user="${BGU_CLUSTER_USER:-}"
vpn_user="${BGU_VPN_USER:-}"
socket_dir="$HOME/.ssh/bgu-cluster"

usage() {
    cat <<'EOF'
Usage:
  bgu-cluster                  Open an interactive cluster shell.
  bgu-cluster connect          Authenticate and keep the connection for commands.
  bgu-cluster run 'COMMAND'    Run a shell command on the cluster.
  bgu-cluster disconnect       Close the saved cluster connection (not the VPN/VM).

Starts the Master VM if necessary and prompts for the BGU VPN token and cluster
password when required. Reuses SSH authentication for up to one idle hour.
Passwords and tokens are never saved. Host-key verification remains enabled.

Configuration:
  BGU_CLUSTER_USER         Required BGU cluster username.
  BGU_VPN_USER             VPN username, including @vpn, when VPN login is needed.
  BGU_AZURE_SUBSCRIPTION   Optional Azure subscription ID or name.
  BGU_VM_SSH_KEY           Optional VM private-key path.

Examples:
  bgu-cluster connect
  bgu-cluster run 'hostname; whoami'
  bgu-cluster run 'cat > ~/job.sh' < ./job.sh
  bgu-cluster run 'sbatch ~/job.sh'
  bgu-cluster run 'squeue -u "$USER"'
EOF
}

fail() {
    printf 'bgu-cluster: %s\n' "$*" >&2
    exit 1
}

mode="${1:-shell}"
case "$mode" in
    -h|--help)
        usage
        exit 0
        ;;
    shell|connect|disconnect)
        [[ $# -le 1 ]] || { usage >&2; exit 2; }
        ;;
    run)
        [[ $# -eq 2 && -n "$2" ]] || { usage >&2; exit 2; }
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

command -v ssh >/dev/null || fail "OpenSSH is required."
[[ "$cluster_user" =~ ^[a-zA-Z0-9._-]+$ ]] \
    || fail "Set BGU_CLUSTER_USER to your BGU cluster username."
cluster="$cluster_user@slurm.bgu.ac.il"
socket="$socket_dir/%r@%h"

if [[ "$mode" == disconnect ]]; then
    exec ssh -S "$socket" -O exit "$cluster"
fi

umask 077
mkdir -p "$socket_dir"
chmod 700 "$socket_dir"

if ! ssh -S "$socket" -O check "$cluster" >/dev/null 2>&1; then
    command -v az >/dev/null || fail "Azure CLI is required; sign in with az login."
    [[ -r "$key" ]] || fail "Private key not found: $key"

    azure_options=(-g "$resource_group" -n "$vm_name")
    if [[ -n "$subscription" ]]; then
        azure_options+=(--subscription "$subscription")
    fi
    state="$(az vm get-instance-view "${azure_options[@]}" \
        --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" \
        --output tsv)"
    if [[ "$state" != PowerState/running ]]; then
        printf 'Starting Azure VM %s...\n' "$vm_name" >&2
        az vm start "${azure_options[@]}" --only-show-errors --output none
    fi

    ip="$(az vm show "${azure_options[@]}" --show-details \
        --query publicIps --output tsv)"
    [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || fail "Expected one VM public IPv4 address, got: $ip"
    vm="azureuser@$ip"
    vm_options=(-i "$key" -o IdentitiesOnly=yes -o BatchMode=yes
        -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3
        -o ForwardAgent=no)

    printf 'Waiting for SSH on %s...\n' "$vm" >&2
    ready=false
    for ((attempt=1; attempt<=12; attempt++)); do
        if ssh "${vm_options[@]}" "$vm" true </dev/null 2>/dev/null; then
            ready=true
            break
        fi
        sleep 5
    done
    if [[ "$ready" != true ]]; then
        ssh "${vm_options[@]}" "$vm" true </dev/null
        fail "VM SSH is not ready."
    fi

    if ! ssh "${vm_options[@]}" "$vm" \
        'ip -4 addr show dev tunsnx 2>/dev/null | grep -q "inet "' </dev/null; then
        [[ -n "$vpn_user" ]] || fail "Set BGU_VPN_USER to your VPN username, including @vpn."
        [[ -t 0 ]] || fail "VPN login required. Run '~/scripts/bgu-cluster connect' in a terminal."
        printf 'Enter a fresh BGU VPN token at the password prompt.\n' >&2
        printf -v vpn_command '%q ' snx -s vpn.bgu.ac.il -u "$vpn_user"
        ssh -t "${vm_options[@]}" "$vm" "$vpn_command"
    fi

    printf -v vpn_check '%q ' bash -c \
        'timeout 10 bash -c '\''exec 3<>/dev/tcp/slurm.bgu.ac.il/22; IFS= read -r banner <&3; [[ "$banner" == SSH-* ]]'\'''
    ssh "${vm_options[@]}" "$vm" "$vpn_check" </dev/null \
        || fail "The VPN cannot reach cluster SSH. Check SNX on the VM before retrying."

    # Keep the VM key local; forward only the cluster TCP connection through it.
    printf -v proxy '%q ' ssh "${vm_options[@]}" -W '%h:%p' "$vm"
    cluster_options=(-S "$socket" -o ControlMaster=auto -o ControlPersist=1h
        -o "ProxyCommand=$proxy" -o ConnectTimeout=15
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ForwardAgent=no)
    if [[ ! -t 0 ]]; then
        cluster_options+=(-o BatchMode=yes)
    fi
    printf 'Authenticating to %s...\n' "$cluster" >&2
    ssh "${cluster_options[@]}" -MNf "$cluster" \
        || fail "Cluster authentication failed. Run '~/scripts/bgu-cluster connect' in a terminal."
    ssh -S "$socket" -O check "$cluster" >/dev/null 2>&1 \
        || fail "The cluster connection did not remain open."
fi

case "$mode" in
    connect)
        printf 'Cluster connection ready. Use: ~/scripts/bgu-cluster run '\''COMMAND'\''\n'
        ;;
    shell)
        exec ssh -S "$socket" -o ControlMaster=no -o BatchMode=yes \
            -o ProxyCommand=false -t "$cluster"
        ;;
    run)
        exec ssh -S "$socket" -o ControlMaster=no -o BatchMode=yes \
            -o ProxyCommand=false -T "$cluster" "$2"
        ;;
esac

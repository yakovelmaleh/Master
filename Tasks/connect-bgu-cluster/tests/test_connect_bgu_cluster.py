import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import unittest


SCRIPT = str(Path(__file__).resolve().parents[1] / "connect_bgu_cluster.sh")
MOCK = r"""#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["MOCK_ROOT"])
with (root / "calls").open("a") as out:
    out.write(json.dumps([name, args]) + "\n")
if name == "az":
    if "get-instance-view" in args:
        print(os.environ.get("VM_STATE", "PowerState/running"))
    elif "show" in args:
        print("203.0.113.8")
elif name == "ssh":
    if "-O" in args:
        if "check" in args:
            sys.exit(0 if (root / "master").exists() else 1)
        if "exit" in args:
            (root / "master").unlink(missing_ok=True)
    elif "-MNf" in args:
        if os.environ.get("AUTH_FAIL") == "1":
            sys.exit(255)
        (root / "master").touch()
    elif args[-1] == "true":
        counter = root / "probes"
        count = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(count))
        sys.exit(255 if count <= int(os.environ.get("SSH_FAILURES", "0")) else 0)
    elif "ip -4 addr show" in args[-1]:
        sys.exit(1 if os.environ.get("VPN_DOWN") == "1" else 0)
    elif args[-1].startswith("snx "):
        sys.exit(int(os.environ.get("VPN_LOGIN_EXIT", "0")))
    elif "dev/tcp/" in args[-1]:
        sys.exit(1 if os.environ.get("UNREACHABLE") == "1" else 0)
    elif "-T" in args:
        print("CLUSTER_COMMAND=" + args[-1])
        sys.stdout.write(sys.stdin.read())
        sys.exit(int(os.environ.get("COMMAND_EXIT", "0")))
"""


class ClusterScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bgu-cluster-tests-")
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("az", "ssh", "sleep"):
            path = self.bin / name
            path.write_text(MOCK)
            path.chmod(0o700)
        self.home = self.root / "home with spaces"
        (self.home / "Downloads").mkdir(parents=True)
        (self.home / "Downloads/Master-VM.pem").touch()
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            MOCK_ROOT=str(self.root),
            BGU_CLUSTER_USER="researcher",
            BGU_VPN_USER="researcher@vpn",
            BGU_AZURE_SUBSCRIPTION="test-subscription",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, data="", **env):
        return subprocess.run(
            ["/bin/bash", SCRIPT, *args],
            input=data,
            text=True,
            capture_output=True,
            env=dict(self.env, **env),
            timeout=10,
        )

    def calls(self, tool=None):
        path = self.root / "calls"
        calls = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [args for name, args in calls if tool is None or name == tool]

    def test_running_vm_and_vpn_authenticate_without_start_or_token(self):
        result = self.run_script("connect")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any("start" in args for args in self.calls("az")))
        self.assertFalse(any(args[-1].startswith("snx ") for args in self.calls("ssh")))
        master = next(args for args in self.calls("ssh") if "-MNf" in args)
        self.assertIn("BatchMode=yes", master)
        self.assertIn("ControlPersist=1h", master)
        proxy = next(arg for arg in master if arg.startswith("ProxyCommand="))
        self.assertIn("home\\ with\\ spaces", proxy)
        self.assertNotIn("StrictHostKeyChecking=no", proxy)
        self.assertEqual((self.home / ".ssh/bgu-cluster").stat().st_mode & 0o777, 0o700)

    def test_stopped_vm_is_started_and_current_public_ip_is_used(self):
        result = self.run_script("connect", VM_STATE="PowerState/deallocated", SSH_FAILURES="2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum("start" in args for args in self.calls("az")), 1)
        probes = [args for args in self.calls("ssh") if args[-1] == "true"]
        self.assertEqual(len(probes), 3)
        self.assertTrue(all("azureuser@203.0.113.8" in args for args in probes))

    def test_existing_master_skips_vm_setup_and_preserves_command_and_stdin(self):
        (self.root / "master").touch()
        command = "printf '%s\\n' 'a b'; cat > ~/job.sh"
        result = self.run_script("run", command, data="#!/bin/bash\necho job\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("az"), [])
        self.assertIn("CLUSTER_COMMAND=" + command, result.stdout)
        self.assertIn("#!/bin/bash\necho job\n", result.stdout)
        final = self.calls("ssh")[-1]
        self.assertIn("ProxyCommand=false", final)
        self.assertEqual(final[-1], command)

    def test_command_exit_status_is_preserved(self):
        (self.root / "master").touch()
        result = self.run_script("run", "exit 42", COMMAND_EXIT="42")
        self.assertEqual(result.returncode, 42)

    def test_vpn_requires_interactive_login_instead_of_hanging(self):
        result = self.run_script("connect", VPN_DOWN="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("VPN login required", result.stderr)
        self.assertFalse((self.root / "master").exists())

    def test_vpn_unreachable_prevents_cluster_login(self):
        result = self.run_script("connect", UNREACHABLE="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot reach cluster SSH", result.stderr)
        self.assertFalse(any("-MNf" in args for args in self.calls("ssh")))

    def test_auth_failure_does_not_run_the_job(self):
        result = self.run_script("run", "sbatch ~/job.sh", AUTH_FAIL="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Cluster authentication failed", result.stderr)
        self.assertNotIn("CLUSTER_COMMAND=", result.stdout)

    def test_interactive_vpn_uses_requested_username(self):
        master_fd, slave_fd = pty.openpty()
        try:
            process = subprocess.Popen(
                ["/bin/bash", SCRIPT, "connect"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=dict(self.env, VPN_DOWN="1"),
            )
            os.close(slave_fd)
            slave_fd = None
            output = b""
            while process.poll() is None:
                if select.select([master_fd], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master_fd, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output += chunk
            self.assertEqual(process.wait(timeout=10), 0, output.decode())
        finally:
            os.close(master_fd)
            if slave_fd is not None:
                os.close(slave_fd)
        vpn = [args for args in self.calls("ssh") if args[-1].startswith("snx ")]
        self.assertEqual(len(vpn), 1)
        self.assertEqual(vpn[0][-1].strip(), "snx -s vpn.bgu.ac.il -u researcher@vpn")
        self.assertIn("-t", vpn[0])

    def test_disconnect_only_closes_cluster_ssh(self):
        (self.root / "master").touch()
        result = self.run_script("disconnect")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "master").exists())
        self.assertEqual(self.calls("az"), [])
        self.assertEqual(len(self.calls("ssh")), 1)

    def test_missing_cluster_user_fails_before_network_access(self):
        result = self.run_script("connect", BGU_CLUSTER_USER="")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Set BGU_CLUSTER_USER", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_vpn_user_fails_before_requesting_a_token(self):
        result = self.run_script("connect", VPN_DOWN="1", BGU_VPN_USER="")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Set BGU_VPN_USER", result.stderr)
        self.assertFalse(any(args[-1].startswith("snx ") for args in self.calls("ssh")))

    def test_omitting_subscription_uses_the_azure_cli_default(self):
        result = self.run_script("connect", BGU_AZURE_SUBSCRIPTION="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.calls("az"))
        self.assertFalse(any("--subscription" in args for args in self.calls("az")))

    def test_help_requires_no_configuration_or_network_access(self):
        result = self.run_script("--help", BGU_CLUSTER_USER="", BGU_VPN_USER="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage:", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_usage_errors_do_not_connect(self):
        for args in (["run"], ["run", ""], ["run", "one", "two"], ["unknown"]):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

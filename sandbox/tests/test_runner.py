"""Standalone runner tests; real Docker checks require explicit opt-in."""

from __future__ import annotations

import http.client
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from sandbox.runner import (
    Config,
    Execution,
    Registry,
    RunnerServer,
    StateLease,
    validate_request,
)


class RequestValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(token="test-" + "x" * 32, image="sandbox:fixed")
        self.request = {
            "script": "def main(x): return x",
            "function": "main",
            "payload": {},
        }

    def test_client_cannot_choose_image_command_mount_or_environment(self):
        for field in ("image", "command", "mounts", "env", "codePath", "sdk", "docker"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_request(
                    {**self.request, field: "attacker-controlled"}, self.config
                )

    def test_function_timeout_and_body_types_are_validated(self):
        for values in (
            {"function": "os.system"},
            {"timeoutSeconds": 9999},
            {"timeoutSeconds": True},
            {"context": []},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_request({**self.request, **values}, self.config)

    def test_token_and_fixed_image_are_mandatory(self):
        for token, image in (
            ("short", "sandbox:fixed"),
            ("x" * 32, "--privileged"),
            ("x" * 32, ""),
        ):
            with self.subTest(image=image), self.assertRaises(ValueError):
                Config(token=token, image=image)

    def test_owner_lease_is_exclusive_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            lease = StateLease(directory)
            owner = lease.owner_id
            try:
                with self.assertRaises(OSError):
                    StateLease(directory)
            finally:
                lease.close()
            restarted = StateLease(directory)
            try:
                self.assertEqual(restarted.owner_id, owner)
            finally:
                restarted.close()

    def test_rpc_ids_keep_type_and_reject_boolean_or_stale_replies(self):
        for rpc_id in (1, "rpc-1"):
            execution = Execution(Registry(self.config), {"timeoutSeconds": 10})
            execution.put(
                {
                    "type": "rpc",
                    "id": rpc_id,
                    "resource": "graph",
                    "method": "execute_read",
                    "args": [],
                    "kwargs": {},
                }
            )
            event = execution.next_event()
            self.assertEqual(event["id"], rpc_id)
            captured = []
            execution.write_stdin = captured.append
            for wrong_id in (True, 2, "stale"):
                with self.assertRaises(ValueError):
                    execution.reply({"id": wrong_id, "result": None})
            execution.reply({"id": rpc_id, "result": 7})
            self.assertEqual(captured, [{"id": rpc_id, "result": 7}])
            with self.assertRaises(ValueError):
                execution.reply({"id": rpc_id, "result": 8})
        for invalid in (True, False, 0, -1, [], "bad/id"):
            execution = Execution(Registry(self.config), {"timeoutSeconds": 10})
            execution.put(
                {
                    "type": "rpc",
                    "id": invalid,
                    "resource": "graph",
                    "method": "execute_read",
                    "args": [],
                    "kwargs": {},
                }
            )
            with self.assertRaises(ValueError):
                execution.next_event()


@unittest.skipUnless(
    os.getenv("SANDBOX_DOCKER_TEST") == "1", "requires explicit real Docker test opt-in"
)
class DockerIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "test-" + secrets.token_hex(24)
        cls.config = Config(
            token=cls.token,
            image=os.environ.get(
                "SCRIPT_SANDBOX_TEST_IMAGE", "techkg-script-sandbox:test"
            ),
            concurrency=1,
            max_timeout=30,
            memory_mb=128,
            pids=16,
        )
        cls.server = RunnerServer(("127.0.0.1", 0), cls.config)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, method, path, body=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=35)
        connection.request(
            method,
            path,
            json.dumps(body) if body is not None else None,
            {
                "Authorization": "Bearer " + (self.token if token is None else token),
                "Content-Type": "application/json",
            },
        )
        return connection, connection.getresponse()

    def execute(self, script, *, context=None, payload=None, timeout=15, callback=None):
        connection, response = self.request(
            "POST",
            "/execute",
            {
                "script": script,
                "function": "main",
                "payload": payload or {},
                "context": context or {},
                "timeoutSeconds": timeout,
            },
        )
        self.assertEqual(
            response.status, 200, response.read() if response.status != 200 else ""
        )
        events = []
        try:
            while True:
                raw = response.readline()
                if not raw:
                    break
                event = json.loads(raw)
                events.append(event)
                if event["type"] == "rpc":
                    self.assertIsNotNone(callback)
                    reply = {"id": event["id"], "result": callback(event)}
                    client, answer = self.request(
                        "POST", f"/runs/{event['runId']}/reply", reply
                    )
                    self.assertEqual(answer.status, 200, answer.read())
                    client.close()
        finally:
            response.close()
            connection.close()
        self.assertEqual(events[0]["type"], "ready")
        self.assertIn(events[-1]["type"], {"result", "error"})
        return events

    def assertClean(self):
        deadline = time.monotonic() + 12
        last = ""
        while time.monotonic() < deadline:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    f"label=techkg.script-runner={self.server.registry.instance_id}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            last = result.stdout.strip()
            with self.server.registry.lock:
                idle = not self.server.registry.runs
            if not last and idle:
                return
            time.sleep(0.1)
        self.fail(f"runner containers were not removed: {last}")

    def tearDown(self):
        self.server.registry.close()
        self.assertClean()

    def test_files_network_environment_uid_and_capabilities_are_isolated(self):
        script = """
def main(payload):
    import os, socket, pathlib
    checks = {'uid': os.getuid(), 'docker_socket': pathlib.Path('/var/run/docker.sock').exists(),
              'backend_env': pathlib.Path('/app/.env').exists(),
              'tokens': [k for k in os.environ if k.startswith(('MYSQL_', 'WORKFLOW_', 'SCRIPT_RUNNER_'))]}
    try:
        pathlib.Path('/etc/sandbox-escape').write_text('bad')
        checks['root_write'] = True
    except OSError:
        checks['root_write'] = False
    try:
        socket.create_connection(('1.1.1.1', 80), timeout=0.3).close()
        checks['network'] = True
    except OSError:
        checks['network'] = False
    try:
        import infra
        checks['backend_import'] = True
    except ImportError:
        checks['backend_import'] = False
    checks['capabilities'] = [x for x in pathlib.Path('/proc/self/status').read_text().splitlines() if x.startswith('CapEff:')][0].split()[1]
    pathlib.Path('/tmp/output').write_text('allowed')
    checks['tmp'] = pathlib.Path('/tmp/output').read_text()
    return checks
"""
        value = self.execute(script)[-1]["value"]
        self.assertEqual(
            value,
            {
                "uid": 65532,
                "docker_socket": False,
                "backend_env": False,
                "tokens": [],
                "root_write": False,
                "network": False,
                "backend_import": False,
                "capabilities": "0000000000000000",
                "tmp": "allowed",
            },
        )

    def test_sdk_rpc_roundtrip_and_sqlalchemy_compatibility(self):
        script = """
def main(payload):
    from kg_sdk import current_context
    from sqlalchemy import text
    print('normal print stays out of the protocol')
    records = current_context().graph.execute_read('MATCH (n) RETURN n LIMIT 1').records
    return {'records': records, 'sql': str(text('SELECT 1'))}
"""
        seen = []

        def reply(event):
            seen.append(event)
            return {"records": [{"name": "authorized-business-result"}]}

        result = self.execute(
            script, context={"graph": {"space": "private_a"}}, callback=reply
        )[-1]
        self.assertEqual(
            result["value"]["records"], [{"name": "authorized-business-result"}]
        )
        self.assertEqual(result["value"]["sql"], "SELECT 1")
        self.assertEqual(seen[0]["resource"], "graph")
        self.assertEqual(seen[0]["method"], "execute_read")

    def test_fork_limit_is_enforced(self):
        script = """
def main(payload):
    import os, time, signal
    children = []
    limited = False
    try:
        for _ in range(40):
            try:
                pid = os.fork()
            except OSError:
                limited = True
                break
            if pid == 0:
                time.sleep(20)
                os._exit(0)
            children.append(pid)
    finally:
        for pid in children:
            os.kill(pid, signal.SIGKILL)
        for pid in children:
            os.waitpid(pid, 0)
    return {'limited': limited, 'children': len(children)}
"""
        result = self.execute(script)[-1]["value"]
        self.assertTrue(result["limited"])
        self.assertLess(result["children"], 16)

    def test_timeout_removes_container(self):
        events = self.execute("def main(payload):\n    while True: pass", timeout=3)
        self.assertEqual(events[-1]["type"], "error")
        self.assertClean()

    def test_stdout_and_stderr_floods_are_stopped(self):
        for fd in (1, 2):
            with self.subTest(fd=fd):
                events = self.execute(
                    f"def main(payload):\n    import os\n    while True: os.write({fd}, b'x' * 65536)"
                )
                self.assertEqual(events[-1]["type"], "error")
                self.assertIn("limit", events[-1]["message"])
                self.assertClean()

    def test_disconnect_and_cancel_remove_containers(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                client, response = self.request(
                    "POST",
                    "/execute",
                    {
                        "script": "def main(x):\n    import time\n    time.sleep(25)",
                        "function": "main",
                        "payload": {},
                        "timeoutSeconds": 30,
                    },
                )
                ready = json.loads(response.readline())
                if cancel:
                    other, answer = self.request("DELETE", f"/runs/{ready['runId']}")
                    self.assertEqual(answer.status, 200, answer.read())
                    other.close()
                response.close()
                client.close()
                self.assertClean()

    def test_concurrency_and_stale_reply_are_rejected(self):
        client, response = self.request(
            "POST",
            "/execute",
            {
                "script": "def main(x):\n    import time\n    time.sleep(20)",
                "function": "main",
                "payload": {},
                "timeoutSeconds": 25,
            },
        )
        ready = json.loads(response.readline())
        try:
            for path, value, status in (
                (
                    "/execute",
                    {
                        "script": "def main(x): return x",
                        "function": "main",
                        "payload": {},
                        "timeoutSeconds": 10,
                    },
                    429,
                ),
                (
                    f"/runs/{ready['runId']}/reply",
                    {"id": "not-pending", "result": {}},
                    409,
                ),
            ):
                other, answer = self.request("POST", path, value)
                self.assertEqual(answer.status, status, answer.read())
                other.close()
        finally:
            response.close()
            client.close()

    def test_authentication_is_required(self):
        client, response = self.request("POST", "/execute", {}, token="forged")
        self.assertEqual(response.status, 401, response.read())
        client.close()

    def test_memory_limit_stops_oversized_allocation(self):
        events = self.execute(
            "def main(x):\n    return len(bytearray(512 * 1024 * 1024))"
        )
        self.assertEqual(events[-1]["type"], "error")
        self.assertClean()

    def test_crashed_runner_recovers_only_its_persisted_owner(self):
        foreign = "techkg-script-test-foreign-" + secrets.token_hex(12)
        child = None
        with tempfile.TemporaryDirectory(prefix="sandbox-owner-") as directory:
            code = """
import json, sys, time
from sandbox.runner import Config, StateLease, Registry, Execution
lease = StateLease(sys.argv[1])
registry = Registry(Config(token='x'*32, image=sys.argv[2]), lease.owner_id)
execution = Execution(registry, {'script': 'def main(x):\\n    while True: pass',
    'function': 'main', 'payload': {}, 'context': {}, 'timeoutSeconds': 300})
execution.start()
print(json.dumps({'owner': lease.owner_id, 'name': execution.name}), flush=True)
time.sleep(300)
"""
            owned = None
            try:
                child = subprocess.Popen(
                    [sys.executable, "-u", "-c", code, directory, self.config.image],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                owned = json.loads(child.stdout.readline())
                with self.assertRaises(OSError):
                    StateLease(directory)
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "-d",
                        "--name",
                        foreign,
                        "--network=none",
                        "--label",
                        "techkg.script-owner=" + secrets.token_hex(16),
                        "--entrypoint",
                        "python",
                        self.config.image,
                        "-c",
                        "import time; time.sleep(60)",
                    ],
                    capture_output=True,
                    check=True,
                    timeout=15,
                )
                child.kill()
                child.wait(timeout=5)
                lease = StateLease(directory)
                try:
                    self.assertEqual(lease.owner_id, owned["owner"])
                    lease.recover("docker")
                finally:
                    lease.close()
                self.assertNotEqual(
                    subprocess.run(
                        ["docker", "inspect", owned["name"]],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    ).returncode,
                    0,
                )
                self.assertEqual(
                    subprocess.run(
                        ["docker", "inspect", foreign],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    ).returncode,
                    0,
                )
            finally:
                if child is not None:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=5)
                for name in (foreign, owned["name"] if owned else None):
                    if name:
                        subprocess.run(
                            ["docker", "rm", "--force", name],
                            capture_output=True,
                            timeout=15,
                            check=False,
                        )


if __name__ == "__main__":
    unittest.main()

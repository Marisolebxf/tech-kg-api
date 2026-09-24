"""Trusted Docker runner. Only this service may access the Docker daemon.

The child image receives public JSON over stdin, never host mounts or credentials.
No business clients or backend modules are imported by this service.
"""

from __future__ import annotations

import hmac
import json
import os
import queue
import re
import secrets
import select
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_REQUEST = 32 * 1024 * 1024
MAX_SCRIPT = 2 * 1024 * 1024
MAX_LINE = 16 * 1024 * 1024
MAX_OUTPUT = 64 * 1024 * 1024
MAX_STDERR = 1024 * 1024
MAX_RPC = 8 * 1024 * 1024
MAX_RPCS = 1024
MAX_REPLY = 8 * 1024 * 1024
FUNCTION = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
RPC_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,255}\Z")


def encode(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()


def decode(value: bytes):
    def reject_constant(_):
        raise ValueError("non-finite JSON value")

    return json.loads(value, parse_constant=reject_constant)


@dataclass(frozen=True)
class Config:
    token: str
    image: str
    docker: str = "docker"
    concurrency: int = 4
    max_timeout: int = 3600
    memory_mb: int = 256
    cpus: float = 1.0
    pids: int = 32

    def __post_init__(self):
        if not 32 <= len(self.token) <= 512:
            raise ValueError("SCRIPT_RUNNER_TOKEN must contain 32 to 512 characters")
        if not IMAGE.fullmatch(self.image):
            raise ValueError("a fixed SCRIPT_SANDBOX_IMAGE is required")
        if not 1 <= self.concurrency <= 32 or not 1 <= self.max_timeout <= 86400:
            raise ValueError("invalid concurrency or timeout limit")
        if (
            not 64 <= self.memory_mb <= 4096
            or not 0.1 <= self.cpus <= 4
            or not 8 <= self.pids <= 128
        ):
            raise ValueError("invalid container resource limits")

    @classmethod
    def from_env(cls):
        return cls(
            token=os.environ.get("SCRIPT_RUNNER_TOKEN", ""),
            image=os.environ.get("SCRIPT_SANDBOX_IMAGE", ""),
            concurrency=int(os.getenv("SCRIPT_RUNNER_CONCURRENCY", "4")),
            max_timeout=int(os.getenv("SCRIPT_SANDBOX_MAX_SECONDS", "3600")),
            memory_mb=int(os.getenv("SCRIPT_SANDBOX_MEMORY_MB", "256")),
            cpus=float(os.getenv("SCRIPT_SANDBOX_CPUS", "1")),
            pids=int(os.getenv("SCRIPT_SANDBOX_PIDS", "32")),
        )


class StateLease:
    """Persistent single-owner lease; held until all execution containers stop."""

    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = (directory / "owner.lock").open("a+b", buffering=0)
        os.set_inheritable(self.file.fileno(), False)
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.file.seek(0)
            raw = self.file.read(128).strip()
            if raw and not re.fullmatch(rb"[a-f0-9]{32}", raw):
                raise ValueError("invalid persisted runner owner")
            self.owner_id = raw.decode() if raw else secrets.token_hex(16)
            if not raw:
                self.file.write(self.owner_id.encode() + b"\n")
                self.file.flush()
                os.fsync(self.file.fileno())
        except BaseException:
            self.file.close()
            raise

    def recover(self, docker):
        # The exclusive owner lease prevents a second live runner sharing this
        # volume. Only our labeled, structurally valid container names qualify.
        result = subprocess.run(
            [
                docker,
                "ps",
                "--all",
                "--filter",
                f"label=techkg.script-owner={self.owner_id}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        pattern = re.compile(
            rf"techkg-script-{self.owner_id}-[a-f0-9]{{16}}-[a-f0-9]{{32}}\Z"
        )
        for name in result.stdout.splitlines():
            if not pattern.fullmatch(name):
                raise RuntimeError(
                    "unexpected container name for persisted runner owner"
                )
            subprocess.run(
                [docker, "rm", "--force", name],
                capture_output=True,
                timeout=30,
                check=True,
            )

    def close(self):
        self.file.close()


class Execution:
    def __init__(self, registry, request):
        self.registry = registry
        self.config = registry.config
        self.run_id = secrets.token_hex(16)
        self.name = f"{registry.prefix}{self.run_id}"
        self.request = request
        self.deadline = time.monotonic() + request["timeoutSeconds"]
        self.events = queue.Queue(maxsize=8)
        self.cancelled = threading.Event()
        self.reason = "execution cancelled"
        self.process = None
        self.pending_id = None
        self.rpc_count = 0
        self.output_bytes = 0
        self.pending_lock = threading.Lock()
        self.stdin_lock = threading.Lock()
        self.cleanup_lock = threading.Lock()
        self.timer = threading.Timer(
            request["timeoutSeconds"], self.abort, args=("execution timed out",)
        )
        self.timer.daemon = True

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if self.cancelled.is_set() or remaining <= 0:
            raise RuntimeError(self.reason)
        return remaining

    def docker(self, *args):
        result = subprocess.run(
            [self.config.docker, *args],
            capture_output=True,
            timeout=min(30, self.remaining()),
            check=False,
        )
        if result.returncode:
            raise RuntimeError("sandbox container could not be prepared")

    def start(self):
        self.timer.start()
        self.docker(
            "create",
            "--pull=never",
            "--name",
            self.name,
            "--label",
            f"techkg.script-runner={self.registry.instance_id}",
            "--label",
            f"techkg.script-owner={self.registry.owner_id}",
            "--interactive",
            "--init",
            "--network=none",
            "--ipc=none",
            "--read-only",
            "--user=65532:65532",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            f"--pids-limit={self.config.pids}",
            f"--cpus={self.config.cpus}",
            f"--memory={self.config.memory_mb}m",
            f"--memory-swap={self.config.memory_mb}m",
            "--ulimit=nofile=128:128",
            "--ulimit=core=0:0",
            "--log-driver=none",
            "--stop-timeout=1",
            "--workdir=/tmp",
            "--hostname=script-sandbox",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
            self.config.image,
        )
        self.remaining()
        self.process = subprocess.Popen(
            [self.config.docker, "start", "--attach", "--interactive", self.name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self.read_stdout, daemon=True).start()
        threading.Thread(target=self.read_stderr, daemon=True).start()
        threading.Thread(target=self.write_boot, daemon=True).start()

    def put(self, item):
        while not self.cancelled.is_set():
            try:
                self.events.put(item, timeout=0.2)
                return
            except queue.Full:
                continue

    def write_boot(self):
        try:
            self.write_stdin(self.request)
        except (OSError, RuntimeError, ValueError):
            self.abort("sandbox input could not be delivered")

    def write_stdin(self, message):
        data = encode(message) + b"\n"
        with self.stdin_lock:
            self.remaining()
            self.process.stdin.write(data)
            self.process.stdin.flush()

    def read_stdout(self):
        try:
            while not self.cancelled.is_set():
                line = self.process.stdout.readline(MAX_LINE + 1)
                if not line:
                    self.put({"type": "eof"})
                    return
                self.output_bytes += len(line)
                if len(line) > MAX_LINE or self.output_bytes > MAX_OUTPUT:
                    self.abort("sandbox output limit exceeded")
                    return
                value = decode(line)
                if not isinstance(value, dict):
                    raise TypeError("invalid sandbox protocol")
                self.put(value)
        except (OSError, ValueError, TypeError, RecursionError):
            self.abort("invalid sandbox output")

    def read_stderr(self):
        total = 0
        try:
            while not self.cancelled.is_set():
                chunk = self.process.stderr.read1(8192)
                if not chunk:
                    return
                total += len(chunk)
                if total > MAX_STDERR:
                    self.abort("sandbox diagnostic output limit exceeded")
                    return
        except (OSError, ValueError):
            pass

    def next_event(self):
        self.remaining()
        try:
            message = self.events.get(timeout=min(0.2, self.remaining()))
        except queue.Empty:
            return None
        kind = message.get("type")
        if kind == "rpc":
            self.rpc_count += 1
            if self.rpc_count > MAX_RPCS or len(encode(message)) > MAX_RPC:
                raise ValueError("sandbox RPC limit exceeded")
            if set(message) != {"type", "id", "resource", "method", "args", "kwargs"}:
                raise ValueError("invalid RPC fields")
            rpc_id = message["id"]
            if not (
                (type(rpc_id) is int and 0 < rpc_id < 2**53)
                or (isinstance(rpc_id, str) and RPC_ID.fullmatch(rpc_id))
            ):
                raise ValueError("invalid RPC id")
            if not isinstance(message["resource"], str) or not FUNCTION.fullmatch(
                message["resource"]
            ):
                raise ValueError("invalid RPC resource")
            if not isinstance(message["method"], str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.]{0,127}", message["method"]
            ):
                raise ValueError("invalid RPC method")
            if not isinstance(message["args"], list) or not isinstance(
                message["kwargs"], dict
            ):
                raise ValueError("invalid RPC arguments")
            with self.pending_lock:
                if self.pending_id is not None:
                    raise ValueError("only one RPC may be pending")
                self.pending_id = message["id"]
            return {**message, "runId": self.run_id}
        if kind == "result" and set(message) == {"type", "value"}:
            with self.pending_lock:
                if self.pending_id is not None:
                    raise ValueError("result arrived before RPC reply")
            return message
        if kind == "error" and set(message) == {"type", "message"}:
            if not isinstance(message["message"], str):
                raise ValueError("invalid error message")
            return {"type": "error", "message": message["message"][:4096]}
        raise ValueError("sandbox process ended without a valid result")

    def reply(self, message):
        if not isinstance(message, dict) or set(message) not in (
            {"id", "result"},
            {"id", "error"},
        ):
            raise ValueError("invalid RPC reply")
        with self.pending_lock:
            if (
                self.pending_id is None
                or type(message["id"]) is not type(self.pending_id)
                or message["id"] != self.pending_id
            ):
                raise ValueError("reply does not match the pending RPC")
            self.pending_id = None
        self.write_stdin(message)

    def abort(self, reason):
        if not self.cancelled.is_set():
            self.reason = reason
            self.cancelled.set()
        self.cleanup()

    def cleanup(self):
        # Always retry the exact owned name in finally, including after a create timeout.
        # Never enumerate, delete by user input, or clean another runner's containers.
        with self.cleanup_lock:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()
            if (
                not self.name.startswith(self.registry.prefix)
                or self.name != self.registry.prefix + self.run_id
            ):
                raise RuntimeError("refusing cleanup of an unowned container")
            try:
                subprocess.run(
                    [self.config.docker, "rm", "--force", self.name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                # The request's finally retries; no other container is ever targeted.
                pass
            if self.process is not None:
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                if self.process.poll() is not None:
                    for pipe in (
                        self.process.stdin,
                        self.process.stdout,
                        self.process.stderr,
                    ):
                        try:
                            pipe.close()
                        except (OSError, ValueError):
                            pass

    def close(self):
        self.timer.cancel()
        self.cancelled.set()
        self.cleanup()
        self.registry.remove(self.run_id)


class Registry:
    def __init__(self, config, owner_id=None):
        self.config = config
        self.instance_id = secrets.token_hex(8)
        self.owner_id = owner_id or secrets.token_hex(16)
        self.prefix = f"techkg-script-{self.owner_id}-{self.instance_id}-"
        self.runs = {}
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(config.concurrency)

    def add(self, execution):
        with self.lock:
            self.runs[execution.run_id] = execution

    def get(self, run_id):
        with self.lock:
            return self.runs.get(run_id)

    def remove(self, run_id):
        with self.lock:
            self.runs.pop(run_id, None)

    def close(self):
        with self.lock:
            runs = list(self.runs.values())
        for run in runs:
            run.abort("runner shutting down")


def validate_request(value, config):
    if not isinstance(value, dict) or set(value) - {
        "script",
        "function",
        "payload",
        "context",
        "timeoutSeconds",
    }:
        raise ValueError(
            "only script, function, payload, context and timeoutSeconds are accepted"
        )
    script = value.get("script")
    function = value.get("function")
    timeout = value.get("timeoutSeconds", 60)
    if not isinstance(script, str) or not 1 <= len(script.encode()) <= MAX_SCRIPT:
        raise ValueError("script size is invalid")
    if not isinstance(function, str) or not FUNCTION.fullmatch(function):
        raise ValueError("function must be a top-level Python name")
    if not isinstance(value.get("context", {}), dict) or "payload" not in value:
        raise ValueError("public context and payload are required")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 1 <= timeout <= config.max_timeout
    ):
        raise ValueError("execution timeout is outside the permitted range")
    return {**value, "context": value.get("context", {}), "timeoutSeconds": timeout}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ScriptRunner"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_args):
        pass  # Do not log request bodies, tokens, scripts or returned data.

    def authenticated(self):
        expected = "Bearer " + self.server.registry.config.token
        supplied = self.headers.get("Authorization", "")
        return len(supplied) <= 1024 and hmac.compare_digest(
            supplied.encode(), expected.encode()
        )

    def respond(self, status, value):
        body = encode(value)
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def body(self, limit):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("chunked request bodies are not accepted")
        raw_length = self.headers.get_all("Content-Length", [])
        if len(raw_length) != 1 or not raw_length[0].isdigit():
            raise ValueError("one Content-Length header is required")
        size = int(raw_length[0])
        if not 0 < size <= limit:
            raise ValueError("request body limit exceeded")
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError("incomplete request body")
        return decode(data)

    def emit(self, event):
        self.wfile.write(encode(event) + b"\n")
        self.wfile.flush()

    def disconnected(self):
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except OSError:
            return True

    def do_POST(self):
        if not self.authenticated():
            self.respond(401, {"error": "unauthorized"})
            return
        if self.path == "/execute":
            self.execute()
            return
        match = re.fullmatch(r"/runs/([a-f0-9]{32})/reply", self.path)
        if match:
            execution = self.server.registry.get(match.group(1))
            if execution is None:
                self.respond(404, {"error": "run not found"})
                return
            try:
                execution.reply(self.body(MAX_REPLY))
            except (ValueError, RuntimeError, OSError, RecursionError):
                self.respond(409, {"error": "invalid or expired RPC reply"})
                return
            self.respond(200, {"ok": True})
            return
        self.respond(404, {"error": "not found"})

    def do_DELETE(self):
        if not self.authenticated():
            self.respond(401, {"error": "unauthorized"})
            return
        match = re.fullmatch(r"/runs/([a-f0-9]{32})", self.path)
        execution = self.server.registry.get(match.group(1)) if match else None
        if execution is None:
            self.respond(404, {"error": "run not found"})
            return
        execution.abort("execution cancelled")
        self.respond(200, {"ok": True})

    def execute(self):
        registry = self.server.registry
        try:
            request = validate_request(self.body(MAX_REQUEST), registry.config)
        except (ValueError, OSError, RecursionError):
            self.respond(400, {"error": "invalid execution request"})
            return
        if not registry.slots.acquire(blocking=False):
            self.respond(429, {"error": "runner concurrency limit reached"})
            return
        execution = Execution(registry, request)
        registry.add(execution)
        started = False
        try:
            execution.start()
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            started = True
            self.emit({"type": "ready", "runId": execution.run_id})
            while True:
                if self.disconnected():
                    execution.abort("execution client disconnected")
                    break
                message = execution.next_event()
                if message is None:
                    continue
                self.emit(message)
                if message["type"] in {"result", "error"}:
                    break
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
            try:
                if started:
                    self.emit(
                        {
                            "type": "error",
                            "message": execution.reason
                            if execution.cancelled.is_set()
                            else "sandbox execution failed",
                        }
                    )
                else:
                    self.respond(503, {"error": "sandbox execution could not start"})
            except OSError:
                pass
        finally:
            execution.close()
            registry.slots.release()


class RunnerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, config, owner_id=None):
        self.registry = Registry(config, owner_id)
        super().__init__(address, Handler)

    def server_close(self):
        self.registry.close()
        super().server_close()


def main():
    config = Config.from_env()
    lease = StateLease(os.getenv("SCRIPT_RUNNER_STATE_DIR", "/var/lib/script-runner"))
    lease.recover(config.docker)
    server = RunnerServer(
        (
            os.getenv("SCRIPT_RUNNER_HOST", "0.0.0.0"),
            int(os.getenv("SCRIPT_RUNNER_PORT", "8099")),
        ),
        config,
        lease.owner_id,
    )

    def stop(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        lease.close()


if __name__ == "__main__":
    main()

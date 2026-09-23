# Uploaded Python script sandbox

The trusted worker selects resources and authorizes each SDK RPC. `script-runner` only starts a fixed image and transports messages. The uploaded script runs as UID/GID 65532 inside a separate Docker container with no network, no host mounts, no Docker socket, a read-only root filesystem and a 64 MiB `/tmp` tmpfs. Capabilities are dropped; privilege escalation, swap growth, excessive processes, CPU and memory use are constrained.

The runtime image contains Python, SQLAlchemy 2.0.42 (`sqlalchemy.text` compatibility), the public SDK and `runtime.py`. It does not contain backend `infra`, `dao`, source trees, environment files or business credentials. Scripts importing backend internals must use the SDK instead. Additional computation libraries require an administrator-built runtime image; scripts cannot install packages from the network or choose a different image.

See [example_extract.py](example_extract.py) for a minimal SDK-only extraction function.

## Build and opt-in deployment

Build contexts are the repository root; Dockerfiles copy only the listed files. Do not use `COPY .`.

```bash
docker build -f sandbox/Dockerfile.runtime -t techkg-script-sandbox:local .
docker build -f sandbox/Dockerfile.runner -t techkg-script-runner:local .
```

Generate and retain a random `SCRIPT_RUNNER_TOKEN` of at least 32 characters. Put it only in the trusted worker and runner environments. `SCRIPT_SANDBOX_IMAGE` is a fixed administrator configuration; the HTTP API cannot override images, commands, files, mounts or environment variables. The worker must send only public context and batch payloads, never resolved connection credentials.

The common overlay adds an internal network, a runner without published ports, and a build-only runtime profile. Select the matching worker overlay, preserving the worker's existing networks:

```bash
docker compose -f docker-compose.dev2.yml -f docker-compose.sandbox.yml -f sandbox/compose.dev2.yml --profile sandbox-build build script-runner script-sandbox-image
docker compose -f docker-compose.dev2.yml -f docker-compose.sandbox.yml -f sandbox/compose.dev2.yml up -d script-runner temporal-worker-dev2
```

For main/gray substitute their base Compose file, `sandbox/compose.main.yml` or `sandbox/compose.gray.yml`, and matching worker service. This overlay is opt-in and does not itself deploy anything. Enabling business RBAC and worker execution mode must follow the main deployment instructions; a worker must fail closed if its required sandbox is unavailable.

The Docker socket exists only in the trusted runner. That grants the runner authority over its Docker host, so it belongs on the trusted private network. Uploaded scripts never receive that socket or the runner token. This is process/container isolation, not a separate kernel or a virtual machine; all containers share the Docker host kernel.

Keep the runner's dedicated `script-runner-state` named volume across restarts. It stores a random owner ID under an exclusive OS file lock. A restarted runner removes only containers carrying that owner label and a matching generated name before serving requests. A second runner sharing the volume fails to acquire the lock, preventing concurrent instances from deleting each other's work. This also recovers execution containers left behind by a killed or OOM-terminated runner; the volume is never mounted into script containers. Deleting this volume discards the recovery identity, so stop the runner and its owned executions before intentionally removing it.

## Protocol and limits

Every request requires `Authorization: Bearer <SCRIPT_RUNNER_TOKEN>`.

`POST /execute` accepts only `{script, function, payload, context, timeoutSeconds}`. `function` is a top-level Python identifier. It returns newline-delimited JSON:

1. `{type:"ready",runId}`
2. Zero or more `{type:"rpc",runId,id,resource,method,args,kwargs}` messages.
3. `{type:"result",value}` or `{type:"error",message}`.

The worker executes each RPC through its authorization broker, then calls `POST /runs/<runId>/reply` with `{id,result}` or `{id,error}`. The runner accepts only the currently pending ID and rejects stale or duplicate replies. There is one pending RPC per run. Optional `DELETE /runs/<runId>` cancels immediately. All three endpoints use the same trusted bearer token.

The initial JSON is sent over the sandbox's stdin before user import. Subsequent stdin lines are RPC replies. Ordinary `print` output goes to stderr. The SDK uses original stdin/stdout for RPC. Protocol messages are untrusted data: the worker must continue to validate every resource and operation even when an uploaded script bypasses the SDK.

Default limits: 32 MiB request, 2 MiB script, 16 MiB output line/result, 64 MiB cumulative stdout, 1 MiB stderr, 8 MiB RPC/reply, 1,024 RPCs, four simultaneous executions, 3,600-second maximum deadline (`SCRIPT_SANDBOX_MAX_SECONDS`, configurable up to 86,400), 256 MiB memory, one CPU and 32 PIDs. The runner owns deadline enforcement, including when the HTTP client disconnects. Timeout, cancellation, protocol failure and normal completion delete only the exact container name generated by this runner instance. If the Docker daemon itself is unreachable, deletion is retried by request cleanup; daemon availability remains necessary to force-remove a running container.

## Verification

Standalone tests live under `sandbox/tests`, independent of backend infrastructure. Unit tests validate input, protocol restrictions and exclusive owner locking. Docker integration tests are explicitly enabled and use the fixed test image; they run actual untrusted code to check network, filesystem, environment, UID/capabilities, PID and memory limits, timeout, output limits, cancellation, concurrency and real SDK RPC round trips. A crash recovery test kills a separate test runner process, reopens its persisted owner lease, removes its orphan execution and checks that another owner is unaffected.

```bash
python -m unittest discover -s sandbox/tests -v
SANDBOX_DOCKER_TEST=1 SCRIPT_SANDBOX_TEST_IMAGE=techkg-script-sandbox:local python -m unittest discover -s sandbox/tests -v
```

These tests create only containers prefixed and labeled for their runner instance, remove them after each test, and do not start or modify the application stack.

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
STACK_COMMON = REPO_ROOT / "scripts" / "stack-common.sh"


class HealthServer:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        self.server = server
        self.thread = thread

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/_local/diagnostics":
            body = json.dumps(
                {
                    "status": "ok",
                    "service_name": "mr-visit-jp-runtime",
                    "prompt_context": {"profile_id": "alpha_baseline_v1", "experiment_id": None},
                    "session_counts": {"total": 1},
                    "recent_sessions": [{"session_id": "sess_diag_001"}],
                }
            ).encode("utf-8")
            self.send_response(200)
        elif self.path == "/healthz":
            body = json.dumps({"status": "ok", "prompt_profile": "alpha_baseline_v1"}).encode(
                "utf-8"
            )
            self.send_response(200)
        else:
            body = json.dumps({"detail": "not found"}).encode("utf-8")
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _start_health_server() -> HealthServer:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    server = ThreadingHTTPServer(("127.0.0.1", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return HealthServer(server=server, thread=thread)


def _run_bash(
    script: str,
    *,
    env: dict[str, str] | None = None,
    cwd: Path = REPO_ROOT,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=cwd,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_stack_load_env_defaults_preserves_explicit_environment(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".env").write_text(
        "WEB_PORT=3999\nHERMES_PORT=4999\nMR_RUNTIME_PORT=5999\n",
        encoding="utf-8",
    )

    result = _run_bash(
        f"""
        set -euo pipefail
        source "{STACK_COMMON}"
        export WEB_PORT=3555
        stack_load_env_defaults "{repo_root}"
        printf 'WEB_PORT=%s\\n' "$WEB_PORT"
        printf 'HERMES_PORT=%s\\n' "$HERMES_PORT"
        printf 'MR_RUNTIME_PORT=%s\\n' "$MR_RUNTIME_PORT"
        """
    )

    assert result.returncode == 0, result.stderr
    assert "WEB_PORT=3555" in result.stdout
    assert "HERMES_PORT=4999" in result.stdout
    assert "MR_RUNTIME_PORT=5999" in result.stdout


def test_stack_service_pid_cleans_stale_pid_file(tmp_path: Path) -> None:
    state_dir = tmp_path / "stack-state"
    state_dir.mkdir()
    pid_file = state_dir / "runtime.pid"
    pid_file.write_text("999999\n", encoding="utf-8")

    result = _run_bash(
        f"""
        set -euo pipefail
        source "{STACK_COMMON}"
        pid="$(stack_service_pid "{state_dir}" runtime)"
        printf 'pid=<%s>\\n' "$pid"
        if [[ -f "{pid_file}" ]]; then
          echo "pid_file=present"
        else
          echo "pid_file=missing"
        fi
        """
    )

    assert result.returncode == 0, result.stderr
    assert "pid=<>" in result.stdout
    assert "pid_file=missing" in result.stdout
    assert not pid_file.exists()


def test_stack_assert_port_available_reports_port_conflict() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]

        result = _run_bash(
            f"""
            set -euo pipefail
            source "{STACK_COMMON}"
            stack_assert_port_available runtime "{port}"
            """
        )

    assert result.returncode != 0
    assert f"runtime port {port} is already in use" in result.stderr


def test_stack_status_reports_health_and_diagnostics_urls(tmp_path: Path) -> None:
    if shutil.which("curl") is None:
        pytest.skip("curl not installed")
    stack_status = REPO_ROOT / "scripts" / "stack-status.sh"
    server = _start_health_server()
    state_dir = tmp_path / "stack-state"
    state_dir.mkdir()
    (state_dir / "runtime.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    (state_dir / "runtime.log").write_text(
        '{"trace_id":"trace_stack_001","session_id":"sess_diag_001"}\n',
        encoding="utf-8",
    )

    try:
        result = _run_bash(
            f'bash "{stack_status}"',
            env={
                "STACK_STATE_DIR": str(state_dir),
                "MR_RUNTIME_PORT": str(server.port),
                "HERMES_PORT": "65531",
                "WEB_PORT": "65532",
            },
        )
    finally:
        server.stop()

    assert result.returncode == 0, result.stderr
    assert f"health_url=http://127.0.0.1:{server.port}/healthz" in result.stdout
    assert f"diagnostics_url=http://127.0.0.1:{server.port}/_local/diagnostics" in result.stdout
    assert '[stack-status] runtime health={"status": "ok", "prompt_profile": "alpha_baseline_v1"}' in result.stdout
    assert '"recent_sessions": [{"session_id": "sess_diag_001"}]' in result.stdout
    assert '"trace_id":"trace_stack_001","session_id":"sess_diag_001"' in result.stdout

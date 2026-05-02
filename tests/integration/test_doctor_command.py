from __future__ import annotations

import importlib.util
import json
import os
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTOR_PATH = REPO_ROOT / "scripts" / "doctor.py"


def _load_doctor_module():
    spec = importlib.util.spec_from_file_location("cosi_doctor", DOCTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


doctor = _load_doctor_module()


@dataclass
class HealthServer:
    server: ThreadingHTTPServer
    thread: threading.Thread

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/healthz"

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"status": "ok"}).encode("utf-8")
        self.send_response(200)
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


def test_redact_env_value_hides_secrets() -> None:
    assert doctor.redact_env_value("OPENAI_API_KEY", "super-secret-value") == "[redacted len=18]"
    assert doctor.redact_env_value("WEB_PORT", "3000") == "3000"
    assert doctor.redact_env_value("MR_RUNTIME_MODEL_API_KEY", "") == "<empty>"


def test_resolve_env_value_prefers_explicit_environment() -> None:
    resolved = doctor.resolve_env_value(
        "WEB_PORT",
        {"WEB_PORT": "3999"},
        "3000",
        environ={"WEB_PORT": "3555"},
    )
    assert resolved.value == "3555"
    assert resolved.source == "env"


def test_check_provider_config_requires_openai_compat_settings() -> None:
    resolved = {
        "MR_RUNTIME_MODEL_MODE": doctor.ResolvedValue(
            name="MR_RUNTIME_MODEL_MODE",
            value="openai_compat",
            source=".env",
        ),
        "MR_RUNTIME_MODEL_API_BASE": doctor.ResolvedValue(
            name="MR_RUNTIME_MODEL_API_BASE",
            value="",
            source=".env",
        ),
        "MR_RUNTIME_MODEL_API_KEY": doctor.ResolvedValue(
            name="MR_RUNTIME_MODEL_API_KEY",
            value="",
            source=".env",
        ),
        "MR_RUNTIME_MODEL_NAME": doctor.ResolvedValue(
            name="MR_RUNTIME_MODEL_NAME",
            value="",
            source=".env",
        ),
    }

    result = doctor.check_provider_config(resolved)

    assert result.level == "FAIL"
    assert "openai_compat mode requires" in result.detail
    assert "MR_RUNTIME_MODEL_API_KEY" in result.detail


def test_validate_domain_assets_passes_for_repo() -> None:
    python_bin = str(REPO_ROOT / ".venv" / "bin" / "python")
    if not Path(python_bin).is_file():
        python_bin = sys.executable
    result = doctor.validate_domain_assets(REPO_ROOT, python_bin)

    assert result.level == "PASS"
    assert "scenarios=8" in result.detail


def test_validate_prompt_assets_passes_for_repo() -> None:
    python_bin = str(REPO_ROOT / ".venv" / "bin" / "python")
    if not Path(python_bin).is_file():
        python_bin = sys.executable
    result = doctor.validate_prompt_assets(REPO_ROOT, python_bin)

    assert result.level == "PASS"
    assert "default_profile=alpha_baseline_v1" in result.detail


def test_validate_evaluation_gates_passes_for_repo() -> None:
    python_bin = str(REPO_ROOT / ".venv" / "bin" / "python")
    if not Path(python_bin).is_file():
        python_bin = sys.executable
    result = doctor.validate_evaluation_gates(REPO_ROOT, python_bin)

    assert result.level == "PASS"
    assert "rollout=active" in result.detail


def test_content_only_mode_exits_zero(capsys) -> None:
    exit_code = doctor.main(["--repo-root", str(REPO_ROOT), "--content-only"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "assets.domain" in captured.out
    assert "assets.evaluation_gates" in captured.out


def test_inspect_service_reports_managed_healthy_service(tmp_path: Path) -> None:
    server = _start_health_server()
    state_dir = tmp_path / "stack-state"
    state_dir.mkdir()
    (state_dir / "runtime.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")

    try:
        result = doctor.inspect_service(
            service=doctor.ServiceDefinition(
                name="runtime",
                port=server.port,
                health_url=server.url,
            ),
            state_dir=state_dir,
            timeout=1.0,
        )
    finally:
        server.stop()

    assert result.level == "PASS"
    assert f"port={server.port}" in result.detail

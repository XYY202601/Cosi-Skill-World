from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


SECRET_NAME_TOKENS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


@dataclass(frozen=True)
class CheckResult:
    level: str
    name: str
    detail: str
    fix: str | None = None


@dataclass(frozen=True)
class ResolvedValue:
    name: str
    value: str
    source: str


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    port: int
    health_url: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose local COSI setup and stack health.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root to inspect.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="HTTP timeout in seconds for service health checks.",
    )
    parser.add_argument(
        "--content-only",
        action="store_true",
        help="Only validate content assets and evaluation gates.",
    )
    return parser


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\r")
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value
    return values


def resolve_env_value(
    name: str,
    env_defaults: dict[str, str],
    default: str | None = None,
    environ: dict[str, str] | None = None,
) -> ResolvedValue:
    active_env = os.environ if environ is None else environ
    if name in active_env:
        return ResolvedValue(name=name, value=active_env[name], source="env")
    if name in env_defaults:
        return ResolvedValue(name=name, value=env_defaults[name], source=".env")
    if default is None:
        return ResolvedValue(name=name, value="", source="missing")
    return ResolvedValue(name=name, value=default, source="default")


def redact_env_value(name: str, value: str) -> str:
    if not value:
        return "<empty>"
    upper_name = name.upper()
    if any(token in upper_name for token in SECRET_NAME_TOKENS):
        return f"[redacted len={len(value)}]"
    return value


def format_resolved_value(resolved: ResolvedValue) -> str:
    return f"{resolved.name}={redact_env_value(resolved.name, resolved.value)} ({resolved.source})"


def pass_result(name: str, detail: str) -> CheckResult:
    return CheckResult(level="PASS", name=name, detail=detail)


def warn_result(name: str, detail: str, fix: str | None = None) -> CheckResult:
    return CheckResult(level="WARN", name=name, detail=detail, fix=fix)


def fail_result(name: str, detail: str, fix: str | None = None) -> CheckResult:
    return CheckResult(level="FAIL", name=name, detail=detail, fix=fix)


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
    )


def normalize_whitespace(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip())
    return collapsed or "<empty>"


def parse_port(resolved: ResolvedValue, name: str) -> tuple[int | None, CheckResult | None]:
    try:
        return int(resolved.value), None
    except ValueError:
        return None, fail_result(
            f"env.{name.lower()}",
            f"{name} must be an integer, got {resolved.value!r} from {resolved.source}",
            fix=f"Update {name} in {resolved.source if resolved.source == 'env' else '.env'} to a numeric port.",
        )


def resolve_python_bin(repo_root: Path) -> str:
    python_candidates = [
        repo_root / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    return next((str(path) for path in python_candidates if path.is_file()), sys.executable)


def check_python_toolchain(repo_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []

    python_name = os.getenv("PYTHON", "python3")
    python_path = shutil.which(python_name)
    if python_path is None:
        return [
            fail_result(
                "tool.python",
                f"Required command not found: {python_name}",
                fix="Install Python 3.11+ and rerun `make bootstrap`.",
            )
        ]

    version_result = run_command(
        [
            python_path,
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
        ]
    )
    version = normalize_whitespace(version_result.stdout or version_result.stderr)
    if version_result.returncode != 0:
        results.append(
            fail_result(
                "tool.python",
                f"Failed to read Python version from {python_path}: {version}",
                fix="Verify your Python installation and rerun `make bootstrap`.",
            )
        )
    else:
        major, minor, *_ = [int(part) for part in version.split(".")]
        if (major, minor) < (3, 11):
            results.append(
                fail_result(
                    "tool.python",
                    f"{python_path} is Python {version}; Python 3.11+ is required.",
                    fix="Install Python 3.11+ and rerun `make bootstrap`.",
                )
            )
        else:
            results.append(pass_result("tool.python", f"{python_path} version={version}"))

    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        results.append(
            fail_result(
                "tool.venv",
                f"Virtualenv interpreter not found at {venv_python}",
                fix="Run `make bootstrap` to create `.venv` and install Python packages.",
            )
        )
        return results

    package_check = run_command(
        [
            str(venv_python),
            "-c",
            (
                "import importlib.metadata as m, json; "
                "packages=['skill-registry','prompt-builder','mr-visit-jp-runtime','gp-visit-jp-runtime','hermes-orchestrator']; "
                "print(json.dumps({name: m.version(name) for name in packages}))"
            ),
        ]
    )
    if package_check.returncode != 0:
        detail = normalize_whitespace(package_check.stderr or package_check.stdout)
        results.append(
            fail_result(
                "tool.venv",
                f".venv exists but required editable packages are missing: {detail}",
                fix=(
                    "Run `make bootstrap` or "
                    "`./.venv/bin/pip install -e packages/skill-registry -e packages/prompt-builder "
                    "-e apps/mr-visit-jp-runtime -e apps/gp-visit-jp-runtime "
                    "-e apps/hermes-orchestrator`."
                ),
            )
        )
    else:
        versions = json.loads(package_check.stdout)
        version_bits = ", ".join(f"{name}={value}" for name, value in sorted(versions.items()))
        results.append(pass_result("tool.venv", f"{venv_python} packages: {version_bits}"))

    return results


def check_node_toolchain(repo_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []

    for command_name in ("node", "pnpm"):
        command_path = shutil.which(command_name)
        if command_path is None:
            results.append(
                fail_result(
                    f"tool.{command_name}",
                    f"Required command not found: {command_name}",
                    fix=f"Install `{command_name}` and rerun `make bootstrap`.",
                )
            )
            continue
        version_result = run_command([command_path, "--version"])
        version = normalize_whitespace(version_result.stdout or version_result.stderr)
        if version_result.returncode != 0:
            results.append(
                fail_result(
                    f"tool.{command_name}",
                    f"Failed to read `{command_name}` version from {command_path}: {version}",
                    fix=f"Verify `{command_name}` and rerun `make bootstrap`.",
                )
            )
        else:
            results.append(pass_result(f"tool.{command_name}", f"{command_path} version={version}"))

    node_modules_dir = repo_root / "node_modules"
    if node_modules_dir.is_dir():
        results.append(pass_result("tool.node_modules", str(node_modules_dir)))
    else:
        results.append(
            fail_result(
                "tool.node_modules",
                f"Missing frontend dependencies at {node_modules_dir}",
                fix="Run `pnpm install` or `make bootstrap`.",
            )
        )
    return results


def check_env_files(
    repo_root: Path,
    env_defaults: dict[str, str],
) -> tuple[list[CheckResult], dict[str, ResolvedValue]]:
    results: list[CheckResult] = []
    env_example = repo_root / ".env.example"
    env_file = repo_root / ".env"

    if env_example.is_file():
        results.append(pass_result("env.example", str(env_example)))
    else:
        results.append(
            fail_result(
                "env.example",
                f"Missing {env_example}",
                fix="Restore `.env.example` from git before running bootstrap.",
            )
        )

    if env_file.is_file():
        results.append(pass_result("env.file", str(env_file)))
    else:
        results.append(
            fail_result(
                "env.file",
                f"Missing {env_file}",
                fix="Run `make bootstrap` or copy `.env.example` to `.env`.",
            )
        )

    resolved = {
        "WEB_PORT": resolve_env_value("WEB_PORT", env_defaults, "3000"),
        "HERMES_PORT": resolve_env_value("HERMES_PORT", env_defaults, "8000"),
        "MR_RUNTIME_PORT": resolve_env_value("MR_RUNTIME_PORT", env_defaults, "8100"),
        "GP_RUNTIME_PORT": resolve_env_value("GP_RUNTIME_PORT", env_defaults, "8200"),
        "MR_RUNTIME_MODEL_MODE": resolve_env_value("MR_RUNTIME_MODEL_MODE", env_defaults, "mock"),
        "MR_RUNTIME_DEMO_SEED_MODE": resolve_env_value(
            "MR_RUNTIME_DEMO_SEED_MODE",
            env_defaults,
            "manual",
        ),
        "MR_RUNTIME_MODEL_API_BASE": resolve_env_value("MR_RUNTIME_MODEL_API_BASE", env_defaults, ""),
        "MR_RUNTIME_MODEL_API_KEY": resolve_env_value("MR_RUNTIME_MODEL_API_KEY", env_defaults, ""),
        "MR_RUNTIME_MODEL_NAME": resolve_env_value("MR_RUNTIME_MODEL_NAME", env_defaults, ""),
        "OPENAI_API_KEY": resolve_env_value("OPENAI_API_KEY", env_defaults, ""),
    }
    summary = ", ".join(
        format_resolved_value(resolved[name])
        for name in (
            "WEB_PORT",
            "HERMES_PORT",
            "MR_RUNTIME_PORT",
            "GP_RUNTIME_PORT",
            "MR_RUNTIME_MODEL_MODE",
            "MR_RUNTIME_DEMO_SEED_MODE",
            "MR_RUNTIME_MODEL_API_KEY",
            "OPENAI_API_KEY",
        )
    )
    results.append(pass_result("env.effective", summary))
    return results, resolved


def check_provider_config(resolved: dict[str, ResolvedValue]) -> CheckResult:
    model_mode = resolved["MR_RUNTIME_MODEL_MODE"].value.strip().lower()
    if model_mode != "openai_compat":
        return pass_result(
            "env.provider",
            f"MR_RUNTIME_MODEL_MODE={model_mode or '<empty>'}; provider credentials are optional.",
        )

    required_keys = (
        "MR_RUNTIME_MODEL_API_BASE",
        "MR_RUNTIME_MODEL_API_KEY",
        "MR_RUNTIME_MODEL_NAME",
    )
    missing = [name for name in required_keys if not resolved[name].value.strip()]
    if missing:
        return fail_result(
            "env.provider",
            "openai_compat mode requires "
            + ", ".join(f"{name} ({resolved[name].source})" for name in missing),
            fix="Set the missing provider variables in `.env` or your shell before starting the runtime.",
        )

    summary = ", ".join(format_resolved_value(resolved[name]) for name in required_keys)
    return pass_result("env.provider", summary)


def validate_domain_assets(repo_root: Path, python_bin: str) -> CheckResult:
    loader_path = repo_root / "apps" / "mr-visit-jp-runtime" / "src" / "scenarios" / "asset_loader.py"
    script = """
import importlib.util
import json
import pathlib
import sys

loader_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("cosi_asset_loader", loader_path)
module = importlib.util.module_from_spec(spec)
try:
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    bundle = module.load_domain_bundle()
    print(json.dumps({
        "status": "ok",
        "domain_id": bundle.manifest.get("id"),
        "scenario_count": len(bundle.scenarios),
        "subskill_count": len(bundle.manifest.get("subskills", [])),
    }))
except Exception as exc:
    print(json.dumps({
        "status": "error",
        "error_type": type(exc).__name__,
        "message": str(exc),
    }))
    raise SystemExit(1)
"""
    result = subprocess.run(
        [python_bin, "-", str(loader_path)],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    payload_text = normalize_whitespace(result.stdout or result.stderr)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload = {
            "status": "error",
            "error_type": "UnknownError",
            "message": payload_text,
        }

    if result.returncode == 0 and payload.get("status") == "ok":
        return pass_result(
            "assets.domain",
            "domain_id={domain_id} scenarios={scenario_count} subskills={subskill_count}".format(
                **payload,
            ),
        )

    error_type = str(payload.get("error_type", "UnknownError"))
    message = str(payload.get("message", payload_text))
    if error_type in {"ModuleNotFoundError", "ImportError"}:
        fix = "Run `make bootstrap` so `.venv` has the runtime asset-validation dependencies."
    else:
        fix = (
            "Inspect domain assets under `domains/mr_visit_jp/` and "
            "`packages/shared-schemas/schemas/`, then rerun `make validate-content`."
        )
    return fail_result(
        "assets.domain",
        f"{error_type}: {message}",
        fix=fix,
    )


def validate_prompt_assets(repo_root: Path, python_bin: str) -> CheckResult:
    manager_path = (
        repo_root
        / "apps"
        / "mr-visit-jp-runtime"
        / "src"
        / "providers"
        / "prompt_assets.py"
    )
    script = """
import importlib.util
import json
import pathlib
import sys

manager_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("cosi_prompt_assets", manager_path)
module = importlib.util.module_from_spec(spec)
try:
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    bundle = module.load_prompt_asset_bundle()
    summary = bundle.describe()
    print(json.dumps({
        "status": "ok",
        "default_profile_id": summary.get("default_profile_id"),
        "profile_count": summary.get("profile_count"),
        "profiles": summary.get("profiles", {}),
    }))
except Exception as exc:
    print(json.dumps({
        "status": "error",
        "error_type": type(exc).__name__,
        "message": str(exc),
    }))
    raise SystemExit(1)
"""
    result = subprocess.run(
        [python_bin, "-", str(manager_path)],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    payload_text = normalize_whitespace(result.stdout or result.stderr)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload = {
            "status": "error",
            "error_type": "UnknownError",
            "message": payload_text,
        }

    if result.returncode == 0 and payload.get("status") == "ok":
        return pass_result(
            "assets.prompts",
            "default_profile={default_profile_id} profiles={profile_count}".format(**payload),
        )

    error_type = str(payload.get("error_type", "UnknownError"))
    message = str(payload.get("message", payload_text))
    if error_type in {"ModuleNotFoundError", "ImportError"}:
        fix = "Run `make bootstrap` so `.venv` has the runtime prompt-asset dependencies."
    else:
        fix = (
            "Inspect prompt assets under `domains/mr_visit_jp/prompts/`, then rerun "
            "`make validate-content`."
        )
    return fail_result(
        "assets.prompts",
        f"{error_type}: {message}",
        fix=fix,
    )


def validate_evaluation_gates(repo_root: Path, python_bin: str) -> CheckResult:
    runtime_src = repo_root / "apps" / "mr-visit-jp-runtime" / "src"
    script = """
import json
import pathlib
import sys

runtime_src = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(runtime_src))

class EmptySessionStore:
    def list_all(self, *args, **kwargs):
        return []

try:
    from providers import load_runtime_prompt_context
    from scenarios.asset_loader import load_domain_bundle
    from services.evaluation_gate_service import EvaluationGateService

    bundle = load_domain_bundle()
    requested_prompt_context = load_runtime_prompt_context()
    service = EvaluationGateService(
        domain_bundle=bundle,
        session_store=EmptySessionStore(),
        requested_prompt_context=requested_prompt_context,
        allow_blocked_rollout=False,
    )
    report = service.build_report()
    rollout = report.get("rollout", {})
    print(json.dumps({
        "status": "ok",
        "default_profile_id": report.get("default_profile_id"),
        "rollout_status": rollout.get("status"),
        "offline_gate_count": len(report.get("offline_gates", [])),
        "online_gate_count": len(report.get("online_gates", [])),
    }))
except Exception as exc:
    print(json.dumps({
        "status": "error",
        "error_type": type(exc).__name__,
        "message": str(exc),
    }))
    raise SystemExit(1)
"""
    result = subprocess.run(
        [python_bin, "-", str(runtime_src)],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    payload_text = normalize_whitespace(result.stdout or result.stderr)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload = {
            "status": "error",
            "error_type": "UnknownError",
            "message": payload_text,
        }

    if result.returncode == 0 and payload.get("status") == "ok":
        return pass_result(
            "assets.evaluation_gates",
            (
                "default_profile={default_profile_id} rollout={rollout_status} "
                "offline_gates={offline_gate_count} online_gates={online_gate_count}"
            ).format(**payload),
        )

    error_type = str(payload.get("error_type", "UnknownError"))
    message = str(payload.get("message", payload_text))
    if error_type in {"ModuleNotFoundError", "ImportError"}:
        fix = "Run `make bootstrap` so `.venv` has the runtime evaluation-gate dependencies."
    else:
        fix = (
            "Inspect `domains/mr_visit_jp/prompts/evaluation_gates.yaml`, prompt profiles, "
            "and transcript fixtures, then rerun `make validate-content`."
        )
    return fail_result(
        "assets.evaluation_gates",
        f"{error_type}: {message}",
        fix=fix,
    )


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def port_pids(port: int) -> list[str]:
    lsof_path = shutil.which("lsof")
    if lsof_path is not None:
        result = run_command([lsof_path, "-t", f"-iTCP:{port}", "-sTCP:LISTEN"])
        if result.returncode == 0:
            return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})

    ss_path = shutil.which("ss")
    if ss_path is not None:
        result = run_command([ss_path, "-ltnp", f"( sport = :{port} )"])
        if result.returncode == 0:
            matches = re.findall(r"pid=(\d+)", result.stdout)
            return sorted(set(matches))

    return []


def http_status(url: str, timeout: float) -> tuple[bool, str]:
    request = urllib.request.Request(url, headers={"accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return True, f"HTTP {response.getcode()} {normalize_whitespace(body)}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return False, f"HTTP {exc.code} {normalize_whitespace(body)}"
    except urllib.error.URLError as exc:
        return False, normalize_whitespace(str(exc.reason))


def inspect_service(
    *,
    service: ServiceDefinition,
    state_dir: Path,
    timeout: float,
) -> CheckResult:
    pid_file = state_dir / f"{service.name}.pid"
    log_file = state_dir / f"{service.name}.log"
    pid: int | None = None
    stale_pid = False

    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            return fail_result(
                f"service.{service.name}",
                f"Invalid PID file {pid_file}",
                fix=f"Remove {pid_file} or run `make stack-down`.",
            )

    if pid is not None and not pid_is_running(pid):
        stale_pid = True

    port_open = port_is_open(service.port)
    healthy, health_detail = http_status(service.health_url, timeout) if port_open else (False, "connection refused")
    port_pid_list = port_pids(service.port)
    log_hint = f"log={log_file}"

    if healthy and pid is not None and not stale_pid:
        return pass_result(
            f"service.{service.name}",
            f"healthy pid={pid} port={service.port} {log_hint}",
        )

    if healthy and (pid is None or stale_pid):
        detail = f"healthy on port={service.port} but PID file is missing or stale; listener_pid={','.join(port_pid_list) or 'unknown'} {log_hint}"
        return warn_result(
            f"service.{service.name}",
            detail,
            fix=f"Run `make stack-status` or set `STACK_STATE_DIR` correctly before using `make stack-down`.",
        )

    if stale_pid and not port_open:
        return warn_result(
            f"service.{service.name}",
            f"stale PID file {pid_file} pid={pid}; port {service.port} is closed.",
            fix=f"Run `make stack-down` to clean stale state, then restart with `make stack-up` if needed.",
        )

    if pid is None and not port_open:
        return warn_result(
            f"service.{service.name}",
            f"not running on port {service.port}; expected health URL {service.health_url}",
            fix=f"Start the local stack with `make stack-up`; inspect logs under {state_dir} after startup.",
        )

    if pid is not None and not stale_pid and not port_open:
        return fail_result(
            f"service.{service.name}",
            f"pid={pid} is running but port {service.port} is closed; {log_hint}",
            fix=f"Inspect {log_file} and restart the stack with `make stack-down && make stack-up`.",
        )

    listener_summary = ",".join(port_pid_list) or "unknown"
    return fail_result(
        f"service.{service.name}",
        f"port {service.port} is open but health check failed: {health_detail}; listener_pid={listener_summary} {log_hint}",
        fix=f"Inspect {log_file} and retry `make smoke-check` once the service reports healthy.",
    )


def service_definitions(
    web_port: int,
    hermes_port: int,
    runtime_port: int,
    gp_runtime_port: int,
) -> list[ServiceDefinition]:
    return [
        ServiceDefinition(
            name="runtime",
            port=runtime_port,
            health_url=f"http://127.0.0.1:{runtime_port}/healthz",
        ),
        ServiceDefinition(
            name="gp-runtime",
            port=gp_runtime_port,
            health_url=f"http://127.0.0.1:{gp_runtime_port}/healthz",
        ),
        ServiceDefinition(
            name="hermes",
            port=hermes_port,
            health_url=f"http://127.0.0.1:{hermes_port}/healthz",
        ),
        ServiceDefinition(
            name="web",
            port=web_port,
            health_url=f"http://127.0.0.1:{web_port}/api/runtime/scenarios",
        ),
    ]


def render_result(result: CheckResult) -> str:
    line = f"[doctor] {result.level:<4} {result.name} {result.detail}"
    if result.fix:
        return f"{line}\n[doctor]      fix: {result.fix}"
    return line


def collect_content_validation_results(repo_root: Path, python_bin: str) -> list[CheckResult]:
    return [
        validate_domain_assets(repo_root, python_bin),
        validate_prompt_assets(repo_root, python_bin),
        validate_evaluation_gates(repo_root, python_bin),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    env_defaults = parse_env_file(repo_root / ".env")
    results: list[CheckResult] = []
    python_bin = resolve_python_bin(repo_root)

    if args.content_only:
        results.extend(collect_content_validation_results(repo_root, python_bin))
        print(f"[doctor] repo_root={repo_root}")
        for result in results:
            print(render_result(result))

        pass_count = sum(result.level == "PASS" for result in results)
        warn_count = sum(result.level == "WARN" for result in results)
        fail_count = sum(result.level == "FAIL" for result in results)
        print(f"[doctor] summary pass={pass_count} warn={warn_count} fail={fail_count}")
        return 1 if fail_count else 0

    results.extend(check_python_toolchain(repo_root))
    results.extend(check_node_toolchain(repo_root))
    env_results, resolved = check_env_files(repo_root, env_defaults)
    results.extend(env_results)
    results.append(check_provider_config(resolved))
    results.extend(collect_content_validation_results(repo_root, python_bin))

    web_port, web_error = parse_port(resolved["WEB_PORT"], "WEB_PORT")
    hermes_port, hermes_error = parse_port(resolved["HERMES_PORT"], "HERMES_PORT")
    runtime_port, runtime_error = parse_port(resolved["MR_RUNTIME_PORT"], "MR_RUNTIME_PORT")
    gp_runtime_port, gp_runtime_error = parse_port(resolved["GP_RUNTIME_PORT"], "GP_RUNTIME_PORT")
    for error in (web_error, hermes_error, runtime_error, gp_runtime_error):
        if error is not None:
            results.append(error)

    state_dir = Path(
        resolve_env_value("STACK_STATE_DIR", env_defaults, str(repo_root / ".tmp" / "local-stack")).value
    )

    if None not in (web_port, hermes_port, runtime_port, gp_runtime_port):
        for service in service_definitions(web_port, hermes_port, runtime_port, gp_runtime_port):
            results.append(inspect_service(service=service, state_dir=state_dir, timeout=args.timeout))

    print(f"[doctor] repo_root={repo_root}")
    print(f"[doctor] state_dir={state_dir}")
    for result in results:
        print(render_result(result))

    pass_count = sum(result.level == "PASS" for result in results)
    warn_count = sum(result.level == "WARN" for result in results)
    fail_count = sum(result.level == "FAIL" for result in results)
    print(f"[doctor] summary pass={pass_count} warn={warn_count} fail={fail_count}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

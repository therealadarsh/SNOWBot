"""Sandbox boundary. Docker is constructed here and executed only when present.

The local subprocess fixture performs real git commands. It is not a network
namespace: it strips provider credentials and records ``network`` as
``unisolated-subprocess``. ``docker run --network none`` is the no-network
path and was not executed in the environment that added this package.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from research.errors import DockerUnavailable
from research.gitutil import scrub_env

# Documented Claude Code env (code.claude.com/docs/en/env-vars): the key stays
# on the host proxy; the sandbox only receives the base URL.
_CLAUDE_BASE_URL = "ANTHROPIC_BASE_URL"
_HARNESS_PROXY_URL = "SNOWBOT_MODEL_PROXY_URL"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


@dataclass(frozen=True, slots=True)
class HostProxy:
    """Model calls terminate on the host. The sandbox does not receive keys."""

    base_url: str

    def sandbox_env(self) -> dict[str, str]:
        return {_CLAUDE_BASE_URL: self.base_url, _HARNESS_PROXY_URL: self.base_url}


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_run_argv(
    *,
    image: str,
    workspace: Path,
    command: Sequence[str],
    proxy: HostProxy | None = None,
) -> list[str]:
    """Argv for a fresh container with no network.

    ``--network none`` is Docker's documented network mode. This function does
    not start the container.
    """
    argv = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-v",
        f"{workspace}:/work",
        "-w",
        "/work",
    ]
    if proxy is not None:
        for key, value in proxy.sandbox_env().items():
            argv.extend(["-e", f"{key}={value}"])
    argv.append(image)
    argv.extend(command)
    return argv


def inspect_compose_yaml(*, image: str) -> str:
    """Compose snippet using Inspect's documented ``network_mode: none``.

    Inspect's generated compose sets ``network_mode: none``. A custom file
    replaces that default, so the harness sets it explicitly. See
    https://inspect.aisi.org.uk/sandboxing.html
    """
    return (
        "services:\n"
        "  default:\n"
        f"    image: {image}\n"
        "    init: true\n"
        "    command: tail -f /dev/null\n"
        "    network_mode: none\n"
    )


class LocalSubprocessSandbox:
    """Credential-stripped subprocess in a workspace directory."""

    kind = "local-subprocess"
    network = "unisolated-subprocess"

    def __init__(self, workspace: Path, *, proxy: HostProxy | None = None) -> None:
        self.workspace = workspace
        self.proxy = proxy

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float,
        host_env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        env = scrub_env(host_env)
        if self.proxy is not None:
            env.update(self.proxy.sandbox_env())
        try:
            proc = subprocess.run(
                list(argv),
                cwd=self.workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return ProcessResult(
                argv=tuple(argv),
                returncode=124,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )
        return ProcessResult(
            argv=tuple(argv),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            timed_out=False,
        )


class DockerSandbox:
    """Docker backend. ``run`` does not start a study container in this build."""

    kind = "docker"
    network = "none"

    def __init__(
        self,
        workspace: Path,
        *,
        image: str,
        proxy: HostProxy | None = None,
        available: bool | None = None,
    ) -> None:
        self.workspace = workspace
        self.image = image
        self.proxy = proxy
        self._available = docker_available() if available is None else available

    def argv(self, command: Sequence[str]) -> list[str]:
        return docker_run_argv(
            image=self.image,
            workspace=self.workspace,
            command=command,
            proxy=self.proxy,
        )

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float,
        host_env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        del argv, timeout_s, host_env
        if not self._available:
            raise DockerUnavailable("docker is not available; refusing to start a container")
        raise DockerUnavailable("this build does not start study containers")

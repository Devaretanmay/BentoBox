"""Docker backend for HAVFRYS execution isolation."""

import inspect
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Callable, Optional, Tuple


# Internal mount path inside the container
_WORKSPACE = "/workspace"


class DockerBackend:
    def __init__(
        self,
        image: str,
        resource_args: list[str],
        network_args: list[str],
        timeout: int = 3600,
        workdir: str = "",
    ):
        self.image = image
        self.resource_args = resource_args
        self.network_args = network_args
        self.timeout = timeout
        self.workdir = workdir
        self._container: Optional[str] = None

    def start(self) -> str:
        if not shutil.which("docker"):
            raise RuntimeError("Docker is required for HAVFRYS but was not found.")
        pull = subprocess.run(
            ["docker", "pull", self.image],
            capture_output=True, text=True, timeout=120,
        )
        if pull.returncode != 0:
            raise RuntimeError(f"Failed to pull image {self.image}: {pull.stderr.strip()}")
        args = ["docker", "run", "-d", "--rm", "-e", "HAVFRYS_SESSION=1"]
        if self.workdir:
            args += ["-v", f"{self.workdir}:{_WORKSPACE}"]
            args += ["-w", _WORKSPACE]
        args += self.resource_args + self.network_args
        args += [self.image, "sleep", "infinity"]
        proc = subprocess.run(args, capture_output=True, text=True, check=True, timeout=120)
        self._container = proc.stdout.strip()
        return self._container

    def stop(self) -> None:
        if self._container:
            subprocess.run(["docker", "rm", "-f", self._container], capture_output=True)
            self._container = None

    def commit(self, repository: str, tag: str) -> None:
        if not self._container:
            return
        subprocess.run(["docker", "commit", self._container, f"{repository}:{tag}"], capture_output=True, check=True)

    def execute_cli(self, command: str, cwd: Optional[str], env: Optional[dict]) -> Tuple[int, str, str]:
        if not self._container:
            raise RuntimeError("Container not running")
        exec_args = ["docker", "exec"]
        if env:
            for k, v in env.items():
                exec_args += ["-e", f"{k}={v}"]
        # Use mounted workdir as the execution directory inside the container
        if cwd:
            exec_args += ["-w", cwd]
        elif self.workdir:
            exec_args += ["-w", _WORKSPACE]
        exec_args += [self._container, "sh", "-c", command]
        proc = subprocess.run(
            exec_args,
            capture_output=True, text=True, timeout=self.timeout
        )
        return proc.returncode, proc.stdout, proc.stderr

    def execute_callable(self, fn: Callable[[], Any]) -> Tuple[int, str, str]:
        if not self._container:
            raise RuntimeError("Container not running")
        mod = inspect.getmodule(fn)
        if mod is None:
            mod = sys.modules.get(getattr(fn, "__module__", ""))
        if mod is None or mod is inspect.getmodule(inspect):
            raise RuntimeError("Could not read module source.")
        try:
            module_source = inspect.getsource(mod)
        except OSError:
            raise RuntimeError("Could not read module source.")

        payload = {"source": module_source, "name": getattr(fn, "__name__", "target")}
        script = (
            "import json,sys\n"
            "p=json.loads(sys.stdin.read())\n"
            "ns={}\n"
            "exec(p['source'], ns)\n"
            "fn=ns.get(p['name'])\n"
            "fn() if callable(fn) else None\n"
        )
        exec_args = ["docker", "exec", "-i"]
        if self.workdir:
            exec_args += ["-w", _WORKSPACE]
        exec_args += [self._container, "python3", "-c", script]
        proc = subprocess.run(
            exec_args,
            input=json.dumps(payload), capture_output=True, text=True, timeout=self.timeout
        )
        return proc.returncode, proc.stdout, proc.stderr

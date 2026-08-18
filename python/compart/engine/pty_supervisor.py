"""PTY Supervisor — transparent terminal bridge for interactive agent execution.

Creates a PTY master/slave pair, applies the compartment policy in the child
process, then bridges stdin/stdout between the calling terminal and the child
PTY so that interactive agents (claude, codex, opencode) receive the full
native TUI experience: colors, alternate screen, Ctrl+C, Ctrl+D, resize
events, streaming output, and interactive confirmations.

The supervisor is intentionally invisible: the agent binary does not know
Compart is there.

Usage
-----
Interactive (full terminal hand-off)::

    sup = PtySupervisor(workdir=".", compartment_policy=policy)
    returncode = sup.attach(["claude"])

Non-interactive (output capture for workflows/scripts)::

    result = sup.capture(["pytest", "-q"])
    print(result.stdout)
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import pty
import select
import shutil
import signal
import struct
import sys
import termios
import tty
from dataclasses import dataclass, field
from typing import Optional, Sequence

try:
    from compart._core import sandbox_apply as _core_sandbox_apply
except ImportError:
    _core_sandbox_apply = None

_logger = logging.getLogger("compart.pty_supervisor")


@dataclass
class CaptureResult:
    """Outcome of a non-interactive (captured) execution."""
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.returncode == 0 and self.error is None


class PtySupervisor:
    """Transparent PTY supervisor that bridges a terminal to a sandboxed child.

    Parameters
    ----------
    workdir:
        Working directory for the child process.
    compartment_policy:
        Optional dict describing the compartment policy to apply in the child
        (e.g. ``{"permissions": ["fs_read", "fs_write"]}``.  When ``None``
        no additional policy is applied — the OS-level Landlock/Seatbelt
        profile from the Rust core is still applied when available.
    extra_env:
        Additional environment variables to pass to the child process.
    """

    def __init__(
        self,
        workdir: str = ".",
        compartment_policy: Optional[dict] = None,
        extra_env: Optional[dict] = None,
    ) -> None:
        self.workdir = os.path.abspath(workdir)
        self.compartment_policy = compartment_policy or {}
        self.extra_env = extra_env or {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def attach(self, argv: Sequence[str]) -> int:
        """Launch *argv* in a PTY and hand the calling terminal to it.

        The current process blocks until the child exits.  The child
        receives a full PTY so all TUI features work normally.

        Returns
        -------
        int
            Exit code of the child process.
        """
        if not argv:
            raise ValueError("argv must not be empty")
        binary = self._resolve(argv[0])
        child_env = self._build_env()

        master_fd, slave_fd = pty.openpty()
        winsize = self._get_winsize(sys.stdin.fileno()) if sys.stdin.isatty() else None

        pid = os.fork()
        if pid == 0:
            os.close(master_fd)
            os.setsid()
            try:
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            except Exception:
                pass
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            if winsize is not None:
                self._set_winsize(0, winsize)
            self._apply_policy_child()
            os.chdir(self.workdir)
            child_env["PWD"] = self.workdir
            os.execvpe(binary, list(argv), child_env)
            os._exit(127)

        os.close(slave_fd)

        old_attrs: Optional[list] = None
        if sys.stdin.isatty():
            old_attrs = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())

        def _handle_sigwinch(sig, frame):  # noqa: ARG001
            if sys.stdin.isatty():
                ws = self._get_winsize(sys.stdin.fileno())
                self._set_winsize(master_fd, ws)
        signal.signal(signal.SIGWINCH, _handle_sigwinch)

        try:
            returncode = self._bridge(master_fd, pid)
        finally:
            signal.signal(signal.SIGWINCH, signal.SIG_DFL)
            if old_attrs is not None:
                try:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
                except Exception:
                    pass
            os.close(master_fd)

        return returncode

    def capture(self, argv: Sequence[str], timeout_s: int = 300) -> CaptureResult:
        """Launch *argv* non-interactively and capture its output."""
        if not argv:
            raise ValueError("argv must not be empty")
        binary = self._resolve(argv[0])
        child_env = self._build_env()

        master_fd, slave_fd = pty.openpty()
        output_chunks: list[bytes] = []

        pid = os.fork()
        if pid == 0:
            os.close(master_fd)
            os.setsid()
            try:
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            except Exception:
                pass
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            self._apply_policy_child()
            os.chdir(self.workdir)
            child_env["PWD"] = self.workdir
            os.execvpe(binary, list(argv), child_env)
            os._exit(127)

        os.close(slave_fd)

        try:
            while True:
                try:
                    rlist, _, _ = select.select([master_fd], [], [], 1.0)
                except select.error:
                    break
                if rlist:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            output_chunks.append(data)
                        else:
                            break
                    except OSError as exc:
                        if exc.errno in (errno.EIO, errno.EBADF):
                            break
                        raise
                else:
                    result = os.waitpid(pid, os.WNOHANG)
                    if result[0] != 0:
                        break
        finally:
            os.close(master_fd)

        try:
            _, status = os.waitpid(pid, 0)
            returncode = os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            returncode = 0
        raw_output = b"".join(output_chunks).decode("utf-8", errors="replace")

        return CaptureResult(returncode=returncode, stdout=raw_output)

    def _resolve(self, name: str) -> str:
        """Resolve an agent name to its real absolute binary path."""
        if os.sep in name:
            return name
        shim_dir = os.path.abspath(os.path.join(self.workdir, ".compart", "bin"))
        clean_path = os.pathsep.join(
            p for p in os.environ.get("PATH", "").split(os.pathsep)
            if p and os.path.abspath(p) != shim_dir
        )
        real = shutil.which(name, path=clean_path)
        if real is None:
            raise FileNotFoundError(f"Could not find executable: {name!r}")
        return real

    def _build_env(self) -> dict:
        env = os.environ.copy()
        env.update(self.extra_env)
        return env

    def _apply_policy_child(self) -> None:
        """Apply the compartment policy inside the child process (pre-exec)."""
        if _core_sandbox_apply is not None:
            try:
                permissions = self.compartment_policy.get("permissions", [])
                _core_sandbox_apply(self.workdir, "network" not in permissions)
            except Exception as exc:
                _logger.warning("Could not apply sandbox policy in child: %s", exc)

    @staticmethod
    def _get_winsize(fd: int) -> bytes:
        try:
            return fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\x00" * 8)
        except Exception:
            return struct.pack("HHHH", 24, 80, 0, 0)

    @staticmethod
    def _set_winsize(fd: int, winsize: bytes) -> None:
        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    def _bridge(self, master_fd: int, child_pid: int) -> int:
        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()

        while True:
            try:
                rlist, _, _ = select.select([stdin_fd, master_fd], [], [], 0.05)
            except (select.error, ValueError):
                break

            if stdin_fd in rlist:
                try:
                    data = os.read(stdin_fd, 1024)
                    if data:
                        os.write(master_fd, data)
                except OSError:
                    break

            if master_fd in rlist:
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        os.write(stdout_fd, data)
                    else:
                        break
                except OSError as exc:
                    if exc.errno in (errno.EIO, errno.EBADF):
                        break
                    raise

            try:
                result_pid, status = os.waitpid(child_pid, os.WNOHANG)
                if result_pid == child_pid:
                    try:
                        while True:
                            r, _, _ = select.select([master_fd], [], [], 0.1)
                            if not r:
                                break
                            data = os.read(master_fd, 4096)
                            if data:
                                os.write(stdout_fd, data)
                            else:
                                break
                    except OSError:
                        pass
                    return os.waitstatus_to_exitcode(status)
            except ChildProcessError:
                break

        try:
            _, status = os.waitpid(child_pid, 0)
            return os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            return 0


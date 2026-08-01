"""BentoBox - kernel-level sandbox with an insulated runtime for isolated execution."""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .sandbox.box import Box
from .sandbox.lid import Lid, LidConfig
from .sandbox import compression as _compression_module  # noqa: F401
from .sandbox import credential_module as _credential_module  # noqa: F401
from .sandbox import snapshot_module as _snapshot_module  # noqa: F401
from .sandbox.proxy import RouteConfig
from .compartments import Compartment, CompartmentConfig, CompartmentRuntime
from .errors import LayerError
from .engine.events import emit, event_bus
from .engine.tracer import Tracer, set_tracer

_logger = logging.getLogger("bentoworks")


@dataclass
class BentoBoxConfig:
    workdir: str = "."
    profile: str = "default"
    credential_rules: list[RouteConfig] = field(default_factory=list)



@dataclass
class BentoBoxResult:
    status: str = "success"
    summary: str = ""
    elapsed_s: float = 0.0
    compartments_completed: list[str] = field(default_factory=list)
    output: dict[str, dict] = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    errors: list[LayerError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BentoBox:
    """A kernel-level sandbox with compartmentalized execution."""

    BENTOWORKS_DIR = ".bentoworks"

    def __init__(
        self,
        workdir: str = ".",
        config: Optional[BentoBoxConfig] = None,
        verbose: bool = False,
    ):
        if config is not None:
            self.config = config
        else:
            self.config = BentoBoxConfig(workdir=workdir)
        self.workdir = os.path.abspath(self.config.workdir)
        self._box = Box(workdir=self.workdir)
        self.box_id = self._box.box_id
        self.box_dir = self._box.box_dir
        self._snapshot_base = os.path.join(self.workdir, self.BENTOWORKS_DIR, "snapshots")
        self._lid = Lid(LidConfig(
            profile=self.config.profile,
            credential_rules=self.config.credential_rules,
            snapshot_base=self._snapshot_base,
        ))
        self._runtime = CompartmentRuntime()
        self._started_at: float = 0.0
        self._tracer: Optional[Tracer] = None
        self.verbose = verbose or os.environ.get("BENTOWORKS_TRACE", "0") in (
            "1", "true", "yes", "on",
        )

    def add(self, compartment: Compartment) -> "BentoBox":
        """Register a compartment.

        Compartments run in registration order unless an entry point is
        specified in :meth:`run`.
        """
        self._runtime.add(compartment)
        return self

    def edge(self, from_name: str, to_name: str) -> "BentoBox":
        """Define a message path between two compartments: ``from_name -> to_name``.

        Messages sent by ``from_name`` are routed to ``to_name``.
        """
        self._runtime.edge(from_name, to_name)
        return self

    def why(self, path: str) -> str:
        """Diagnose why a path or network call would be blocked by the sandbox."""
        return self._box.why(path)

    def run(
        self,
        entry: Optional[str] = None,
        request: str = "",
    ) -> BentoBoxResult:
        """Execute all registered compartments inside this BentoBox.

        The lifecycle is:

        1. **Box entered** - sandbox environment is created
        2. **Lid insulated** - behaviour modules load for the task
        3. **Compartments execute** - each runs with its own policy
        4. **Cleanup** - lid released, box destroyed

        Parameters
        ----------
        entry : str, optional
            Name of the compartment to start from. If omitted, all
            compartments run in registration order.
        request : str, optional
            Human-readable task description for logging and trace
            headers. Also used by the Lid to classify the task
            profile (e.g. "fix bug" -> debugging profile).

        Returns
        -------
        BentoBoxResult
        """
        task_desc = request or entry or "bentobox.run()"
        self._started_at = time.time()
        _logger.info("BentoBox %s running: %s", self.box_id, task_desc[:80])

        if self.verbose:
            self._tracer = Tracer(self.box_id, verbose=True)
            self._tracer.header(task_desc)
            set_tracer(self._tracer)
            self._wire_tracer_events()

        self._box.enter(block_network=False, sandbox=False)

        self._lid.insulate(self._box, task_desc)

        raw_results = self._runtime.run(
            entry=entry,
            box=self._box,
            lid=self._lid,
            workdir=self.workdir,
            box_dir=self.box_dir,
        )

        compressed = self._read_compressed_outputs()
        for name, compressed_val in compressed.items():
            if name in raw_results:
                if isinstance(raw_results[name], dict):
                    raw_results[name]["_compressed"] = compressed_val
                else:
                    raw_results[name] = {
                        "result": raw_results[name],
                        "_compressed": compressed_val,
                    }

        elapsed = round(time.time() - self._started_at, 2)

        try:
            self._lid.release()
        except Exception:
            pass
        try:
            self._box.exit()
        except Exception:
            pass

        if self._tracer:
            status = "error" if any(
                isinstance(v, dict) and "error" in v for v in raw_results.values()
            ) else "success"
            self._tracer.footer(status, elapsed)
            self._unwire_tracer_events()
            set_tracer(None)

        return self._build_result(raw_results, elapsed)

    def _wire_tracer_events(self) -> None:
        t = self._tracer
        if not t:
            return
        self._tracer_unsubscribe = []

        def handler(evt):
            t.emit(evt.name, **evt.data)

        for event_name in [
            "box.created", "box.entered", "box.destroyed",
            "lid.insulated", "lid.released",
            "task_profile",
            "compartment_start", "compartment_done", "compartment_failed",
        ]:
            event_bus.on(event_name, handler)
            self._tracer_unsubscribe.append((event_name, handler))

    def _unwire_tracer_events(self) -> None:
        if not hasattr(self, "_tracer_unsubscribe"):
            return
        for event_name, handler in self._tracer_unsubscribe:
            event_bus.remove(event_name, handler)
        self._tracer_unsubscribe.clear()

    def _read_compressed_outputs(self) -> dict[str, str]:
        """Read compressed outputs from the CompressionModule (if loaded)."""
        for engine in self._lid._engines.values():
            for module in engine.modules:
                if hasattr(module, "compressed_outputs"):
                    return module.compressed_outputs
        return {}

    def _build_result(self, raw: dict[str, Any], elapsed: float) -> BentoBoxResult:
        errors: list[LayerError] = []
        completed: list[str] = []
        status = "success"

        for name, result in raw.items():
            if isinstance(result, dict) and "error" in result:
                errors.append(LayerError(result["error"]))
                status = "error"
            else:
                completed.append(name)

        summary = "Task completed"
        if errors:
            summary = errors[-1].args[0] if errors else "Unknown error"

        return BentoBoxResult(
            status=status,
            summary=summary,
            elapsed_s=elapsed,
            compartments_completed=completed,
            output=dict(raw),
            state=dict(raw),
            errors=errors,
        )

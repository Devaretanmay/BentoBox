import logging
import os
from typing import Any, Optional

from .behaviour import BehaviourModule, register
from .snapshot import SnapshotManager

_logger = logging.getLogger("bentoworks.snapshot")


@register
class SnapshotModule(BehaviourModule):
    """Snapshots the workdir before each compartment runs."""

    name = "snapshot"
    engine = "preparation"

    def load(self, ctx) -> None:
        self._workdir = ctx.workdir
        snapshot_base = ctx.config.get("snapshot_base", "")
        box_id = ctx.box_id
        self._snapshot_dir = os.path.join(snapshot_base, box_id) if snapshot_base else ""
        self._manager: Optional[SnapshotManager] = None

    def on_event(self, event: str, **data) -> Any:
        if event == "compartment_start":
            return self._snapshot(data.get("name", "?"))

        if event == "compartment_failed":
            return self._rollback(data.get("name", "?"))

        if event == "compartment_done":
            return self._cleanup(data.get("name", "?"))

        return None

    def _snapshot(self, name: str) -> None:
        if not self._snapshot_dir:
            return
        self._manager = SnapshotManager(
            workdir=self._workdir,
            snapshot_dir=self._snapshot_dir,
        )
        count = self._manager.snapshot()
        if count > 0:
            _logger.info("Snapshot taken for '%s': %d files", name, count)

    def _rollback(self, name: str) -> None:
        if self._manager is None:
            return
        count = self._manager.restore()
        if count > 0:
            _logger.info("Rolled back '%s': %d files restored", name, count)
        self._manager.cleanup()
        self._manager = None

    def _cleanup(self, name: str) -> None:
        if self._manager is None:
            return
        self._manager.cleanup()
        self._manager = None

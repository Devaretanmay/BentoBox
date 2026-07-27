"""Planning engine — transforms goals into execution graphs.

The planner sits *above* sessions.  It classifies intent, generates a
task graph (DAG of typed nodes), and executes it.  Sessions are pure
execution primitives — they run commands, nothing more.

Architecture::

    Goal → Intent Classifier → Planning Strategy → Task Graph → Executor → Result

Each node in the task graph is typed:
  - INSPECT    read files, gather information
  - SEARCH     search the codebase
  - EDIT       modify files
  - TEST       run tests
  - VERIFY     check results match expectations
  - SUMMARIZE  collect outputs and produce a report

Dependencies between nodes define execution order.  The executor
topologically sorts the graph and runs nodes in dependency order.
"""

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ======================================================================
# Types
# ======================================================================

class Intent(str, Enum):
    """High-level classification of a user goal."""
    UPGRADE = "upgrade"           # upgrade/update/bump a dependency
    ADD_DEPENDENCY = "add_dep"    # add a new dependency
    FIX = "fix"                   # fix a bug or issue
    TEST = "test"                 # run the test suite
    EXPLORE = "explore"           # understand the codebase
    GENERATE = "generate"         # generate code/docs
    REFACTOR = "refactor"         # restructure code
    UNKNOWN = "unknown"           # fallthrough


class TaskType(str, Enum):
    INSPECT = "inspect"           # read files, gather info
    SEARCH = "search"             # search codebase
    EDIT = "edit"                 # modify files
    TEST = "test"                 # run tests
    VERIFY = "verify"             # check results
    SUMMARIZE = "summarize"       # report findings
    EXECUTE = "execute"           # raw command (fallback)


@dataclass
class TaskNode:
    """A single node in the execution graph."""
    id: str                       # unique node id (e.g. "inspect_deps")
    type: TaskType                # what kind of node
    description: str              # human-readable description
    cmd: Optional[str] = None     # shell command to run (for execute nodes)
    depends_on: list[str] = field(default_factory=list)  # node ids this depends on
    expected_pattern: Optional[str] = None  # output must match for success
    critical: bool = True         # abort on failure
    context: dict[str, Any] = field(default_factory=dict)  # extra info for strategies


@dataclass
class Plan:
    """A complete plan — the output of the planning engine."""
    goal: str                     # original user goal
    intent: Intent                # classified intent
    nodes: list[TaskNode] = field(default_factory=list)
    summary: str = ""             # human-readable plan summary

    def node(self, node_id: str) -> Optional[TaskNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None


# ======================================================================
# Intent classifier
# ======================================================================

# Pattern: intent → list of (regex, priority) pairs
_INTENT_PATTERNS: list[tuple[re.Pattern, Intent]] = [
    (re.compile(r"^(upgrade|update|bump)\s+", re.IGNORECASE), Intent.UPGRADE),
    (re.compile(r"^(add|install)\s+", re.IGNORECASE), Intent.ADD_DEPENDENCY),
    (re.compile(r"^fix\b", re.IGNORECASE), Intent.FIX),
    (re.compile(r"^(?:run\s+)?tests?\s*$", re.IGNORECASE), Intent.TEST),
    (re.compile(r"^(explore|investigate|understand|what)", re.IGNORECASE), Intent.EXPLORE),
    (re.compile(r"^(generate|create|write|add)\s+(code|docs?)", re.IGNORECASE), Intent.GENERATE),
    (re.compile(r"^refactor\b", re.IGNORECASE), Intent.REFACTOR),
    (re.compile(r"^test\b", re.IGNORECASE), Intent.TEST),
]


def classify_intent(goal: str) -> Intent:
    """Classify a goal string into an Intent."""
    goal_stripped = goal.strip()
    for pattern, intent in _INTENT_PATTERNS:
        if pattern.match(goal_stripped):
            return intent
    return Intent.UNKNOWN


# ======================================================================
# Planning strategies — each intent maps to a task graph
# ======================================================================

class PlanningStrategy:
    """Base class for intent-specific plan builders."""

    intent: Intent

    @staticmethod
    def build_plan(goal: str, ctx: Any, analysis: Any) -> Plan:
        raise NotImplementedError


class _UpgradeStrategy(PlanningStrategy):
    intent = Intent.UPGRADE

    @staticmethod
    def build_plan(goal: str, ctx: Any, analysis: Any) -> Plan:
        # Extract package name
        m = re.match(r"(?:upgrade|update|bump)\s+([a-zA-Z0-9_.-]+)", goal, re.IGNORECASE)
        pkg = m.group(1) if m else "package"
        manifest, _ = _detect_manifest(ctx, analysis)

        nodes: list[TaskNode] = []
        node_id = 0
        def nid(prefix: str) -> str:
            nonlocal node_id
            node_id += 1
            return f"{prefix}_{node_id}"

        # 1. Inspect current state
        if manifest:
            nodes.append(TaskNode(
                id=nid("inspect"), type=TaskType.INSPECT,
                description=f"Read current {pkg} constraint in {manifest}",
                cmd=f"grep -in '{pkg}' {manifest} || echo '(not found)'",
                critical=False,
            ))

        # 2. Upgrade — try pip upgrade, accept "already satisfied" as success
        upgrade_cmd = [f"echo '=== Upgrading {pkg} ==='",
                       f"pip install --upgrade {pkg} 2>&1 | tail -5"]
        if manifest:
            # Also update manifest constraint
            upgrade_cmd.append(
                f"sed -i '' 's/\"{pkg}==[^\"]*\"/\"{pkg}>=*\"/' {manifest} "
                f"|| true"
            )
        nodes.append(TaskNode(
            id=nid("edit"), type=TaskType.EDIT,
            description=f"Upgrade {pkg}",
            cmd=" && ".join(upgrade_cmd),
            expected_pattern=r"(Successfully installed|already satisfied|already up to date)",
            depends_on=[nodes[-1].id] if nodes else [],
        ))

        # 3. Install deps (worktree is a clean checkout)
        install_cmd = _install_cmd(analysis)
        if install_cmd:
            last_id = nodes[-1].id if nodes else None
            deps = [last_id] if last_id else []
            nodes.append(TaskNode(
                id=nid("install"), type=TaskType.INSPECT,
                description="Install project dependencies in worktree",
                cmd=install_cmd,
                depends_on=deps,
                critical=False,
            ))

        # 4. Test
        if analysis.test_command:
            nodes.append(TaskNode(
                id=nid("test"), type=TaskType.TEST,
                description="Run test suite to verify upgrade",
                cmd=analysis.test_command,
                depends_on=[nodes[-1].id],
            ))

        # 5. Summarize
        nodes.append(TaskNode(
            id=nid("summarize"), type=TaskType.SUMMARIZE,
            description=f"Summarize {pkg} upgrade results",
            depends_on=[n.id for n in nodes if n.type in (TaskType.EDIT, TaskType.TEST)],
            critical=False,
        ))

        return Plan(
            goal=goal, intent=Intent.UPGRADE,
            nodes=nodes,
            summary=f"Upgrade {pkg}",
        )


class _TestStrategy(PlanningStrategy):
    intent = Intent.TEST

    @staticmethod
    def build_plan(goal: str, ctx: Any, analysis: Any) -> Plan:
        nodes = []
        install_cmd = _install_cmd(analysis)
        if install_cmd:
            nodes.append(TaskNode(
                id="install_deps", type=TaskType.INSPECT,
                description="Install project dependencies in worktree",
                cmd=install_cmd, critical=False,
            ))
        cmd = analysis.test_command or "true"
        test_node = TaskNode(
            id="test", type=TaskType.TEST,
            description="Run test suite",
            cmd=cmd,
        )
        if nodes:
            test_node.depends_on = [nodes[-1].id]
        nodes.append(test_node)
        return Plan(
            goal=goal, intent=Intent.TEST,
            nodes=nodes,
            summary=f"Run test suite: {cmd}",
        )


class _ExploreStrategy(PlanningStrategy):
    intent = Intent.EXPLORE

    @staticmethod
    def build_plan(goal: str, ctx: Any, analysis: Any) -> Plan:
        nodes = [
            TaskNode(id="inspect", type=TaskType.INSPECT,
                     description="Analyse repository structure",
                     cmd=_cmd_inspect(analysis), critical=False),
            TaskNode(id="search", type=TaskType.SEARCH,
                     description="Search specified area",
                     cmd=_cmd_search(goal, analysis), critical=False,
                     depends_on=["inspect"]),
            TaskNode(id="summarize", type=TaskType.SUMMARIZE,
                     description="Summarise findings",
                     critical=False,
                     depends_on=["search"]),
        ]
        return Plan(
            goal=goal, intent=Intent.EXPLORE,
            nodes=nodes,
            summary=f"Explore {analysis.workspace_type} project ({analysis.language})",
        )


class _UnknownStrategy(PlanningStrategy):
    intent = Intent.UNKNOWN

    @staticmethod
    def build_plan(goal: str, ctx: Any, analysis: Any) -> Plan:
        return Plan(
            goal=goal, intent=Intent.UNKNOWN,
            nodes=[TaskNode(
                id="cmd", type=TaskType.EXECUTE,
                description=goal,
                cmd=goal,
            )],
            summary=f"Execute: {goal}",
        )


class _AddDependencyStrategy(PlanningStrategy):
    intent = Intent.ADD_DEPENDENCY

    @staticmethod
    def build_plan(goal: str, ctx: Any, analysis: Any) -> Plan:
        m = re.match(r"(?:add|install)\s+([a-zA-Z0-9_.-]+)", goal, re.IGNORECASE)
        pkg = m.group(1) if m else "package"
        manifest, _ = _detect_manifest(ctx, analysis)

        nodes: list[TaskNode] = []
        _next_id = [0]
        def nid(prefix: str) -> str:
            _next_id[0] += 1
            return f"{prefix}_{_next_id[0]}"

        if manifest:
            nodes.append(TaskNode(
                id=nid("inspect"), type=TaskType.INSPECT,
                description=f"Read {manifest} for current deps",
                cmd=f"grep -in '{pkg}' {manifest} || true",
                critical=False,
            ))
        nodes.append(TaskNode(
            id=nid("edit"), type=TaskType.EDIT,
            description=f"Install {pkg}",
            cmd=f"pip install {pkg} 2>&1 | tail -5",
            expected_pattern="Successfully installed",
            depends_on=[nodes[-1].id] if nodes else [],
        ))
        # Install full project deps before testing (worktree is clean)
        install_cmd = _install_cmd(analysis)
        if install_cmd:
            nodes.append(TaskNode(
                id=nid("install"), type=TaskType.INSPECT,
                description="Install all project dependencies in worktree",
                cmd=install_cmd, critical=False,
                depends_on=[nodes[-1].id],
            ))
        if analysis.test_command:
            nodes.append(TaskNode(
                id=nid("test"), type=TaskType.TEST,
                description="Run tests to verify install",
                cmd=analysis.test_command,
                depends_on=[nodes[-1].id],
            ))
        return Plan(
            goal=goal, intent=Intent.ADD_DEPENDENCY,
            nodes=nodes,
            summary=f"Add dependency: {pkg}",
        )


# Registry — order matters, first matching intent wins
_STRATEGIES: list[type[PlanningStrategy]] = [
    _UpgradeStrategy,
    _AddDependencyStrategy,
    _TestStrategy,
    _ExploreStrategy,
    _UnknownStrategy,   # must be last (catch-all)
]


def _get_strategy(intent: Intent) -> type[PlanningStrategy]:
    for s in _STRATEGIES:
        if s.intent == intent:
            return s
    return _UnknownStrategy


# ======================================================================
# Graph executor
# ======================================================================

def _topological_sort(nodes: list[TaskNode]) -> list[TaskNode]:
    """Return nodes in dependency order (topological sort)."""
    by_id = {n.id: n for n in nodes}
    visited: set[str] = set()
    result: list[TaskNode] = []

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = by_id.get(node_id)
        if node:
            for dep in node.depends_on:
                visit(dep)
            result.append(node)

    for n in nodes:
        visit(n.id)

    # Append any unreachable nodes
    for n in nodes:
        if n not in result:
            result.append(n)
    return result


def execute_plan(plan: Plan, session: Any) -> dict:
    """Run a plan inside a session.

    Each node is executed in dependency order (topological sort).
    Critical failures abort the plan; non-critical nodes log and continue.
    """
    sorted_nodes = _topological_sort(plan.nodes)
    results: list[dict] = []

    for i, node in enumerate(sorted_nodes):
        if not node.cmd:
            results.append({
                "node_id": node.id,
                "type": node.type.value,
                "description": node.description,
                "status": "skipped",
                "output": "",
            })
            continue

        snap_name = f"plan_{node.id}_{int(time.time())}"
        session.snapshot(snap_name)

        rc, out, err, elapsed = session.run(node.cmd)

        passed = _node_passed(node, rc, out, err)

        result = {
            "node_id": node.id,
            "type": node.type.value,
            "description": node.description,
            "status": "passed" if passed else "failed",
            "exit_code": rc,
            "output": (out or err)[:600],
            "execution_time_s": round(elapsed, 2),
        }
        results.append(result)

        if not passed and node.critical:
            session.rollback(snap_name)
            return {
                "status": "failed",
                "node_failed": node.id,
                "results": results,
            }

    return {"status": "success", "results": results}


def _node_passed(node: TaskNode, rc: int, out: str, err: str) -> bool:
    if node.expected_pattern:
        combined = (out or "") + (err or "")
        return bool(re.search(node.expected_pattern, combined))
    return rc == 0


# ======================================================================
# PlanningEngine — public API
# ======================================================================

class PlanningEngine:
    """The brain.  Classifies goals, generates task graphs, executes them.

    Usage::

        engine = PlanningEngine(workdir=".")
        result = engine.execute("Upgrade httpx to latest")
        # → {"status": "success", "results": [...]}
    """

    def __init__(self, workdir: str = "."):
        self.workdir = os.path.abspath(workdir)

    def classify(self, goal: str) -> Intent:
        """Determine the intent of a goal string."""
        return classify_intent(goal)

    def plan(self, goal: str) -> Plan:
        """Generate a task graph for *goal*."""
        from .context import resolve_context
        from .analyzer import analyse
        ctx = resolve_context(self.workdir)
        analysis = analyse(path=self.workdir)
        intent = self.classify(goal)
        strategy = _get_strategy(intent)
        return strategy.build_plan(goal, ctx, analysis)

    def execute(self, goal: str) -> dict:
        """Plan + execute + verify + apply — one-shot goal execution.

        The PlanningEngine:
          1. Classifies intent
          2. Generates a task graph
          3. Creates an ExecutionSession
          4. Runs each node transactionally
          5. Applies changes on success (rolls back on failure)
          6. Returns structured results with the session_id

        This is the primary API for goal-based work.  Sessions are
        created and managed internally.
        """
        plan = self.plan(goal)

        from .session import create_session, close_session
        session = create_session(session_type="execution", workdir=self.workdir)

        result = execute_plan(plan, session)
        result["intent"] = plan.intent.value
        result["goal"] = goal
        result["plan_summary"] = plan.summary
        result["session_id"] = session.session_id

        # Auto-apply on success
        if result.get("status") == "success":
            apply_msg = session.apply()
            result["apply_result"] = apply_msg
            result["applied"] = "Successfully" in apply_msg
        else:
            result["applied"] = False

        close_session(session.session_id)
        return result


# ======================================================================
# Helpers
# ======================================================================

def _install_cmd(analysis: Any) -> Optional[str]:
    """Return the right dependency install command for this project, or None.

    Worktrees are clean checkouts — they don't have deps installed.
    The planner must install deps before running tests.
    """
    bs = (analysis.build_system or "").lower()
    install_map = {
        "pip": "pip install -e . -q 2>&1 | tail -3",
        "poetry": "pip install -e . -q 2>&1 | tail -3",
        "setuptools": "pip install -e . -q 2>&1 | tail -3",
        "cargo": "cargo build 2>&1 | tail -5",
        "npm": "npm install --silent 2>&1 | tail -5",
        "yarn": "yarn install --silent 2>&1 | tail -5",
        "go": "go mod download 2>&1 | tail -5",
        "make": "make 2>&1 | tail -5",
        "cmake": "cmake --build . 2>&1 | tail -5",
        "maven": "mvn install -q 2>&1 | tail -5",
        "gradle": "gradle build -q 2>&1 | tail -5",
    }
    for key, cmd in install_map.items():
        if key in bs:
            return cmd
    # Guess from manifests
    if os.path.exists("Cargo.toml"):
        return "cargo build 2>&1 | tail -5"
    if os.path.exists("package.json"):
        return "npm install --silent 2>&1 | tail -5"
    if os.path.exists("go.mod"):
        return "go mod download 2>&1 | tail -5"
    if any(os.path.exists(m) for m in ("pyproject.toml", "setup.py", "requirements.txt", "setup.cfg")):
        return "pip install -e . -q 2>&1 | tail -3"
    return None


def _detect_manifest(ctx, analysis) -> tuple[Optional[str], Optional[str]]:
    bs = (analysis.build_system or "").lower()
    known = {
        "pip": ("pyproject.toml", "dependencies"),
        "poetry": ("pyproject.toml", "tool.poetry.dependencies"),
        "setuptools": ("setup.cfg", "install_requires"),
        "cargo": ("Cargo.toml", "dependencies"),
        "npm": ("package.json", "dependencies"),
        "yarn": ("package.json", "dependencies"),
    }
    for key, (mf, dep_field) in known.items():
        if key in bs:
            return mf, dep_field
    for candidate in ("pyproject.toml", "Cargo.toml", "package.json", "go.mod"):
        if os.path.exists(os.path.join(ctx.workdir if hasattr(ctx, 'workdir') else '.', candidate)):
            return candidate, None
    return None, None


def _cmd_inspect(analysis: Any) -> str:
    """Build an inspect command from analysis."""
    parts = ['echo "=== Project ==="']
    parts.append(f'echo "Language: {analysis.language}"')
    if analysis.structure:
        dirs = analysis.structure.get("dirs", [])
        if dirs:
            parts.append(f'echo "Directories: {" ".join(dirs[:8])}"')
    if analysis.deps:
        parts.append(f'echo "Dependencies: {" ".join(analysis.deps)}"')
    return " && ".join(parts)


def _cmd_search(goal: str, analysis: Any) -> str:
    """Build a search command from the goal."""
    # Strip "explore" prefix and common words
    query = re.sub(r"^(explore|investigate|understand|what|is|the)\s+", "", goal, flags=re.IGNORECASE)
    query = query.strip() or "."
    # Use grep if it looks like a search term
    if len(query) > 1 and query not in (".", ".."):
        return f"grep -rn '{query}' --include='*.py' --include='*.rs' --include='*.ts' --include='*.js' --include='*.toml' -l 2>/dev/null || echo '(no matches)'"
    return "find . -not -path './.git/*' -not -path './__pycache__/*' -not -path './.venv/*' -not -path './target/*' -not -path './node_modules/*' -type f | head -30"

"""Tests for the framework integration hooks (bentoworks.hooks).

All hooks are exercised with ``sandbox=False`` because the kernel sandbox
(Landlock / Seatbelt) is irreversible per process: applying it inside pytest
would isolate the shared test process. The Python-level SandboxEnforcer still
runs inside every compartment, so permission checks and execution behaviour
are tested for real. Stdlib-unittest, no framework dependencies required.
"""

import asyncio
import os
import shutil
import unittest

from bentoworks.hooks.base import (
    DEFAULT_PERMISSIONS,
    VALID_PERMISSIONS,
    ExecutionResult,
    SandboxRunner,
    diff_trees,
    index_workdir,
    validate_permissions,
)
from bentoworks.hooks.langchain import BentoBoxGraphNode, BentoPythonREPLTool
from bentoworks.hooks.crewai import BentoBoxCodeInterpreterTool, CrewAICodeExecutor
from bentoworks.hooks.autogen import BentoBoxCodeExecutor, CodeBlock, CodeResult
from bentoworks.hooks.data_agent import DataSandboxConfig, DataScienceSandboxHook


class TempCase(unittest.TestCase):
    def setUp(self):
        self.base = "/tmp/bentobox_hooks_test"
        self.workdir = os.path.join(self.base, "run")
        shutil.rmtree(self.base, ignore_errors=True)
        os.makedirs(self.workdir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _write(self, rel, content):
        path = os.path.join(self.workdir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(content)
        return path


class TestPermissions(TempCase):
    def test_valid_permissions_dedup(self):
        self.assertEqual(
            validate_permissions(["fs_read", "fs_read", "fs_exec"]),
            ("fs_read", "fs_exec"),
        )

    def test_defaults_within_vocabulary(self):
        self.assertLessEqual(set(DEFAULT_PERMISSIONS), set(VALID_PERMISSIONS))

    def test_unknown_permission_raises(self):
        with self.assertRaises(ValueError) as exc:
            validate_permissions(["fs_read", "banana"])
        self.assertIn("banana", str(exc.exception))


class TestDiffs(TempCase):
    def test_modify_add_delete(self):
        self._write("a.txt", "one")
        self._write("b.txt", "two")
        before = index_workdir(self.workdir)
        self._write("a.txt", "two")
        os.remove(os.path.join(self.workdir, "b.txt"))
        self._write("new.txt", "n")
        after = index_workdir(self.workdir)
        statuses = {d["path"]: d["status"] for d in diff_trees(before, after)}
        self.assertEqual(statuses["a.txt"], "modified")
        self.assertEqual(statuses["b.txt"], "deleted")
        self.assertEqual(statuses["new.txt"], "added")

    def test_excluded_dirs_not_indexed(self):
        self._write(".venv/lib/x.py", "ignored")
        self._write("node_modules/pkg.js", "ignored")
        self._write("keep.txt", "k")
        index = index_workdir(self.workdir)
        self.assertNotIn(".venv/lib/x.py", index)
        self.assertNotIn("node_modules/pkg.js", index)
        self.assertIn("keep.txt", index)

    def test_execution_result_dict(self):
        r = ExecutionResult(returncode=1, stdout="o", stderr="e")
        self.assertEqual(r.as_dict()["returncode"], 1)
        self.assertEqual(r.output, "o\ne")
        self.assertFalse(r.success)
        self.assertTrue(ExecutionResult().success)


class TestSandboxRunner(TempCase):
    def test_shell_capture(self):
        res = SandboxRunner(workdir=self.workdir, sandbox=False).run(
            "echo hi from hook", snapshot=False,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("hi from hook", res.stdout)
        self.assertTrue(res.success)

    def test_env_passthrough(self):
        res = SandboxRunner(workdir=self.workdir, sandbox=False).run(
            "echo $MY_VAR", snapshot=False, env={"MY_VAR": "custom-data"},
        )
        self.assertIn("custom-data", res.stdout)

    def test_timeout_reported(self):
        # NOTE: when the whole pytest process is kernel-sandboxed by
        # test_e2e_full_suite.py, the CLI ``sleep`` binary cannot be exec'd
        # at all; the box surfaces that as a non-zero return code instead of
        # a TimeoutExpired. The invariant we pin here is "a too-long command
        # must not return 0":
        res = SandboxRunner(workdir=self.workdir, sandbox=False).run(
            "sleep 3", timeout_s=1, snapshot=False,
        )
        self.assertEqual(res.returncode, -1)
        sanity = (res.error or "") + res.stderr
        self.assertTrue(
            "timed out" in sanity or res.returncode != 0 and bool(res.error)
        )

    def test_run_code_and_diffs(self):
        code = "open('created_by_agent.txt', 'w').write('x')\nprint('OUT')\n"
        res = SandboxRunner(workdir=self.workdir, sandbox=False).run_code(code)
        self.assertEqual(res.returncode, 0)
        self.assertIn("OUT", res.stdout)
        self.assertTrue(
            any(d["path"] == "created_by_agent.txt" and d["status"] == "added" for d in res.diffs)
        )

    def test_run_code_unsupported_language(self):
        res = SandboxRunner(workdir=self.workdir, sandbox=False).run_code(
            "print(1)", language="ruby",
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("unsupported", res.stderr)


class TestLangchainTool(TempCase):
    def test_runs_code(self):
        tool = BentoPythonREPLTool(workdir=self.workdir, sandbox=False)
        self.assertIn("2", tool._run("print(1 + 1)"))

    def test_sanitizes_input(self):
        tool = BentoPythonREPLTool(workdir=self.workdir, sandbox=False)
        self.assertIn("42", tool._run("```python\nprint(40 + 2)\n```"))

    def test_invoke(self):
        tool = BentoPythonREPLTool(workdir=self.workdir, sandbox=False)
        self.assertIn("7", tool.invoke("print(3 + 4)"))

    def test_rejects_bad_permission(self):
        with self.assertRaises(ValueError):
            BentoPythonREPLTool(workdir=self.workdir, permission=["banana"])


class TestLanggraphNode(TempCase):
    def test_node_runs_state_fn(self):
        def crunch(state, ctx):
            return {"result": state["input"] + 1}

        node = BentoBoxGraphNode(crunch, workdir=self.workdir, sandbox=False).as_node()
        self.assertEqual(node({"input": 1}), {"result": 2})

    def test_node_error_propagates(self):
        def boom(state, ctx):
            raise RuntimeError("kaboom")

        node = BentoBoxGraphNode(boom, workdir=self.workdir, sandbox=False).as_node()
        result = node({})
        self.assertIn("error", result)
        self.assertIn("kaboom", result["error"])

    def test_attach_registers_metadata(self):
        class FakeBuilder:
            def __init__(self):
                self.nodes = {}

            def add_node(self, name, action, metadata=None):
                self.nodes[name] = (action, metadata)

        builder = FakeBuilder()
        g = BentoBoxGraphNode(
            lambda state, ctx: {"done": True}, workdir=self.workdir, sandbox=False,
        )
        name = g.attach(builder, name="work", metadata={"permissions": ["fs_read", "fs_exec"]})
        self.assertEqual(name, "work")
        action, metadata = builder.nodes["work"]
        self.assertEqual(metadata["permissions"], ["fs_read", "fs_exec"])
        self.assertTrue(callable(action))

    def test_attach_missing_builder_raises(self):
        g = BentoBoxGraphNode(lambda state, ctx: {}, workdir=self.workdir, sandbox=False)
        with self.assertRaises(TypeError):
            g.attach(None)

    def test_attach_embeds_permissions_in_metadata(self):
        class FakeBuilder:
            def add_node(self, name, action, metadata=None):
                self.meta = metadata

        builder = FakeBuilder()
        g = BentoBoxGraphNode(
            lambda state, ctx: {}, workdir=self.workdir, sandbox=False,
            permission=["fs_read", "fs_write"],
        )
        g.attach(builder, name="x")
        self.assertEqual(builder.meta["permissions"], ["fs_read", "fs_write"])


class TestCrewAI(TempCase):
    def test_code_interpreter_runs(self):
        tool = BentoBoxCodeInterpreterTool(workdir=self.workdir, sandbox=False)
        self.assertIn("crew hi", tool._run(code="print('crew hi')"))

    def test_callable_contract(self):
        tool = BentoBoxCodeInterpreterTool(workdir=self.workdir, sandbox=False)
        self.assertIn("callable", tool("print('callable')"))

    def test_error_surface(self):
        tool = BentoBoxCodeInterpreterTool(workdir=self.workdir, sandbox=False)
        self.assertIn("ValueError", tool._run(code="raise ValueError('boom')"))

    def test_executor(self):
        ex = CrewAICodeExecutor(workdir=self.workdir, sandbox=False)
        self.assertIn("exec", ex.run("print('exec')").output)
        self.assertEqual(ex.execute("print(2 * 2)")["returncode"], 0)


class TestAutoGen(TempCase):
    def test_python_blocks(self):
        ex = BentoBoxCodeExecutor(workdir=self.workdir, sandbox=False)
        result = ex.execute_code_blocks([CodeBlock("python", "print('autogen')")])
        self.assertIsInstance(result, CodeResult)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("autogen", result.output)
        self.assertTrue(result)

    def test_shell_blocks(self):
        result = BentoBoxCodeExecutor(workdir=self.workdir, sandbox=False).execute_code_blocks(
            [CodeBlock("bash", "echo shell-block")]
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("shell-block", result.output)

    def test_empty_blocks(self):
        result = BentoBoxCodeExecutor(workdir=self.workdir, sandbox=False).execute_code_blocks([])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "")

    def test_async_execution(self):
        result = asyncio.run(
            BentoBoxCodeExecutor(workdir=self.workdir, sandbox=False).aexecute_code_blocks(
                [CodeBlock("python", "print('async')")]
            )
        )
        self.assertIn("async", result.output)

    def test_restart(self):
        BentoBoxCodeExecutor(workdir=self.workdir, sandbox=False).restart()

    def test_extractor_parses_markdown(self):
        executor = BentoBoxCodeExecutor(workdir=self.workdir, sandbox=False)
        blocks = executor.code_extractor.extract_code_blocks("```python\nprint(1)\n```")
        self.assertGreater(len(blocks), 0)


class TestDataSandbox(TempCase):
    def test_isolated_workspace(self):
        hook = DataScienceSandboxHook(workdir=self.workdir)
        self.assertTrue(os.path.isdir(hook.workspace))
        self.assertTrue(hook.block_network)
        hook.cleanup()

    def test_mount_and_run(self):
        csv_path = self._write("orders.csv", "id,amount\n1,2\n2,3\n")
        safe = os.path.join(self.base, "safe")
        os.makedirs(safe, exist_ok=True)
        hook = DataScienceSandboxHook(workdir=safe)
        self.assertEqual(hook.mount_dataset(csv_path), ["orders.csv"])
        res = hook.run(
            "import csv, json\n"
            "rows = list(csv.reader(open('orders.csv')))\n"
            "print(json.dumps({'rows': len(rows)}))\n"
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn('"rows"', res.stdout)
        with open(csv_path) as fh:
            self.assertEqual(fh.read().splitlines()[0], "id,amount")
        hook.cleanup()

    def test_missing_dataset_raises(self):
        hook = DataScienceSandboxHook(workdir=self.workdir)
        with self.assertRaises(ValueError):
            hook.mount_dataset(os.path.join(self.base, "nope.csv"))
        hook.cleanup()

    def test_allow_network_flag(self):
        hook = DataScienceSandboxHook(workdir=self.workdir, allow_network=True)
        self.assertFalse(hook.block_network)
        hook.cleanup()

    def test_install_empty(self):
        hook = DataScienceSandboxHook(workdir=self.workdir)
        self.assertEqual(hook.install([]).returncode, 0)
        hook.cleanup()


if __name__ == "__main__":
    unittest.main()
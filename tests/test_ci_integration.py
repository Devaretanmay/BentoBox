"""Unit tests for Compart CI Integration."""

import os
import unittest
from compart.ci.runner import CompartCIRunner, run_ci_step


class TestCIIntegration(unittest.TestCase):

    def test_ci_runner_executes_simple_command(self):
        runner = CompartCIRunner(workdir=".", block_network=True, sandbox=False)
        res = runner.run_step("echo 'Hello CI Compart'")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["returncode"], 0)
        self.assertIn("Hello CI Compart", res["stdout"])

    def test_ci_runner_captures_failure_exit_code(self):
        runner = CompartCIRunner(workdir=".", block_network=True, sandbox=False)
        res = runner.run_step("exit 42")
        self.assertEqual(res["returncode"], 42)

    def test_ci_runner_helper_function(self):
        code = run_ci_step("echo 'Testing helper'", block_network=True, sandbox=False)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

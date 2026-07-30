"""E2E tests for the compartment-centric BentoBox API.

Compartments are now user-defined execution units with their own
permissions and function bodies. No more fixed Intent/Plan/Execute/Verify.
"""

import os
import shutil
import subprocess
import unittest
import uuid

from bentoworks.bentobox import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig


def _make_repo(path: str):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@bentoworks.test"],
                   cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "BentoBox Test"],
                   cwd=path, capture_output=True)
    readme = os.path.join(path, "README.md")
    with open(readme, "w") as f:
        f.write("# Test Repo\n")
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path,
                   capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "Test",
                        "GIT_AUTHOR_EMAIL": "test@test.com",
                        "GIT_COMMITTER_NAME": "Test",
                        "GIT_COMMITTER_EMAIL": "test@test.com"})


def _result_comp(name: str, data: dict):
    """Create a compartment that returns a fixed dict."""
    return Compartment(
        name=name,
        fn=lambda ctx: data,
        config=CompartmentConfig(permissions=["fs_read"]),
    )


class TestBentoBoxInit(unittest.TestCase):

    def setUp(self):
        self.tmpdir = f"/tmp/bentobox_e2e_{uuid.uuid4().hex[:8]}"
        _make_repo(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_structure(self):
        box = BentoBox(workdir=self.tmpdir)
        self.assertTrue(box.box_id.startswith("box_"))
        self.assertTrue(hasattr(box, "_lid"))

    def test_two_boxes_independent(self):
        a = BentoBox(workdir=self.tmpdir)
        b = BentoBox(workdir=self.tmpdir)
        self.assertNotEqual(a.box_id, b.box_id)
        self.assertNotEqual(a.box_dir, b.box_dir)


class TestCompartmentFlow(unittest.TestCase):

    def setUp(self):
        self.tmpdir = f"/tmp/bentobox_flow_{uuid.uuid4().hex[:8]}"
        _make_repo(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_single_compartment_success(self):
        box = BentoBox(workdir=self.tmpdir)
        box.add(_result_comp("hello", {"greeting": "Hello, World!"}))
        result = box.run()
        self.assertEqual(result.status, "success")
        self.assertEqual(result.compartments_completed, ["hello"])
        self.assertEqual(result.output.get("hello", {}).get("greeting"), "Hello, World!")

    def test_multi_compartment_chain(self):
        box = BentoBox(workdir=self.tmpdir)
        box.add(_result_comp("first", {"step": 1}))
        box.add(_result_comp("second", {"step": 2}))
        box.add(_result_comp("third", {"step": 3}))
        box.edge("first", "second").edge("second", "third")
        result = box.run()
        self.assertEqual(result.status, "success")
        self.assertEqual(result.compartments_completed, ["first", "second", "third"])

    def test_compartment_policy_applied(self):
        """Each compartment's policy should be pushed to the Box before execution."""
        box = BentoBox(workdir=self.tmpdir)
        box.add(Compartment(
            name="network_job",
            fn=lambda ctx: {"permissions": ctx.config.permissions},
            config=CompartmentConfig(permissions=["network", "fs_read"], timeout_s=60),
        ))
        result = box.run()
        self.assertEqual(result.status, "success")
        self.assertEqual(
            result.output.get("network_job", {}).get("permissions"),
            ["network", "fs_read"],
        )

    def test_message_passing_between_compartments(self):
        """Compartments should be able to communicate via send/receive."""
        def sender(ctx):
            # Use ctx.send to route a message to the next compartment
            ctx.send("receiver", {"payload": "hello from sender"})
            return {"sent": True}

        def receiver(ctx):
            msgs = ctx.messages
            return {"received": len(msgs), "payload": msgs[0].data if msgs else None}

        box = BentoBox(workdir=self.tmpdir)
        box.add(Compartment(name="sender", fn=sender,
                            config=CompartmentConfig(permissions=["fs_read"])))
        box.add(Compartment(name="receiver", fn=receiver,
                            config=CompartmentConfig(permissions=["fs_read"])))
        box.edge("sender", "receiver")
        result = box.run()
        self.assertEqual(result.status, "success")
        self.assertTrue(result.output.get("sender", {}).get("sent"))
        self.assertEqual(result.output.get("receiver", {}).get("received"), 1)
        self.assertEqual(
            result.output.get("receiver", {}).get("payload", {}).get("payload"),
            "hello from sender",
        )

    def test_compartment_failure_does_not_crash_runtime(self):
        def failing(ctx):
            raise ValueError("Intentional failure")

        box = BentoBox(workdir=self.tmpdir)
        box.add(Compartment(name="good", fn=lambda ctx: {"ok": True},
                            config=CompartmentConfig(permissions=["fs_read"])))
        box.add(Compartment(name="bad", fn=failing,
                            config=CompartmentConfig(permissions=["fs_read"])))
        result = box.run()
        self.assertEqual(result.status, "error")  # at least one failed
        self.assertIn("good", result.compartments_completed)
        self.assertNotIn("bad", result.compartments_completed)
        self.assertGreater(len(result.errors), 0)


if __name__ == "__main__":
    unittest.main()

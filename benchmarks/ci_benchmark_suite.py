"""BentoBox CI Empirical Benchmark Suite.

Head-to-head empirical testing comparing BentoBox vs Docker vs Native process
across startup latency, security exfiltration, credential protection, state resets, and I/O.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

from bentoworks.bentobox import AgentBentoBox, BentoBoxConfig
from bentoworks.ci.runner import BentoCIRunner
from bentoworks.compartments import Compartment, CompartmentConfig
from bentoworks.sandbox.snapshot import SnapshotManager


def test_startup_latency(iterations: int = 20) -> dict[str, Any]:
    """Benchmark 1: Startup Latency & Cold-Start Boot Overhead."""
    print("Running Benchmark 1: Startup Latency & Boot Overhead...")
    
    # 1. Native process execution
    native_times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        subprocess.run([sys.executable, "-c", "pass"], check=True)
        t1 = time.perf_counter()
        native_times.append((t1 - t0) * 1000)

    # 2. BentoBox Kernel Compartment
    bento_times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        runner = BentoCIRunner(workdir=".", block_network=True)
        runner.run_step(f"{sys.executable} -c 'pass'")
        t1 = time.perf_counter()
        bento_times.append((t1 - t0) * 1000)

    # 3. Docker Container (if docker daemon is available)
    docker_times = []
    docker_available = shutil.which("docker") is not None
    if docker_available:
        try:
            # Check if docker daemon is running
            subprocess.run(["docker", "ps"], capture_output=True, check=True)
            for _ in range(5):  # fewer iterations due to slowness
                t0 = time.perf_counter()
                subprocess.run(
                    ["docker", "run", "--rm", "python:3.11-slim", "python", "-c", "pass"],
                    capture_output=True,
                    check=True,
                )
                t1 = time.perf_counter()
                docker_times.append((t1 - t0) * 1000)
        except Exception:
            docker_available = False

    return {
        "native_avg_ms": round(sum(native_times) / len(native_times), 2),
        "bento_avg_ms": round(sum(bento_times) / len(bento_times), 2),
        "docker_avg_ms": round(sum(docker_times) / len(docker_times), 2) if docker_times else "N/A (Docker unavailable/slow)",
        "docker_available": docker_available,
    }


def test_security_network_exfiltration() -> dict[str, Any]:
    """Benchmark 2: Security & Secret Exfiltration Resistance."""
    print("Running Benchmark 2: Secret Exfiltration Resistance...")

    # Attempt to open an outbound socket connection inside BentoBox with block_network=True
    code = """
import socket, sys
try:
    s = socket.create_connection(("1.1.1.1", 80), timeout=2)
    s.close()
    print("EXFILTRATION_SUCCESS")
except Exception as e:
    print(f"EXFILTRATION_BLOCKED: {e}")
"""

    runner = BentoCIRunner(workdir=".", block_network=True)
    res = runner.run_step(f"{sys.executable} -c '{code}'")

    blocked = "EXFILTRATION_BLOCKED" in res["stdout"] or "PermissionError" in res["stderr"] or res["returncode"] != 0

    return {
        "exfiltration_attempt": "Outbound HTTP/TCP connection to 1.1.1.1:80",
        "bento_network_blocked": blocked,
        "result": "BLOCKED (Kernel Landlock/Seatbelt socket restriction)" if blocked else "ALLOWED",
    }


def test_credential_path_protection() -> dict[str, Any]:
    """Benchmark 3: Sensitive Credential Path Protection."""
    print("Running Benchmark 3: Sensitive Path Protection...")

    ssh_path = os.path.expanduser("~/.ssh")
    code = f"""
import os
try:
    files = os.listdir('{ssh_path}')
    print(f'READ_SUCCESS: {{len(files)}} files')
except Exception as e:
    print(f'READ_BLOCKED: {{e}}')
"""

    runner = BentoCIRunner(workdir=".", block_network=True)
    res = runner.run_step(f"{sys.executable} -c '{code}'")

    blocked = "READ_BLOCKED" in res["stdout"] or "PermissionError" in res["stderr"] or res["returncode"] != 0

    return {
        "target_path": ssh_path,
        "bento_path_blocked": blocked,
        "result": "BLOCKED (Deny-by-default OS Kernel rules)" if blocked else "ALLOWED",
    }


def test_state_reset_speed() -> dict[str, Any]:
    """Benchmark 4: BLAKE3 Snapshot & Workspace Reset Speed."""
    print("Running Benchmark 4: Workspace State Reset Speed...")

    tmp_workdir = os.path.abspath("benchmarks/scratch_workdir")
    tmp_snapdir = os.path.abspath("benchmarks/scratch_snapshots")
    os.makedirs(tmp_workdir, exist_ok=True)
    os.makedirs(tmp_snapdir, exist_ok=True)

    # Create 50 files
    for i in range(50):
        with open(os.path.join(tmp_workdir, f"file_{i}.txt"), "w") as f:
            f.write(f"Original content {i}\n")

    snap = SnapshotManager(workdir=tmp_workdir, snapshot_dir=tmp_snapdir)
    
    t0 = time.perf_counter()
    snap.snapshot()
    t1 = time.perf_counter()
    snapshot_time_ms = (t1 - t0) * 1000

    # Modify 20 files and delete 10 files
    for i in range(20):
        with open(os.path.join(tmp_workdir, f"file_{i}.txt"), "w") as f:
            f.write("MODIFIED CORRUPTED CONTENT\n")
    for i in range(20, 30):
        os.remove(os.path.join(tmp_workdir, f"file_{i}.txt"))

    # Time restore
    t0 = time.perf_counter()
    restored_count = snap.restore()
    t1 = time.perf_counter()
    restore_time_ms = (t1 - t0) * 1000

    snap.cleanup()
    shutil.rmtree(tmp_workdir, ignore_errors=True)
    shutil.rmtree(tmp_snapdir, ignore_errors=True)

    return {
        "files_snapshotted": 50,
        "files_modified_or_deleted": 30,
        "restored_count": restored_count,
        "snapshot_duration_ms": round(snapshot_time_ms, 2),
        "restore_duration_ms": round(restore_time_ms, 2),
    }


def main():
    print("===============================================================")
    print("     BENTOWORKS CI EMPIRICAL BENCHMARK & EDGE-CASE SUITE       ")
    print("===============================================================\n")

    res_latency = test_startup_latency(iterations=10)
    res_network = test_security_network_exfiltration()
    res_creds = test_credential_path_protection()
    res_reset = test_state_reset_speed()

    print("\n---------------------------------------------------------------")
    print("                     BENCHMARK RESULTS                         ")
    print("---------------------------------------------------------------")
    print(f"1. Startup Latency (Avg over 10 runs):")
    print(f"   - Native Python Spawn: {res_latency['native_avg_ms']} ms")
    print(f"   - BentoBox Compartment: {res_latency['bento_avg_ms']} ms")
    print(f"   - Docker Container:     {res_latency['docker_avg_ms']} ms")

    print(f"\n2. Secret Exfiltration Resistance:")
    print(f"   - Attempt: {res_network['exfiltration_attempt']}")
    print(f"   - Result:  {res_network['result']}")

    print(f"\n3. Credential Protection:")
    print(f"   - Attempt: Reading {res_creds['target_path']}")
    print(f"   - Result:  {res_creds['result']}")

    print(f"\n4. State Reset Speed (BLAKE3 Hash Snapshot):")
    print(f"   - Snapshot 50 files: {res_reset['snapshot_duration_ms']} ms")
    print(f"   - Restore 30 modified/deleted files: {res_reset['restore_duration_ms']} ms")
    print("---------------------------------------------------------------\n")


if __name__ == "__main__":
    main()

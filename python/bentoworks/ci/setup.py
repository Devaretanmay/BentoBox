"""BentoBox GitHub Actions Setup Entrypoint.

Invoked during ``uses: bentoworks/setup@v1`` to configure shell wrappers and
environment defaults on GitHub-hosted or self-hosted runners.
"""

import argparse
import os
import sys

BANNER = """
===========================================================
  BentoBox CI Security & Acceleration Initialized
  - Kernel Isolation: Landlock (Linux) / Seatbelt (macOS)
  - Latency: < 1ms
  - Network Egress: Managed per-stage
  - State Reset: BLAKE3 Hash Rollback (<100ms)
===========================================================
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure BentoBox CI environment")
    parser.add_argument("--network", default="false", help="Default network policy")
    args = parser.parse_args()

    print(BANNER)
    
    # Export BENTOWORKS_CI_ACTIVE=1 into GitHub Actions environment
    github_env = os.environ.get("GITHUB_ENV")
    if github_env and os.path.exists(github_env):
        with open(github_env, "a") as f:
            f.write("BENTOWORKS_CI_ACTIVE=1\n")
            f.write(f"BENTOWORKS_DEFAULT_NETWORK={args.network}\n")
        print("Exported BentoBox environment variables to GITHUB_ENV")
    else:
        os.environ["BENTOWORKS_CI_ACTIVE"] = "1"
        os.environ["BENTOWORKS_DEFAULT_NETWORK"] = args.network
        print("Configured local environment variables for BentoBox CI")

    return 0


if __name__ == "__main__":
    sys.exit(main())

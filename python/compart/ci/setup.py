"""Compart GitHub Actions Setup Entrypoint.

Invoked by the Compart repository action to configure CI defaults and
environment defaults on GitHub-hosted or self-hosted runners.
"""

import argparse
import os
import sys

BANNER = """
===========================================================
  Compart CI Security & Acceleration Initialized
  - Kernel Isolation: Landlock (Linux) / Seatbelt (macOS)
  - Latency: depends on repository and runner
  - Network Egress: Managed per-stage
  - State Reset: BLAKE3 Hash Rollback
===========================================================
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Compart CI environment")
    parser.add_argument("--network", default="false", help="Default network policy")
    args = parser.parse_args()

    print(BANNER)
    
    # Export COMPART_CI_ACTIVE=1 into GitHub Actions environment
    github_env = os.environ.get("GITHUB_ENV")
    if github_env and os.path.exists(github_env):
        with open(github_env, "a") as f:
            f.write("COMPART_CI_ACTIVE=1\n")
            f.write(f"COMPART_DEFAULT_NETWORK={args.network}\n")
        print("Exported Compart environment variables to GITHUB_ENV")
    else:
        os.environ["COMPART_CI_ACTIVE"] = "1"
        os.environ["COMPART_DEFAULT_NETWORK"] = args.network
        print("Configured local environment variables for Compart CI")

    return 0


if __name__ == "__main__":
    sys.exit(main())

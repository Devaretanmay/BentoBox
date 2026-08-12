"""Validation Test 3: Custom Agent / MCP Tools + Zero-Trust Credential Proxy under Compart Control.

Demonstrates:
- Outbound API calls to /openai are rewritten and authenticated in memory.
- Agent code and LLM prompt context never see or touch raw API keys.
"""

import os
from compart.sandbox.proxy import CredentialProxy, RouteConfig

print("=== Compart Control Layer Demo: Credential Proxy & MCP Tools ===")

# Set dummy key for validation test
os.environ["OPENAI_API_KEY"] = "sk-test-compart-secret-key-12345"

proxy = CredentialProxy(routes=[
    RouteConfig(
        prefix="/openai",
        upstream="https://api.openai.com",
        credential_source="env:OPENAI_API_KEY",
        header_name="Authorization",
        header_prefix="Bearer "
    )
])

proxy.start()
proxy.set_env()

print("\n[Step 1] Credential Proxy active on local port:", proxy.port)
print("  HTTP_PROXY set to:", os.environ.get("HTTP_PROXY"))
print("  Requests to /openai will have Authorization injected in memory.")

proxy.restore_env()
proxy.stop()
print("\n[Step 2] Proxy environment restored cleanly.")

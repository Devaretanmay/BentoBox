"""CredentialModule — behaviour module that injects API credentials via a local HTTP proxy.

The module reads ``credential_rules`` from the Lid's context config,
starts a local ``CredentialProxy``, and sets ``HTTP_PROXY`` environment
variables so compartment traffic routes through the proxy.
"""

import logging
from typing import Any

from .behaviour import BehaviourModule, register
from .proxy import CredentialProxy, RouteConfig

_logger = logging.getLogger("bentoworks.credential")


@register
class CredentialModule(BehaviourModule):
    """Starts a credential-injecting HTTP proxy for the box's lifetime.

    Hooks into the ``lid.insulated`` event to start the proxy and
    ``lid.released`` to stop it.  The proxy routes are read from
    ``ctx.config["credential_rules"]``.
    """

    name = "credential"
    engine = "preparation"
    profiles = ["*"]

    def load(self, ctx) -> None:
        rules_data = ctx.config.get("credential_rules", [])
        if not rules_data:
            return

        routes = []
        for rd in rules_data:
            if isinstance(rd, RouteConfig):
                routes.append(rd)
            elif isinstance(rd, dict):
                routes.append(RouteConfig(**rd))

        if not routes:
            return

        self._proxy = CredentialProxy(routes=routes)
        self._proxy.start()
        self._proxy.set_env()
        _logger.info(
            "CredentialModule active — %d route(s), proxy at %s",
            len(routes), self._proxy.proxy_url,
        )

    def unload(self) -> None:
        proxy = getattr(self, "_proxy", None)
        if proxy is not None:
            proxy.restore_env()
            proxy.stop()

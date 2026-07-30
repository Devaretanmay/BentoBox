"""Runtime internals — for advanced users and framework developers.

Normal usage::

    from bentoworks import BentoBox

    box = BentoBox()
    box.add(Compartment(name="task", fn=my_fn))
    result = box.run()

Advanced usage::

    from bentoworks.runtime import Box, Lid, CompartmentRuntime, Compartment
"""

from .sandbox.box import Box, BoxConfig
from .sandbox.lid import Lid, LidConfig
from .sandbox.behaviour import BehaviourModule, BehaviourContext, Engine
from .compartments import Compartment, CompartmentConfig, CompartmentRuntime, CompartmentContext, Message
from .engine.events import EventBus, Event, event_bus, emit
from .engine.tracer import Tracer

__all__ = [
    "Box", "BoxConfig",
    "Lid", "LidConfig",
    "BehaviourModule", "BehaviourContext", "Engine",
    "Compartment", "CompartmentConfig", "CompartmentRuntime", "CompartmentContext", "Message",
    "EventBus", "Event", "event_bus", "emit",
    "Tracer",
]

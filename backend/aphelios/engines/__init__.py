"""APHELIOS-Engines – reale MVP-Engines und Schnittstellen-Stubs."""

from aphelios.engines.conversation_engine import ConversationEngine
from aphelios.engines.memory_engine import MemoryEngine
from aphelios.engines.stubs import (
    AgentEngine,
    AutomationEngine,
    BrowserEngine,
    CodingEngine,
    KnowledgeEngine,
    PlanningEngine,
    ReasoningEngine,
    VisionEngine,
    VoiceEngine,
)
from aphelios.engines.system_engine import SystemEngine

#: Alle Engine-Klassen, die der Standard-Bootstrap registriert.
ALL_ENGINES = [
    SystemEngine,
    ConversationEngine,
    MemoryEngine,
    ReasoningEngine,
    PlanningEngine,
    AutomationEngine,
    CodingEngine,
    BrowserEngine,
    KnowledgeEngine,
    VisionEngine,
    VoiceEngine,
    AgentEngine,
]

__all__ = [cls.__name__ for cls in ALL_ENGINES] + ["ALL_ENGINES"]

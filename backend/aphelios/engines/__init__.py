"""APHELIOS-Engines – reale MVP-Engines und Schnittstellen-Stubs."""

from aphelios.engines.automation_engine import AutomationEngine
from aphelios.engines.calendar_engine import CalendarEngine
from aphelios.engines.conversation_engine import ConversationEngine
from aphelios.engines.mail_engine import MailEngine
from aphelios.engines.memory_engine import MemoryEngine
from aphelios.engines.planning_engine import PlanningEngine
from aphelios.engines.reasoning_engine import ReasoningEngine
from aphelios.engines.stubs import (
    AgentEngine,
    BrowserEngine,
    CodingEngine,
    KnowledgeEngine,
)
from aphelios.engines.system_engine import SystemEngine
from aphelios.engines.vision_engine import VisionEngine
from aphelios.engines.voice_engine import VoiceEngine
from aphelios.engines.weather_engine import WeatherEngine

#: Alle Engine-Klassen, die der Standard-Bootstrap registriert.
#: MailEngine/CalendarEngine bleiben ohne Google-Anmeldung inaktiv (siehe
#: docs/integrations.md) – sie können daher gefahrlos immer registriert werden.
ALL_ENGINES = [
    SystemEngine,
    ConversationEngine,
    MemoryEngine,
    WeatherEngine,
    MailEngine,
    CalendarEngine,
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

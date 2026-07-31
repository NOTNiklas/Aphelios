"""APHELIOS-Engines – reale MVP-Engines und Schnittstellen-Stubs."""

from aphelios.engines.automation_engine import AutomationEngine
from aphelios.engines.briefing_engine import BriefingEngine
from aphelios.engines.browser_engine import BrowserEngine
from aphelios.engines.calendar_engine import CalendarEngine
from aphelios.engines.coding_engine import CodingEngine
from aphelios.engines.conversation_engine import ConversationEngine
from aphelios.engines.mail_engine import MailEngine
from aphelios.engines.memory_engine import MemoryEngine
from aphelios.engines.music_engine import MusicEngine
from aphelios.engines.planning_engine import PlanningEngine
from aphelios.engines.push_engine import PushEngine
from aphelios.engines.reasoning_engine import ReasoningEngine
from aphelios.engines.research_engine import ResearchEngine
from aphelios.engines.screen_share_engine import ScreenShareEngine
from aphelios.engines.knowledge_engine import KnowledgeEngine
from aphelios.engines.office_engine import OfficeEngine
from aphelios.engines.stock_engine import StockEngine
from aphelios.engines.stubs import AgentEngine
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
    MusicEngine,
    StockEngine,
    ResearchEngine,
    ScreenShareEngine,
    PushEngine,
    BriefingEngine,
    ReasoningEngine,
    PlanningEngine,
    AutomationEngine,
    CodingEngine,
    BrowserEngine,
    KnowledgeEngine,
    OfficeEngine,
    VisionEngine,
    VoiceEngine,
    AgentEngine,
]

__all__ = [cls.__name__ for cls in ALL_ENGINES] + ["ALL_ENGINES"]

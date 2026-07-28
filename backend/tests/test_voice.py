"""Tests für die VoiceEngine (Alpha 1.3): Piper-TTS + faster-whisper-STT.

Echte Modelle lassen sich in dieser Sandbox nicht laden (Hugging Face Hub
liefert 403 über den Sandbox-Proxy, siehe auch WeatherEngine-Logs) – deshalb
werden Piper-Voice/Whisper-Model per Attribut-Injektion
(``engine._piper_voice`` / ``engine._whisper_model``) direkt gesetzt. Das ist
kein Test-Hack: ``_ensure_piper``/``_ensure_whisper`` erkennen "bereits
geladen" genau darüber (dasselbe Lazy-Load-Muster wie
``ConversationEngine._client``). Getestet wird damit die eigentliche Logik –
WAV-Erzeugung, Base64-Kodierung, Bus-Verdrahtung, Fallback ohne Modell –
nicht die Modell-Qualität selbst.
"""

from __future__ import annotations

import base64
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines.voice_engine import VoiceEngine


def _engine(bus: EventBus, **config_kwargs) -> VoiceEngine:
    return VoiceEngine(bus, Config(**config_kwargs), SecurityGate(bus))


# -- Fakes für Piper (kein echtes Modell nötig) -------------------------------
@dataclass
class _FakeChunk:
    audio_int16_bytes: bytes


@dataclass
class _FakePiperConfig:
    sample_rate: int = 22050


class _FakePiperVoice:
    def __init__(self, sample_rate: int = 22050, raise_on_synthesize: bool = False) -> None:
        self.config = _FakePiperConfig(sample_rate)
        self._raise = raise_on_synthesize

    def synthesize(self, text: str):
        if self._raise:
            raise RuntimeError("Synthese kaputt")
        yield _FakeChunk(audio_int16_bytes=b"\x00\x00" * 100)  # 100 Samples Stille


# -- Fakes für Whisper (kein echtes Modell nötig) -----------------------------
@dataclass
class _FakeSegment:
    text: str


class _FakeWhisperModel:
    def __init__(self, text: str = "hallo aphelios", raise_on_transcribe: bool = False) -> None:
        self._text = text
        self._raise = raise_on_transcribe

    def transcribe(self, audio, language=None):
        if self._raise:
            raise RuntimeError("Transkription kaputt")
        return [_FakeSegment(self._text)], object()


# -- TTS: voice.speak ----------------------------------------------------------
async def test_speak_without_configured_piper_reports_error():
    bus = EventBus()
    engine = _engine(bus)  # piper_model_path leer -> has_piper False
    await engine.start()

    errors: list[dict] = []
    bus.subscribe("voice.error", lambda e: errors.append(e.data))
    await engine.handle_speak(Event("voice.speak", {"id": "s1", "text": "Hallo"}))

    assert len(errors) == 1
    assert "APHELIOS_PIPER_MODEL_PATH" in errors[0]["error"]


async def test_speak_with_empty_text_does_nothing():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    engine._piper_voice = _FakePiperVoice()

    events: list[dict] = []
    bus.subscribe("voice.audio", lambda e: events.append(e.data))
    bus.subscribe("voice.error", lambda e: events.append(e.data))
    await engine.handle_speak(Event("voice.speak", {"id": "s1", "text": "   "}))

    assert events == []


async def test_speak_produces_valid_base64_wav_with_injected_voice():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    engine._piper_voice = _FakePiperVoice(sample_rate=22050)

    audios: list[dict] = []
    bus.subscribe("voice.audio", lambda e: audios.append(e.data))
    await engine.handle_speak(Event("voice.speak", {"id": "s2", "text": "Hallo, ich bin APHELIOS."}))

    assert len(audios) == 1
    payload = audios[0]
    assert payload["id"] == "s2"
    assert payload["sample_rate"] == 22050
    assert payload["format"] == "wav"

    # Base64 muss ein gültiges, abspielbares WAV dekodieren.
    wav_bytes = base64.b64decode(payload["audio_base64"])
    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 22050
        assert wav_file.getnframes() == 100


async def test_speak_reports_error_when_synthesis_raises():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    engine._piper_voice = _FakePiperVoice(raise_on_synthesize=True)

    errors: list[dict] = []
    bus.subscribe("voice.error", lambda e: errors.append(e.data))
    await engine.handle_speak(Event("voice.speak", {"id": "s3", "text": "Test"}))

    assert len(errors) == 1
    assert "TTS fehlgeschlagen" in errors[0]["error"]


async def test_ensure_piper_only_attempts_load_once():
    # Regression: ein fehlgeschlagener Ladeversuch darf nicht bei jeder
    # Anfrage erneut (langsam) versucht werden.
    bus = EventBus()
    engine = _engine(bus)  # kein Modell konfiguriert
    await engine.start()

    await engine._ensure_piper()
    first_error = engine._piper_init_error
    await engine._ensure_piper()

    assert engine._piper_init_error == first_error
    assert engine._piper_init_error is not None


# -- STT: voice.transcribe -----------------------------------------------------
async def test_transcribe_without_model_reports_error():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    # Simuliert "Whisper-Paket nicht installiert oder Modell nicht ladbar".
    engine._whisper_init_error = "Whisper-Modell konnte nicht geladen werden: kein Netz"

    errors: list[dict] = []
    bus.subscribe("voice.error", lambda e: errors.append(e.data))
    await engine.handle_transcribe(Event("voice.transcribe", {"id": "t1", "audio_base64": "AAAA"}))

    assert len(errors) == 1
    assert "Whisper-Modell" in errors[0]["error"]


async def test_transcribe_returns_text_with_injected_model():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    engine._whisper_model = _FakeWhisperModel(text="Wie ist die CPU-Auslastung?")

    transcripts: list[dict] = []
    bus.subscribe("voice.transcript", lambda e: transcripts.append(e.data))
    audio_b64 = base64.b64encode(b"fake-audio-bytes").decode("ascii")
    await engine.handle_transcribe(Event("voice.transcribe", {"id": "t2", "audio_base64": audio_b64}))

    assert transcripts == [{"id": "t2", "text": "Wie ist die CPU-Auslastung?"}]


async def test_transcribe_joins_multiple_segments():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()

    class _MultiSegmentModel:
        def transcribe(self, audio, language=None):
            return [_FakeSegment("Hallo"), _FakeSegment("Aphelios")], object()

    engine._whisper_model = _MultiSegmentModel()

    transcripts: list[dict] = []
    bus.subscribe("voice.transcript", lambda e: transcripts.append(e.data))
    audio_b64 = base64.b64encode(b"x").decode("ascii")
    await engine.handle_transcribe(Event("voice.transcribe", {"id": "t3", "audio_base64": audio_b64}))

    assert transcripts[0]["text"] == "Hallo Aphelios"


async def test_transcribe_without_audio_does_nothing():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    engine._whisper_model = _FakeWhisperModel()

    events: list[dict] = []
    bus.subscribe("voice.transcript", lambda e: events.append(e.data))
    bus.subscribe("voice.error", lambda e: events.append(e.data))
    await engine.handle_transcribe(Event("voice.transcribe", {"id": "t4", "audio_base64": ""}))

    assert events == []


async def test_transcribe_reports_error_when_model_raises():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    engine._whisper_model = _FakeWhisperModel(raise_on_transcribe=True)

    errors: list[dict] = []
    bus.subscribe("voice.error", lambda e: errors.append(e.data))
    audio_b64 = base64.b64encode(b"x").decode("ascii")
    await engine.handle_transcribe(Event("voice.transcribe", {"id": "t5", "audio_base64": audio_b64}))

    assert len(errors) == 1
    assert "Transkription fehlgeschlagen" in errors[0]["error"]


# -- Config ---------------------------------------------------------------------
def test_has_piper_false_when_path_empty():
    assert Config().has_piper is False


def test_has_piper_false_when_path_does_not_exist():
    assert Config(piper_model_path=Path(__file__ + "-does-not-exist")).has_piper is False

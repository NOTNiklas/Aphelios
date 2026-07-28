"""VoiceEngine – lokale Sprachein-/ausgabe: Piper-TTS + faster-whisper-STT
(Alpha 1.3, erste Ausbaustufe).

Ergänzt die browserbasierte Web Speech API (`frontend/src/voice/`) um eine
echte, lokale Alternative statt der robotischen Standard-Browserstimme:

- **TTS** (`voice.speak`): [Piper](https://github.com/rhasspy/piper) erzeugt
  eine natürliche, tiefe männliche Stimme lokal auf dem PC – kein Cloud-
  Dienst, kein API-Key. Ohne konfiguriertes Modell
  (`APHELIOS_PIPER_MODEL_PATH`, siehe `docs/voice.md`) bleibt die Engine für
  TTS inaktiv und meldet das über `voice.error` – das Frontend fällt dann
  automatisch auf die Browser-Stimme zurück, das HUD bleibt also immer
  sprachfähig, nur eben mit der bisherigen Qualität.
- **STT** (`voice.transcribe`): [faster-whisper](
  https://github.com/SYSTRAN/faster-whisper) transkribiert eine
  Audio-Aufnahme lokal. Das Modell wird beim ersten Gebrauch automatisch von
  Hugging Face heruntergeladen und danach lokal zwischengespeichert.

Beide Modelle werden lazy geladen (erst beim ersten `voice.speak`/
`voice.transcribe`), damit ein Start ohne konfigurierte Sprachmodelle nicht
durch mehrsekündiges Modell-Laden verzögert wird – dasselbe Muster wie der
lazy geladene Claude-Client in der ConversationEngine.

Bus-Schnittstelle:
    * ``voice.speak`` (in) – ``{id, text}``
      → ``voice.audio`` (out) ``{id, audio_base64, sample_rate, format:"wav"}``
      → oder ``voice.error`` (out) ``{id, error}``, wenn kein Modell konfiguriert
        oder das Laden/die Synthese fehlschlägt
    * ``voice.transcribe`` (in) – ``{id, audio_base64}`` (beliebiges von
      PyAV/ffmpeg dekodierbares Audioformat, z. B. das, was der Browser per
      MediaRecorder liefert)
      → ``voice.transcript`` (out) ``{id, text}``
      → oder ``voice.error`` (out) ``{id, error}``
"""

from __future__ import annotations

import asyncio
import base64
import io
import wave

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event


class VoiceEngine(BaseEngine):
    """Synthetisiert Sprache (Piper) und transkribiert Audio (Whisper) lokal."""

    name = "voice"

    async def start(self) -> None:
        self._running = True
        self._piper_voice = None
        self._piper_init_error: str | None = None
        self._whisper_model = None
        self._whisper_init_error: str | None = None
        self.bus.subscribe("voice.speak", self.handle_speak)
        self.bus.subscribe("voice.transcribe", self.handle_transcribe)

    # -- TTS ------------------------------------------------------------------
    async def handle_speak(self, event: Event) -> None:
        request_id = event.data.get("id", "")
        text = (event.data.get("text") or "").strip()
        if not text:
            return
        voice = await self._ensure_piper()
        if voice is None:
            await self.emit("voice.error", {"id": request_id, "error": self._piper_init_error})
            return
        try:
            audio_bytes, sample_rate = await asyncio.to_thread(self._synthesize, voice, text)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Piper-Synthese fehlgeschlagen")
            await self.emit("voice.error", {"id": request_id, "error": f"TTS fehlgeschlagen: {exc}"[:200]})
            return
        await self.emit(
            "voice.audio",
            {
                "id": request_id,
                "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
                "sample_rate": sample_rate,
                "format": "wav",
            },
        )

    def _synthesize(self, voice, text: str) -> tuple[bytes, int]:  # noqa: ANN001
        """Läuft in einem Thread (blockierende ONNX-Inferenz)."""
        sample_rate = voice.config.sample_rate
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(sample_rate)
            for chunk in voice.synthesize(text):
                wav_file.writeframes(chunk.audio_int16_bytes)
        return buffer.getvalue(), sample_rate

    async def _ensure_piper(self):  # noqa: ANN201
        if self._piper_voice is not None or self._piper_init_error is not None:
            return self._piper_voice
        if not self.config.has_piper:
            self._piper_init_error = (
                "Kein Piper-Sprachmodell konfiguriert (APHELIOS_PIPER_MODEL_PATH "
                "in der .env) – siehe docs/voice.md."
            )
            return None
        try:
            from piper import PiperVoice

            self._piper_voice = await asyncio.to_thread(
                PiperVoice.load, str(self.config.piper_model_path)
            )
            self.log.info("Piper-Sprachmodell geladen: %s", self.config.piper_model_path)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Piper-Modell konnte nicht geladen werden")
            self._piper_init_error = f"Piper-Modell konnte nicht geladen werden: {exc}"[:200]
        return self._piper_voice

    # -- STT ------------------------------------------------------------------
    async def handle_transcribe(self, event: Event) -> None:
        request_id = event.data.get("id", "")
        audio_b64 = event.data.get("audio_base64") or ""
        if not audio_b64:
            return
        model = await self._ensure_whisper()
        if model is None:
            await self.emit("voice.error", {"id": request_id, "error": self._whisper_init_error})
            return
        try:
            audio_bytes = base64.b64decode(audio_b64)
            text = await asyncio.to_thread(self._transcribe, model, audio_bytes)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Whisper-Transkription fehlgeschlagen")
            await self.emit(
                "voice.error", {"id": request_id, "error": f"Transkription fehlgeschlagen: {exc}"[:200]}
            )
            return
        await self.emit("voice.transcript", {"id": request_id, "text": text})

    def _transcribe(self, model, audio_bytes: bytes) -> str:  # noqa: ANN001
        """Läuft in einem Thread (blockierende Inferenz)."""
        segments, _info = model.transcribe(io.BytesIO(audio_bytes), language="de")
        return " ".join(segment.text.strip() for segment in segments).strip()

    async def _ensure_whisper(self):  # noqa: ANN201
        if self._whisper_model is not None or self._whisper_init_error is not None:
            return self._whisper_model
        try:
            from faster_whisper import WhisperModel

            self._whisper_model = await asyncio.to_thread(
                WhisperModel,
                self.config.whisper_model,
                device=self.config.whisper_device,
                compute_type="int8",
            )
            self.log.info("Whisper-Modell geladen: %s (%s)", self.config.whisper_model, self.config.whisper_device)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Whisper-Modell konnte nicht geladen werden")
            self._whisper_init_error = f"Whisper-Modell konnte nicht geladen werden: {exc}"[:200]
        return self._whisper_model

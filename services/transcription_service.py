"""
Transcription Service - Servicio OOP para manejar transcripciones de llamadas
Gestiona el almacenamiento, procesamiento y recuperación de transcripciones
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TranscriptionService:
    """
    Servicio para manejar todas las operaciones relacionadas con transcripciones.
    Arquitectura OOP para mantener el código organizado y mantenible.
    """

    def __init__(self):
        """
        Inicializa el servicio de transcripciones.
        """
        # Almacenamiento de transcripciones por call_id
        self.call_transcriptions: Dict[str, List[str]] = {}

        # Metadata adicional de las transcripciones
        self.call_metadata: Dict[str, Dict[str, Any]] = {}

        logger.info("[TRANSCRIPTION-SERVICE] ✅ Servicio inicializado")

    def process_websocket_event(self, event_type: str, event_data: Dict[str, Any], call_id: str) -> bool:
        """
        Procesa eventos del WebSocket y decide si mostrarlos en logs.

        Args:
            event_type: Tipo de evento recibido
            event_data: Datos completos del evento
            call_id: ID de la llamada

        Returns:
            bool: True si el evento debe ser silenciado, False si debe mostrarse
        """
        # Eventos que NO queremos loggear (muy verbosos)
        skip_events = [
            "response.output_audio_transcript.delta",
            "conversation.item.input_audio_transcription.delta",
            "output_audio_buffer.started",
            "output_audio_buffer.stopped",
            "input_audio_buffer.speech_started",
            "input_audio_buffer.speech_stopped",
            "input_audio_buffer.committed",
            "response.output_audio.done"
        ]

        # Silenciar eventos ruidosos
        if event_type in skip_events:
            return True

        # Procesar eventos importantes de transcripción
        if event_type in ["conversation.item.input_audio_transcription.completed",
                          "response.output_audio_transcript.done"]:
            transcript = event_data.get("transcript", "")
            if transcript:
                if "input_audio_transcription" in event_type:
                    logger.info(f"[TRANSCRIPT] 🗣️ Cliente: {transcript}")
                    self.add_transcription(call_id, "Cliente", transcript)
                else:
                    logger.info(f"[TRANSCRIPT] 🤖 Jessica: {transcript}")
                    self.add_transcription(call_id, "Jessica", transcript)
            return True

        # Otros eventos no relacionados con transcripción
        return False

    def add_transcription(self, call_id: str, speaker: str, message: str) -> None:
        """
        Agrega una transcripción al almacenamiento.

        Args:
            call_id: ID de la llamada
            speaker: Quién habla (Cliente/Jessica)
            message: El mensaje transcrito
        """
        try:
            # Inicializar si no existe
            if call_id not in self.call_transcriptions:
                self.call_transcriptions[call_id] = []
                self.call_metadata[call_id] = {
                    "started_at": datetime.now().isoformat(),
                    "message_count": 0,
                    "last_message_at": None
                }

            # Agregar transcripción
            formatted_message = f"{speaker}: {message}"
            self.call_transcriptions[call_id].append(formatted_message)

            # Actualizar metadata
            self.call_metadata[call_id]["message_count"] += 1
            self.call_metadata[call_id]["last_message_at"] = datetime.now().isoformat()

            logger.debug(f"[TRANSCRIPT-STORED] {formatted_message}")

        except Exception as e:
            logger.error(f"[TRANSCRIPTION-SERVICE] Error almacenando transcripción: {e}")

    def store_from_realtime_event(self, event_data: Dict[str, Any], call_id: str) -> None:
        """
        Almacena transcripciones desde eventos del proceso realtime.
        Este método es llamado desde process_realtime_event.

        Args:
            event_data: Datos del evento
            call_id: ID de la llamada
        """
        event_type = event_data.get("type")

        # 🔍 LOGGING MÍNIMO solo para eventos importantes
        if ("conversation.item.input_audio_transcription" in event_type or
            (event_type in ["conversation.item.added", "conversation.item.done"] and
             event_data.get("item", {}).get("role") == "user")):
            logger.info(f"[TRANSCRIPT-DEBUG] 🎯 Evento cliente: {event_type}")

            # Solo loggear contenido relevante para transcripciones de cliente
            if event_type in ["conversation.item.added", "conversation.item.done"]:
                item = event_data.get("item", {})
                content = item.get("content", [])
                for c in content:
                    if c.get("type") == "input_audio":
                        transcript = c.get("transcript")
                        logger.info(f"[TRANSCRIPT-DEBUG] 📝 Cliente transcript: {transcript}")
                        break

        # 🎯 FORMATO GA: Capturar transcripciones de conversation.item events
        if event_type in ["conversation.item.added", "conversation.item.done"]:
            item = event_data.get("item", {})
            if item.get("role") == "user" and item.get("status") == "completed":
                # Extraer transcript del content
                content = item.get("content", [])
                for content_item in content:
                    if content_item.get("type") == "input_audio":
                        transcript = content_item.get("transcript")
                        if transcript and transcript.strip():
                            logger.info(f"[TRANSCRIPT-CLIENT] 🗣️ Cliente detectado (GA): '{transcript.strip()}'")
                            self.add_transcription(call_id, "Cliente", transcript.strip())
                        else:
                            logger.debug(f"[TRANSCRIPT-CLIENT] ⏸️ Cliente sin transcript disponible aún")

        # MANTENER compatibilidad con formato beta (si llega)
        if event_type == "conversation.item.input_audio_transcription.completed":
            user_transcript = event_data.get("transcript", "").strip()
            if user_transcript:
                logger.info(f"[TRANSCRIPT-CLIENT] 🗣️ Cliente detectado (BETA): '{user_transcript}'")
                self.add_transcription(call_id, "Cliente", user_transcript)
            else:
                logger.warning(f"[TRANSCRIPT-CLIENT] ⚠️ Evento de cliente sin transcript")

        elif event_type == "response.output_audio_transcript.done":
            ai_transcript = event_data.get("transcript", "").strip()
            if ai_transcript:
                logger.info(f"[TRANSCRIPT-JESSICA] 🤖 Jessica detectada: '{ai_transcript}'")
                self.add_transcription(call_id, "Jessica", ai_transcript)
            else:
                logger.warning(f"[TRANSCRIPT-JESSICA] ⚠️ Evento de Jessica sin transcript")

    def get_full_transcript(self, call_id: str) -> str:
        """
        Obtiene la transcripción completa de una llamada.

        Args:
            call_id: ID de la llamada

        Returns:
            str: Transcripción completa formateada
        """
        try:
            if call_id in self.call_transcriptions:
                transcript = "\n".join(self.call_transcriptions[call_id])
                message_count = len(self.call_transcriptions[call_id])
                logger.info(f"[TRANSCRIPTION-SERVICE] ✅ Transcript recuperado: {message_count} mensajes")
                return transcript
            else:
                logger.warning(f"[TRANSCRIPTION-SERVICE] ⚠️ No hay transcript para call_id: {call_id}")
                return ""

        except Exception as e:
            logger.error(f"[TRANSCRIPTION-SERVICE] Error obteniendo transcript: {e}")
            return ""

    def get_transcript_list(self, call_id: str) -> List[str]:
        """
        Obtiene la lista de mensajes transcritos.

        Args:
            call_id: ID de la llamada

        Returns:
            List[str]: Lista de mensajes transcritos
        """
        return self.call_transcriptions.get(call_id, [])

    def get_transcript_with_metadata(self, call_id: str) -> Dict[str, Any]:
        """
        Obtiene transcripción completa con metadata.

        Args:
            call_id: ID de la llamada

        Returns:
            Dict con transcripción y metadata
        """
        return {
            "call_id": call_id,
            "transcript": self.get_full_transcript(call_id),
            "messages": self.get_transcript_list(call_id),
            "metadata": self.call_metadata.get(call_id, {}),
            "message_count": len(self.call_transcriptions.get(call_id, []))
        }

    def clear_transcript(self, call_id: str) -> None:
        """
        Limpia la transcripción de una llamada después de procesarla.

        Args:
            call_id: ID de la llamada
        """
        try:
            if call_id in self.call_transcriptions:
                message_count = len(self.call_transcriptions[call_id])
                logger.info(f"[TRANSCRIPTION-SERVICE] 🧹 Limpiando transcript de {call_id}")
                logger.info(f"[TRANSCRIPTION-SERVICE] 📊 Mensajes capturados: {message_count}")

                del self.call_transcriptions[call_id]

                if call_id in self.call_metadata:
                    del self.call_metadata[call_id]
            else:
                logger.debug(f"[TRANSCRIPTION-SERVICE] No hay transcript que limpiar para: {call_id}")

        except Exception as e:
            logger.error(f"[TRANSCRIPTION-SERVICE] Error limpiando transcript: {e}")

    def has_transcript(self, call_id: str) -> bool:
        """
        Verifica si existe una transcripción para una llamada.

        Args:
            call_id: ID de la llamada

        Returns:
            bool: True si existe transcripción
        """
        return call_id in self.call_transcriptions

    def get_active_transcripts_count(self) -> int:
        """
        Obtiene el número de transcripciones activas en memoria.

        Returns:
            int: Número de transcripciones activas
        """
        return len(self.call_transcriptions)

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas generales del servicio.

        Returns:
            Dict con estadísticas
        """
        total_messages = sum(len(msgs) for msgs in self.call_transcriptions.values())

        return {
            "active_calls": self.get_active_transcripts_count(),
            "total_messages": total_messages,
            "calls_with_metadata": len(self.call_metadata)
        }

    async def get_call_transcriptions(self, call_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene transcripciones estructuradas para PostAICallService.

        Args:
            call_id: ID de la llamada

        Returns:
            List[Dict] con formato [{"speaker": "Cliente|Jessica", "message": "..."}]
        """
        try:
            if call_id not in self.call_transcriptions:
                logger.warning(f"[TRANSCRIPTION-SERVICE] No hay transcripciones para call_id: {call_id}")
                return []

            structured_transcriptions = []
            messages = self.call_transcriptions[call_id]

            for message in messages:
                # Parsear el formato "Speaker: message" si está presente
                if ": " in message:
                    parts = message.split(": ", 1)
                    speaker = parts[0].strip()
                    content = parts[1].strip()

                    # Normalizar nombres de speakers
                    if speaker.lower() in ["user", "cliente", "client"]:
                        speaker = "Cliente"
                    elif speaker.lower() in ["assistant", "ai", "jessica"]:
                        speaker = "Jessica"

                    structured_transcriptions.append({
                        "speaker": speaker,
                        "message": content,
                        "timestamp": datetime.now().isoformat()  # Aproximado
                    })
                else:
                    # Si no tiene formato speaker, asumir que es del cliente
                    structured_transcriptions.append({
                        "speaker": "Cliente",
                        "message": message.strip(),
                        "timestamp": datetime.now().isoformat()
                    })

            logger.info(f"[TRANSCRIPTION-SERVICE] ✅ Transcripciones estructuradas obtenidas: {len(structured_transcriptions)} mensajes para {call_id}")
            return structured_transcriptions

        except Exception as e:
            logger.error(f"[TRANSCRIPTION-SERVICE] ❌ Error obteniendo transcripciones para {call_id}: {e}")
            return []
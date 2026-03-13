"""
Post AI Call Service - Call Center Edition
Servicio simplificado para procesar llamadas post-AI en ambiente call center.

RESPONSABILIDADES:
- Guardar transcripción a call_history
- Finalizar llamada en Vicidial
- Log de completitud de llamada
- Estructuración simple y directa
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PostAICallService:
    """
    Orquesta el procesamiento post-llamada para call center.

    Simplificado comparado con el sistema de barbería/restaurante.
    Solo se encarga de:
    - Guardar transcripción
    - Finalizar la llamada en Vicidial
    - Logging básico
    """

    def __init__(
        self,
        database_manager=None,
        transcription_service=None,
        call_history_service=None,
        vicidial_service=None
    ):
        """
        Inicializa el servicio post-llamada para call center.

        Args:
            database_manager: Instancia del DatabaseManager
            transcription_service: Servicio de transcripciones
            call_history_service: Servicio de historial de llamadas
            vicidial_service: Servicio de Vicidial para finalizar llamadas
        """
        self.db = database_manager
        self.transcription_service = transcription_service
        self.call_history_service = call_history_service
        self.vicidial_service = vicidial_service

        logger.info("[POST-CALL] ✅ Servicio call center inicializado")

    async def process_call(
        self,
        call_id: str,
        tenant_id: str,
        branch_id: str,
        caller_phone: str,
        call_duration: float,
        timezone: str = "America/Mexico_City",
        technical_logs: list = None,
        call_status: str = "completed"
    ) -> Dict[str, Any]:
        """
        Procesa una llamada completa después de que termina.

        Este es el punto de entrada principal para call center.
        Flujo simple: guardar transcript → finalizar en Vicidial → log

        Args:
            call_id: ID de la llamada (OpenAI call ID)
            tenant_id: ID del tenant
            branch_id: ID de la branch
            caller_phone: Teléfono del cliente
            call_duration: Duración de la llamada en segundos
            timezone: Timezone del branch (para logs)
            technical_logs: Logs técnicos capturados durante la llamada
            call_status: Estado de la llamada (completed, failed, etc.)

        Returns:
            Dict con resultados del procesamiento
        """
        logger.info(f"[POST-CALL] 🚀 INICIANDO procesamiento post-llamada para call_id: {call_id}")
        logger.info(f"[POST-CALL] Tenant: {tenant_id}, Branch: {branch_id}, Phone: {caller_phone}")
        logger.info(f"[POST-CALL] Duración: {call_duration}s, Estado: {call_status}")
        logger.info(f"[POST-CALL] 🌍 Timezone: {timezone}")

        try:
            # 1. 📋 Construir conversación completa desde transcripción
            full_conversation, conversation_data = await self._build_full_conversation(call_id)

            if not full_conversation:
                logger.warning(f"[POST-CALL] ⚠️ No hay conversación para procesar: {call_id}")
                full_conversation = "Sin conversación registrada"

            logger.info(f"[POST-CALL] ✅ Conversación construida: {len(conversation_data)} mensajes")

            # 2. 💾 Guardar historial de llamada
            await self._save_call_history(
                call_id=call_id,
                tenant_id=tenant_id,
                branch_id=branch_id,
                caller_phone=caller_phone,
                call_duration=call_duration,
                full_transcript=full_conversation,
                call_status=call_status,
                technical_logs=technical_logs or []
            )

            # 3. 📞 Finalizar llamada en Vicidial
            await self._finalize_in_vicidial(
                call_id=call_id,
                caller_phone=caller_phone,
                call_status=call_status,
                call_duration=call_duration
            )

            logger.info(f"[POST-CALL] ✅ Procesamiento completado para {call_id}")
            return {
                "success": True,
                "call_id": call_id,
                "status": call_status,
                "duration": call_duration,
                "messages_count": len(conversation_data)
            }

        except Exception as e:
            logger.error(f"[POST-CALL] ❌ Error procesando call_id {call_id}: {e}", exc_info=True)
            return {
                "success": False,
                "call_id": call_id,
                "error": str(e)
            }

    async def _build_full_conversation(self, call_id: str) -> tuple[str, List[Dict[str, Any]]]:
        """
        Construye la conversación completa usando TranscriptionService.

        Args:
            call_id: ID de la llamada

        Returns:
            Tuple de (conversación formateada, lista de transcripciones)
        """
        try:
            if not self.transcription_service:
                logger.error("[POST-CALL] ⚠️ TranscriptionService no disponible")
                return "", []

            # Obtener transcripciones del call_id
            transcriptions = await self.transcription_service.get_call_transcriptions(call_id)

            if not transcriptions:
                logger.warning(f"[POST-CALL] ⚠️ No hay transcripciones para call_id: {call_id}")
                return "", []

            # Construir conversación legible
            clean_messages = []
            for transcript in transcriptions:
                speaker = transcript.get('speaker', 'Unknown')
                message = transcript.get('message', '').strip()
                if message:
                    clean_messages.append(f"{speaker}: {message}")

            full_conversation = "\n".join([
                "=== CONVERSACIÓN COMPLETA ===",
                "\n".join(clean_messages) if clean_messages else "Sin conversación registrada",
                "=== FIN CONVERSACIÓN ==="
            ])

            logger.info(f"[POST-CALL] ✅ Conversación construida: {len(clean_messages)} mensajes")
            return full_conversation, transcriptions

        except Exception as e:
            logger.error(f"[POST-CALL] ❌ Error construyendo conversación: {e}")
            return "", []

    async def _save_call_history(
        self,
        call_id: str,
        tenant_id: str,
        branch_id: str,
        caller_phone: str,
        call_duration: float,
        full_transcript: str,
        call_status: str,
        technical_logs: list
    ) -> None:
        """
        Guarda el historial de la llamada en la base de datos.

        Args:
            call_id: ID de la llamada
            tenant_id: ID del tenant
            branch_id: ID de la rama
            caller_phone: Teléfono de quien llamó
            call_duration: Duración en segundos
            full_transcript: Transcripción completa
            call_status: Estado de la llamada
            technical_logs: Logs técnicos
        """
        try:
            if not self.call_history_service:
                logger.error("[POST-CALL] ⚠️ CallHistoryService no disponible")
                return

            logger.info(f"[POST-CALL] 💾 Guardando historial para {call_id}")

            # Metadatos técnicos
            metadata = {
                "call_source": "openai_sip_realtime",
                "ai_processed": True,
                "technical_logs": technical_logs,
                "processing_timestamp": time.time(),
                "mode": "call_center"
            }

            # Guardar historial
            history_result = await self.call_history_service.save_call_history(
                call_id=call_id,
                tenant_id=tenant_id,
                branch_id=branch_id,
                from_number=caller_phone,
                to_number="sip-openai-realtime",
                duration_seconds=int(call_duration),
                full_transcript=full_transcript,
                call_status=call_status,
                additional_metadata=metadata
            )

            if history_result:
                logger.info(f"[POST-CALL] ✅ Historial guardado exitosamente para {call_id}")
            else:
                logger.warning(f"[POST-CALL] ⚠️ No se pudo guardar historial para {call_id}")

        except Exception as e:
            logger.error(f"[POST-CALL] ❌ Error guardando historial: {e}", exc_info=True)

    async def _finalize_in_vicidial(
        self,
        call_id: str,
        caller_phone: str,
        call_status: str,
        call_duration: float
    ) -> None:
        """
        Finaliza la llamada en Vicidial con el estado correcto.

        Args:
            call_id: ID de la llamada
            caller_phone: Teléfono del cliente
            call_status: Estado final de la llamada
            call_duration: Duración total de la llamada
        """
        try:
            if not self.vicidial_service:
                logger.warning(f"[POST-CALL] ⚠️ VicidialService no disponible, no se finaliza en Vicidial")
                return

            logger.info(f"[POST-CALL] 📞 Finalizando en Vicidial con estado: {call_status}")

            # Mapear estado de OpenAI/nuestro sistema a estado de Vicidial
            vicidial_status = self._map_to_vicidial_status(call_status)

            hangup_result = await self.vicidial_service.hangup_call(
                openai_call_id=call_id,
                status=vicidial_status,
                notes=f"IA call completed - {call_status}"
            )

            if hangup_result.get("success"):
                logger.info(f"[POST-CALL] ✅ Llamada finalizada en Vicidial exitosamente")
            else:
                logger.warning(f"[POST-CALL] ⚠️ Error finalizando en Vicidial: {hangup_result.get('error')}")

        except Exception as e:
            logger.error(f"[POST-CALL] ❌ Error en _finalize_in_vicidial: {e}", exc_info=True)

    def _map_to_vicidial_status(self, call_status: str) -> str:
        """
        Mapea el estado de la llamada al formato de Vicidial.

        Args:
            call_status: Estado interno de la llamada

        Returns:
            Estado en formato de Vicidial
        """
        status_map = {
            "completed": "INFO",
            "sale": "SALE",
            "not_interested": "NI",
            "callback": "CALLBK",
            "transferred": "XFER",
            "dnc": "DNC",
            "failed": "NI",
            "abandoned": "NI",
        }

        return status_map.get(call_status, "INFO")

    def get_service_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas del servicio.
        Útil para monitoring.
        """
        return {
            "service": "PostAICallService",
            "mode": "call_center",
            "services_available": {
                "transcription": self.transcription_service is not None,
                "call_history": self.call_history_service is not None,
                "vicidial": self.vicidial_service is not None
            },
            "status": "active"
        }

"""
Call History Service - Servicio OOP para manejar historial de llamadas
Guarda transcripciones completas con metadata rica y análisis inteligente
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from utils.helpers import get_mexico_timezone

logger = logging.getLogger(__name__)


class CallHistoryService:
    """
    Servicio para manejar el historial de llamadas con arquitectura OOP.
    Diseñado para ser multitenant y flexible sin lógica hardcodeada.
    """

    def __init__(self, database_manager=None, tenant_service=None):
        """
        Inicializa el servicio de historial de llamadas.

        Args:
            database_manager: Instancia del DatabaseManager
            tenant_service: Instancia del TenantService
        """
        self.db = database_manager
        self.tenant_service = tenant_service
        logger.info("[CALL-HISTORY-SERVICE] ✅ Servicio inicializado")

    async def save_call_history(
        self,
        call_id: str,
        tenant_id: str,
        branch_id: str,
        from_number: str,
        to_number: str,
        duration_seconds: int,
        full_transcript: str,
        reservation_created: bool = False,
        reservation_id: Optional[str] = None,
        call_status: str = "completed",
        additional_metadata: Optional[Dict[str, Any]] = None,
        client_id: Optional[str] = None  # 🆕 NUEVO parámetro
    ) -> Optional[str]:
        """
        Guarda el historial completo de una llamada en la base de datos.

        Args:
            call_id: ID único de la llamada (OpenAI call_id)
            tenant_id: ID del tenant para multitenant
            branch_id: ID de la sucursal para RLS
            from_number: Número del cliente que llama
            to_number: Número de destino
            duration_seconds: Duración total de la llamada
            full_transcript: Transcripción completa Cliente/Jessica
            reservation_created: Si se creó una reserva (determinado por Post-AI)
            reservation_id: ID de reserva creada (si aplica)
            call_status: Estado final de la llamada
            additional_metadata: Metadata adicional específica del tenant
            client_id: ID del cliente en la tabla clients (NUEVO)

        Returns:
            ID del registro de historial creado o None si falló
        """
        try:
            logger.info(f"[CALL-HISTORY] 💾 Guardando historial para call_id: {call_id}")

            # Generar metadata rica de la conversación
            conversation_metadata = self._analyze_conversation_metadata(full_transcript)

            # Obtener información del tenant para contexto
            tenant_info = await self._get_tenant_context(tenant_id, branch_id)

            # Crear metadata completa combinando todo
            call_metadata = {
                "conversation_analysis": conversation_metadata,
                "tenant_info": tenant_info,
                "system_info": {
                    "version": "2.0_sip_realtime",
                    "language": "es",
                    "analysis_timestamp": datetime.now(get_mexico_timezone()).isoformat(),
                    "processor": "openai_sip_realtime"
                }
            }

            # Agregar metadata adicional si se proporciona
            if additional_metadata:
                call_metadata["custom"] = additional_metadata

            # Preparar datos para inserción (adaptado al schema legacy existente)
            history_data = {
                "tenant_id": tenant_id,
                "branch_id": branch_id,  # CRÍTICO para RLS
                "call_sid": call_id,  # Schema legacy usa call_sid
                "from_number": from_number,
                "to_number": to_number,
                "duration": duration_seconds,  # Schema legacy usa duration
                "status": call_status,  # Schema legacy usa status
                "transcript": full_transcript,  # Schema legacy usa transcript
                "reservation_created": reservation_created,
                "call_metadata": call_metadata,
                "created_at": datetime.now(get_mexico_timezone()).isoformat()
            }

            # Agregar reservation_id si existe
            if reservation_id:
                history_data["reservation_id"] = reservation_id

            # 🆕 Agregar client_id si existe (nueva columna)
            logger.info(f"[CALL-HISTORY-DEBUG] client_id recibido: {client_id}")

            if client_id:
                history_data["client_id"] = client_id
                logger.info(f"[CALL-HISTORY] 👤 Vinculando llamada con client_id: {client_id[:8]}...")
            else:
                logger.warning(f"[CALL-HISTORY] ⚠️ client_id es NULL, no se vinculará con cliente")

            logger.info(f"[CALL-HISTORY-DEBUG] history_data keys: {list(history_data.keys())}")
            logger.info(f"[CALL-HISTORY-DEBUG] client_id en history_data: {history_data.get('client_id')}")

            # Insertar en la base de datos
            if self.db:
                response = self.db.client.table("call_history").insert(history_data).execute()

                if response.data:
                    history_id = response.data[0]['id']
                    saved_client_id = response.data[0].get('client_id')
                    logger.info(f"[CALL-HISTORY] ✅ Historial guardado exitosamente: {history_id}")
                    logger.info(f"[CALL-HISTORY-DEBUG] ✅ client_id guardado en Supabase: {saved_client_id}")

                    # Log estadísticas de la conversación
                    stats = conversation_metadata.get("stats", {})
                    logger.info(f"[CALL-HISTORY] 📊 Estadísticas: {stats.get('total_words', 0)} palabras, "
                               f"{stats.get('total_messages', 0)} mensajes")

                    return history_id
                else:
                    logger.error(f"[CALL-HISTORY] ❌ Error: No se retornaron datos de la inserción")
                    return None
            else:
                logger.warning(f"[CALL-HISTORY] ⚠️ DB no disponible, simulando guardado exitoso")
                return f"mock_history_{call_id}"

        except Exception as e:
            logger.error(f"[CALL-HISTORY] ❌ Error guardando historial: {e}")
            return None

    def _analyze_conversation_metadata(self, full_transcript: str) -> Dict[str, Any]:
        """
        Analiza la transcripción para generar metadata rica SIN lógica hardcodeada.
        Solo estadísticas básicas, el análisis inteligente se hace en Post-AI.

        Args:
            full_transcript: Transcripción completa

        Returns:
            Dict con metadata de análisis básico
        """
        try:
            if not full_transcript:
                return {"stats": {"total_words": 0, "total_messages": 0, "error": "empty_transcript"}}

            # Estadísticas básicas (NO hardcodeadas)
            lines = [line.strip() for line in full_transcript.split('\n') if line.strip()]
            total_words = len(full_transcript.split())
            total_chars = len(full_transcript)

            # Separar mensajes de cliente vs asistente
            client_messages = [line for line in lines if line.startswith("Cliente:")]
            assistant_messages = [line for line in lines if line.startswith("Jessica:")]

            # Estadísticas de participación
            client_words = sum(len(msg.split()) for msg in client_messages)
            assistant_words = sum(len(msg.split()) for msg in assistant_messages)

            # Metadata básica sin interpretación
            metadata = {
                "stats": {
                    "total_words": total_words,
                    "total_characters": total_chars,
                    "total_messages": len(lines),
                    "client_messages": len(client_messages),
                    "assistant_messages": len(assistant_messages),
                    "client_words": client_words,
                    "assistant_words": assistant_words,
                    "conversation_balance": round(client_words / max(total_words, 1) * 100, 1)
                },
                "conversation_flow": {
                    "first_speaker": "Cliente" if lines and lines[0].startswith("Cliente:") else "Jessica",
                    "last_speaker": "Cliente" if lines and lines[-1].startswith("Cliente:") else "Jessica",
                    "turn_taking": len(lines)
                },
                "content_flags": {
                    "has_content": len(lines) > 0,
                    "substantial_conversation": total_words > 20,
                    "balanced_interaction": len(client_messages) > 1 and len(assistant_messages) > 1
                }
            }

            return metadata

        except Exception as e:
            logger.error(f"[CALL-HISTORY] Error analizando metadata: {e}")
            return {"stats": {"error": str(e)}}

    async def _get_tenant_context(self, tenant_id: str, branch_id: str) -> Dict[str, Any]:
        """
        Obtiene contexto del tenant y branch para metadata.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la branch

        Returns:
            Dict con información contextual
        """
        try:
            tenant_context = {"tenant_id": tenant_id, "branch_id": branch_id}

            if self.tenant_service and self.db:
                # Obtener información del tenant
                tenant_info = await self.db.get_tenant_by_id(tenant_id)
                if tenant_info:
                    tenant_context["tenant_name"] = tenant_info.get("name", "Unknown")
                    tenant_context["business_type"] = tenant_info.get("business_type", "service")

                # Obtener información de la branch
                branches = await self.db.get_branches(tenant_id)
                branch_info = next((b for b in branches if b['id'] == branch_id), None)
                if branch_info:
                    tenant_context["branch_name"] = branch_info.get("name", "Unknown")
                    tenant_context["branch_phone"] = branch_info.get("twilio_phone_number", "")

            return tenant_context

        except Exception as e:
            logger.error(f"[CALL-HISTORY] Error obteniendo contexto tenant: {e}")
            return {"tenant_id": tenant_id, "branch_id": branch_id, "error": str(e)}

    async def get_call_history_by_tenant(
        self,
        tenant_id: str,
        branch_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtiene historial de llamadas para un tenant específico.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de branch específica (opcional)
            limit: Número máximo de registros
            offset: Offset para paginación
            status_filter: Filtrar por status específico

        Returns:
            Dict con llamadas y estadísticas
        """
        try:
            if not self.db:
                return {"calls": [], "stats": {}, "error": "Database not available"}

            # Construir query base (adaptado al schema legacy)
            query = self.db.client.table("call_history").select(
                "id, call_sid, from_number, to_number, duration, status, "
                "reservation_created, call_metadata, created_at"
            ).eq("tenant_id", tenant_id)

            # Filtros opcionales
            if branch_id:
                query = query.eq("branch_id", branch_id)
            if status_filter:
                query = query.eq("status", status_filter)

            # Ejecutar query con paginación
            response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

            calls = response.data or []

            # Calcular estadísticas básicas
            stats = self._calculate_call_statistics(calls)

            return {
                "calls": calls,
                "stats": stats,
                "total_retrieved": len(calls),
                "pagination": {"limit": limit, "offset": offset}
            }

        except Exception as e:
            logger.error(f"[CALL-HISTORY] Error obteniendo historial: {e}")
            return {"calls": [], "stats": {}, "error": str(e)}

    def _calculate_call_statistics(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calcula estadísticas básicas de un conjunto de llamadas.

        Args:
            calls: Lista de llamadas

        Returns:
            Dict con estadísticas calculadas
        """
        try:
            if not calls:
                return {"total_calls": 0}

            total_calls = len(calls)
            completed_calls = len([c for c in calls if c.get("status") == "completed"])
            calls_with_reservations = len([c for c in calls if c.get("reservation_created") == True])

            # Duración total y promedio
            total_duration = sum(c.get("duration", 0) for c in calls)
            avg_duration = total_duration / total_calls if total_calls > 0 else 0

            # Tasas de conversión y éxito
            success_rate = (completed_calls / total_calls * 100) if total_calls > 0 else 0
            conversion_rate = (calls_with_reservations / total_calls * 100) if total_calls > 0 else 0

            return {
                "total_calls": total_calls,
                "completed_calls": completed_calls,
                "calls_with_reservations": calls_with_reservations,
                "total_duration_seconds": total_duration,
                "average_duration_seconds": round(avg_duration, 1),
                "success_rate_percentage": round(success_rate, 1),
                "conversion_rate_percentage": round(conversion_rate, 1)
            }

        except Exception as e:
            logger.error(f"[CALL-HISTORY] Error calculando estadísticas: {e}")
            return {"error": str(e)}

    async def get_call_by_id(self, call_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una llamada específica por ID.

        Args:
            call_id: ID de la llamada
            tenant_id: ID del tenant (para seguridad)

        Returns:
            Dict con datos de la llamada o None
        """
        try:
            if not self.db:
                return None

            response = self.db.client.table("call_history").select("*").eq(
                "call_sid", call_id
            ).eq("tenant_id", tenant_id).single().execute()

            return response.data if response.data else None

        except Exception as e:
            logger.error(f"[CALL-HISTORY] Error obteniendo llamada {call_id}: {e}")
            return None

    async def update_call_status(
        self,
        call_id: str,
        tenant_id: str,
        new_status: str,
        reservation_created: Optional[bool] = None,
        reservation_id: Optional[str] = None
    ) -> bool:
        """
        Actualiza el status de una llamada (útil para Post-AI analysis).

        Args:
            call_id: ID de la llamada
            tenant_id: ID del tenant
            new_status: Nuevo status
            reservation_created: Si se creó reserva
            reservation_id: ID de reserva creada

        Returns:
            True si se actualizó exitosamente
        """
        try:
            if not self.db:
                return False

            update_data = {
                "status": new_status,
                "updated_at": datetime.now(get_mexico_timezone()).isoformat()
            }

            if reservation_created is not None:
                update_data["reservation_created"] = reservation_created
            if reservation_id:
                update_data["reservation_id"] = reservation_id

            response = self.db.client.table("call_history").update(update_data).eq(
                "call_sid", call_id
            ).eq("tenant_id", tenant_id).execute()

            success = bool(response.data)
            if success:
                logger.info(f"[CALL-HISTORY] ✅ Status actualizado para {call_id}: {new_status}")

            return success

        except Exception as e:
            logger.error(f"[CALL-HISTORY] Error actualizando status: {e}")
            return False
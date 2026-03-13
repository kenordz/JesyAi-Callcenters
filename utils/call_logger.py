"""
Call Logger - Sistema de logging estructurado por llamada
Captura todos los logs durante una llamada y los estructura para guardar en DB
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


class CallLogger:
    """
    Manejador de logs por llamada individual
    Captura y estructura logs para debugging y monitoreo
    """

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.logs: List[Dict[str, Any]] = []
        self.start_time = datetime.now(ZoneInfo("America/Mexico_City"))

    def _add_log(
        self,
        level: str,
        category: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """Agregar log estructurado"""
        log_entry = {
            "timestamp": datetime.now(ZoneInfo("America/Mexico_City")).isoformat(),
            "level": level,
            "category": category,
            "message": message
        }

        if data:
            log_entry["data"] = data

        self.logs.append(log_entry)

        # También loggear a Google Cloud para debugging en tiempo real
        log_msg = f"[{self.call_id}] [{category}] {message}"
        if level == "INFO":
            logger.info(log_msg)
        elif level == "WARNING":
            logger.warning(log_msg)
        elif level == "ERROR":
            logger.error(log_msg)

    # ==================== WEBHOOK/SIP ====================

    def log_call_received(self, from_number: str, to_number: str, headers: Dict = None):
        """Llamada recibida en webhook"""
        self._add_log(
            "INFO",
            "webhook",
            "Llamada recibida",
            {
                "from_number": from_number,
                "to_number": to_number,
                "headers": headers or {}
            }
        )

    def log_tenant_detected(self, tenant_id: str, tenant_name: str, branch_id: str, branch_name: str):
        """Tenant y branch detectados"""
        self._add_log(
            "INFO",
            "webhook",
            "Tenant/Branch detectado",
            {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
                "branch_id": branch_id,
                "branch_name": branch_name
            }
        )

    # ==================== SESSION ====================

    def log_session_created(self, session_id: str, model: str):
        """Session creada con OpenAI"""
        self._add_log(
            "INFO",
            "session",
            "Session creada con OpenAI Realtime",
            {
                "session_id": session_id,
                "model": model
            }
        )

    def log_tools_sent(self, tools_count: int):
        """Tools enviadas a OpenAI"""
        self._add_log(
            "INFO",
            "session",
            f"{tools_count} tools enviadas a OpenAI"
        )

    def log_instructions_sent(self, instructions_length: int):
        """Instructions enviadas"""
        self._add_log(
            "INFO",
            "session",
            f"Instructions enviadas ({instructions_length} chars)"
        )

    # ==================== FUNCTION CALLS ====================

    def log_function_call_received(self, function_name: str, arguments: Dict):
        """Function call recibido de OpenAI"""
        self._add_log(
            "INFO",
            "function_call",
            f"Function call recibido: {function_name}",
            {
                "function": function_name,
                "arguments": arguments
            }
        )

    def log_function_validation(self, function_name: str, valid: bool, errors: List[str] = None):
        """Validación de argumentos de función"""
        level = "INFO" if valid else "WARNING"
        self._add_log(
            level,
            "function_call",
            f"Validación de {function_name}: {'✅ OK' if valid else '❌ FAILED'}",
            {
                "function": function_name,
                "valid": valid,
                "errors": errors or []
            }
        )

    def log_function_executing(self, function_name: str):
        """Ejecutando función"""
        self._add_log(
            "INFO",
            "function_call",
            f"Ejecutando {function_name}..."
        )

    def log_function_result(self, function_name: str, result: Any, success: bool = True):
        """Resultado de función"""
        level = "INFO" if success else "ERROR"
        self._add_log(
            level,
            "function_call",
            f"Resultado de {function_name}: {'✅ Success' if success else '❌ Error'}",
            {
                "function": function_name,
                "result": result,
                "success": success
            }
        )

    # ==================== AVAILABILITY ====================

    def log_availability_check(self, barber_name: str, date: str):
        """Verificando disponibilidad"""
        self._add_log(
            "INFO",
            "availability",
            f"Verificando disponibilidad: {barber_name} - {date}"
        )

    def log_slots_found(self, barber_name: str, total_slots: int, available_slots: int):
        """Slots encontrados"""
        self._add_log(
            "INFO",
            "availability",
            f"Slots encontrados para {barber_name}",
            {
                "barber": barber_name,
                "total_slots": total_slots,
                "available_slots": available_slots,
                "occupied_slots": total_slots - available_slots
            }
        )

    # ==================== TRANSCRIPTION ====================

    def log_transcription(self, speaker: str, text: str):
        """Transcripción capturada"""
        self._add_log(
            "INFO",
            "transcription",
            f"{speaker}: {text[:100]}..." if len(text) > 100 else f"{speaker}: {text}"
        )

    # ==================== POST-CALL ====================

    def log_call_ended(self, duration: int):
        """Llamada terminada"""
        self._add_log(
            "INFO",
            "call_control",
            f"Llamada terminada (duración: {duration}s)",
            {
                "duration_seconds": duration
            }
        )

    def log_post_analysis_start(self):
        """Iniciando análisis post-llamada"""
        self._add_log(
            "INFO",
            "post_call",
            "Iniciando análisis post-llamada con GPT-4o-mini"
        )

    def log_post_analysis_result(self, intent: str, confidence: float, should_create: bool):
        """Resultado de análisis"""
        self._add_log(
            "INFO",
            "post_call",
            f"Análisis completado: {intent} (confianza: {confidence})",
            {
                "intent": intent,
                "confidence": confidence,
                "should_create_reservation": should_create
            }
        )

    def log_reservation_created(self, reservation_id: str, client_name: str, barber: str, date: str, time: str):
        """Reserva creada automáticamente"""
        self._add_log(
            "INFO",
            "post_call",
            f"✅ Reserva creada: {client_name} con {barber}",
            {
                "reservation_id": reservation_id,
                "client_name": client_name,
                "barber": barber,
                "date": date,
                "time": time
            }
        )

    def log_reservation_not_created(self, reason: str):
        """Reserva NO creada"""
        self._add_log(
            "WARNING",
            "post_call",
            f"❌ Reserva NO creada: {reason}",
            {
                "reason": reason
            }
        )

    # ==================== ERRORS ====================

    def log_error(self, category: str, message: str, error: Exception = None, data: Dict = None):
        """Error durante la llamada"""
        error_data = data or {}
        if error:
            error_data["error_type"] = type(error).__name__
            error_data["error_message"] = str(error)

        self._add_log(
            "ERROR",
            category,
            f"❌ ERROR: {message}",
            error_data
        )

    def log_warning(self, category: str, message: str, data: Dict = None):
        """Warning durante la llamada"""
        self._add_log(
            "WARNING",
            category,
            f"⚠️ WARNING: {message}",
            data
        )

    # ==================== DATABASE ====================

    def log_db_save(self, table: str, record_id: str = None):
        """Guardado en base de datos"""
        self._add_log(
            "INFO",
            "database",
            f"Guardado en {table}",
            {
                "table": table,
                "record_id": record_id
            }
        )

    # ==================== EXPORT ====================

    def get_logs(self) -> List[Dict[str, Any]]:
        """Obtener todos los logs capturados"""
        return self.logs

    def get_summary(self) -> Dict[str, Any]:
        """Resumen de logs"""
        total_logs = len(self.logs)
        by_level = {}
        by_category = {}

        for log in self.logs:
            level = log["level"]
            category = log["category"]

            by_level[level] = by_level.get(level, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1

        return {
            "total_logs": total_logs,
            "by_level": by_level,
            "by_category": by_category,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now(ZoneInfo("America/Mexico_City")).isoformat()
        }

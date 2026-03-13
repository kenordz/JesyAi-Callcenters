"""
Log Helper - Agregar call_id a todos los logs
Solución simple para separar logs por llamada
"""
import logging

# Logger para este módulo
logger = logging.getLogger(__name__)

def format_log_with_call_id(call_id: str, message: str) -> str:
    """
    Agrega call_id al inicio de un mensaje de log.

    Uso:
        logger.info(format_log_with_call_id(call_id, "[FUNCTION-CALL] Ejecutando función..."))

    Output en logs:
        [abc-123] [FUNCTION-CALL] Ejecutando función...
    """
    # Formatear call_id corto (primeros 8 caracteres para legibilidad)
    short_id = get_short_call_id(call_id)

    # Construir mensaje con call_id al inicio
    return f"[{short_id}] {message}"


def get_short_call_id(call_id: str) -> str:
    """
    Obtiene versión corta del call_id para logs.

    Ejemplo:
        "abc-def-123-456-789" → "abc-def-"
        None → "NO-ID"
    """
    if not call_id:
        return "NO-ID"
    return call_id[:8] if len(call_id) > 8 else call_id

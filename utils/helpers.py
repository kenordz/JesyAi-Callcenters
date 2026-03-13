"""
Helper utilities for JesyAI SIP Realtime
Migrado desde utils.py con funciones de utilidad limpias y reutilizables
"""

import os
import re
import time
import string
import tempfile
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def format_phone_number(phone: str, country_code: str = "+52") -> str:
    """
    Formatear número de teléfono de manera consistente.

    Args:
        phone: Número de teléfono en cualquier formato
        country_code: Código de país por defecto

    Returns:
        Número formateado (+52XXXXXXXXXX)
    """
    if not phone:
        return ""

    # Limpiar el número (solo dígitos)
    clean_phone = re.sub(r'[^\d]', '', phone)

    # Si ya tiene código de país, devolverlo formateado
    if clean_phone.startswith('52') and len(clean_phone) == 12:
        return f"+{clean_phone}"
    elif clean_phone.startswith('1') and len(clean_phone) == 11:  # US numbers
        return f"+{clean_phone}"
    elif len(clean_phone) == 10:  # Mexican number without country code
        return f"{country_code}{clean_phone}"

    return phone  # Return as-is if format is unclear


def validate_time_slot(time_str: str) -> bool:
    """
    Validar que un horario esté en formato válido.

    Args:
        time_str: Horario en formato "HH:MM"

    Returns:
        True si es válido, False si no
    """
    try:
        time_pattern = re.compile(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
        if not time_pattern.match(time_str):
            return False

        # Verificar que la hora esté en un rango lógico (6:00 AM - 11:00 PM)
        hour, minute = map(int, time_str.split(':'))
        return 6 <= hour <= 23

    except (ValueError, AttributeError):
        return False


def get_mexico_timezone() -> ZoneInfo:
    """Obtener zona horaria de México."""
    return ZoneInfo('America/Mexico_City')


def get_current_time_mexico() -> datetime:
    """Obtener hora actual en zona horaria de México."""
    return datetime.now(get_mexico_timezone())


def split_text(text: str, max_length: int = 1000) -> List[str]:
    """
    Dividir texto en fragmentos de tamaño máximo especificado.
    Intenta mantener palabras completas.

    Args:
        text: Texto a dividir
        max_length: Longitud máxima por fragmento

    Returns:
        Lista de fragmentos de texto
    """
    if not text or len(text) <= max_length:
        return [text] if text else []

    words = text.split()
    chunks = []
    current_chunk = ""

    for word in words:
        # Si agregar esta palabra excede el límite
        if len(current_chunk) + len(word) + 1 > max_length:
            if current_chunk:  # Si hay contenido en el chunk actual
                chunks.append(current_chunk.strip())
                current_chunk = word
            else:  # Si una sola palabra es muy larga, cortarla
                chunks.append(word[:max_length])
                current_chunk = word[max_length:] if len(word) > max_length else ""
        else:
            current_chunk += (" " + word) if current_chunk else word

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def is_irrelevant_transcript(transcript: str) -> bool:
    """
    Determinar si un transcript es irrelevante (muletillas, agradecimientos vacíos, etc.).

    Args:
        transcript: Texto de la transcripción

    Returns:
        True si es irrelevante, False si no
    """
    if not transcript or len(transcript.strip()) == 0:
        return True

    # Normalizar texto
    norm = transcript.strip().lower()
    norm = norm.translate(str.maketrans('', '', string.punctuation))
    norm = " ".join(norm.split())  # Normalizar espacios

    # Palabras/frases irrelevantes comunes
    irrelevant_patterns = [
        # Inglés
        "thank you", "ok", "great", "alright", "cool", "uh-huh",
        "i'll wait", "i see", "um", "hmm", "thanks", "okay", "uh huh",
        "yeah", "yes", "no", "right", "sure", "fine",

        # Español
        "gracias", "ok", "bueno", "bien", "claro", "sí", "no",
        "ajá", "eh", "este", "pues", "mmm", "ah", "oh",
        "perfecto", "está bien", "muy bien", "de acuerdo",

        # Sonidos/ruido
        "...", "ahhh", "eeeh", "mmhmm", "mhm"
    ]

    return norm in irrelevant_patterns or len(norm) < 3


def is_farewell_transcript(transcript: str) -> bool:
    """
    Determinar si un transcript es una despedida.

    Args:
        transcript: Texto de la transcripción

    Returns:
        True si es despedida, False si no
    """
    if not transcript:
        return False

    norm = transcript.strip().lower()
    norm = norm.translate(str.maketrans('', '', string.punctuation))
    norm = " ".join(norm.split())

    farewell_patterns = [
        # Inglés
        "goodbye", "bye", "see you", "thank you very much", "thats all i needed",
        "have a good day", "talk to you later", "bye bye", "see you later",

        # Español
        "adiós", "hasta luego", "nos vemos", "muchas gracias", "eso es todo",
        "que tengas buen día", "hasta la vista", "chao", "bye", "nos hablamos",
        "gracias por todo", "perfecto gracias", "listo gracias"
    ]

    return any(pattern in norm for pattern in farewell_patterns)


def extract_client_name_from_text(text: str, exclude_barbers: List[str] = None) -> Optional[str]:
    """
    Extraer nombre de cliente del texto usando patrones comunes.

    Args:
        text: Texto donde buscar el nombre
        exclude_barbers: Lista de nombres de barberos para excluir

    Returns:
        Nombre extraído o None si no se encuentra
    """
    if not text:
        return None

    # Normalizar texto
    text_normalized = " ".join(text.split()).lower()

    # Barberos por defecto a excluir
    if exclude_barbers is None:
        exclude_barbers = ['brandon', 'javi', 'eder', 'paco', 'poncho']

    exclude_barbers_lower = [name.lower() for name in exclude_barbers]

    # Patrones para extraer nombres
    patterns = [
        # Patrones explícitos de presentación (prioridad alta)
        r'mi nombre es ([a-zA-ZáéíóúÁÉÍÓÚñÑ ]+?)(?:\s+para|\s+el|\s+a\s|\s+y\s|[.,!?]|$)',
        r'me llamo ([a-zA-ZáéíóúÁÉÍÓÚñÑ ]+?)(?:\s+para|\s+el|\s+a\s|\s+y\s|[.,!?]|$)',
        r'soy ([a-zA-ZáéíóúÁÉÍÓÚñÑ ]+?)(?:\s+para|\s+el|\s+a\s|\s+y\s|[.,!?]|$)',

        # Patrón "a nombre de"
        r'a\s?nombre\s?de\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ]+(?:\s+[a-zA-ZáéíóúÁÉÍÓÚñÑ]+)*?)(?=\s+(?:para|el|a\s|mañana|lunes|martes|miércoles|jueves|viernes|sábado|domingo)|[.,!?]|$)',

        # Patrón "para [nombre]" (solo nombres que empiecen con mayúscula)
        r'para\s+([A-Z][a-záéíóúñ]+(?:\s+[A-Z][a-záéíóúñ]+)*)(?:\s+el|\s+a\s|\s+mañana|\s+lunes|\s+martes|\s+miércoles|\s+jueves|\s+viernes|\s+sábado|\s+domingo|[.,!?]|$)',

        # Patrón "con [nombre]" (cuidado, puede ser barbero)
        r'con\s+([A-Z][a-záéíóúñ]+(?:\s+[A-Z][a-záéíóúñ]+)*)(?:\s+el|\s+a\s|\s+para|[.,!?]|$)',
    ]

    # Palabras comunes que no son nombres
    common_words = [
        'el', 'la', 'de', 'del', 'y', 'con', 'para', 'por', 'que', 'es', 'son', 'está', 'están',
        'mañana', 'hoy', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo',
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
        'octubre', 'noviembre', 'diciembre'
    ]

    for pattern in patterns:
        match = re.search(pattern, text_normalized)
        if match:
            try:
                name = match.group(1).strip()

                # Limpiar nombre (quitar palabras comunes)
                name = re.sub(r'\b(el|la|de|del|y|con|para|por|que|es|son|está|están)\b', '', name, flags=re.IGNORECASE)
                name = ' '.join(name.split())  # Normalizar espacios
                name_lower = name.lower()

                # Verificar que sea un nombre válido
                if (len(name) > 1 and
                    name_lower not in common_words and
                    name_lower not in exclude_barbers_lower):
                    return name.title()

            except Exception as e:
                logger.warning(f"Error procesando nombre con patrón {pattern}: {e}")
                continue

    return None


def normalize_date_string(date_str: str) -> Optional[str]:
    """
    Normalizar string de fecha a formato ISO (YYYY-MM-DD).

    Args:
        date_str: Fecha en formato natural

    Returns:
        Fecha en formato ISO o None si no se puede parsear
    """
    if not date_str:
        return None

    date_lower = date_str.lower().strip()
    now = get_current_time_mexico()

    # Fechas relativas
    if date_lower in ["hoy", "today"]:
        return now.strftime("%Y-%m-%d")
    elif date_lower in ["mañana", "tomorrow"]:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_lower in ["pasado mañana", "day after tomorrow"]:
        return (now + timedelta(days=2)).strftime("%Y-%m-%d")

    # Intentar parsear como fecha ISO
    try:
        parsed_date = datetime.fromisoformat(date_str)
        return parsed_date.strftime("%Y-%m-%d")
    except:
        pass

    # Intentar otros formatos comunes
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"]
    for fmt in formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime("%Y-%m-%d")
        except:
            continue

    return None


def normalize_time_string(time_str: str) -> Optional[str]:
    """
    Normalizar string de tiempo a formato HH:MM.

    Args:
        time_str: Tiempo en formato natural

    Returns:
        Tiempo en formato HH:MM o None si no se puede parsear
    """
    if not time_str:
        return None

    time_lower = time_str.lower().strip()

    # Casos especiales
    special_times = {
        "mediodía": "12:00",
        "medianoche": "00:00",
        "noon": "12:00",
        "midnight": "00:00"
    }

    if time_lower in special_times:
        return special_times[time_lower]

    # Formato "X y media" o "X:30"
    if "media" in time_lower or "y media" in time_lower:
        hour_part = re.sub(r'(y\s+)?media', '', time_lower).strip()
        try:
            base_hour = int(hour_part)
            return f"{base_hour:02d}:30"
        except:
            pass

    # Formato AM/PM
    am_pm_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)'
    match = re.search(am_pm_pattern, time_lower)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        is_pm = match.group(3) == 'pm'

        # Convertir a formato 24h
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute:02d}"

    # Formato 24h directo
    time_pattern = r'^(\d{1,2}):(\d{2})$'
    match = re.search(time_pattern, time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    # Solo hora
    try:
        hour = int(time_str.strip())
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
    except:
        pass

    return None


def format_time_spanish(time_str: str) -> str:
    """
    Formatear hora en español legible.

    Args:
        time_str: Hora en formato HH:MM

    Returns:
        Hora formateada en español
    """
    try:
        hour, minute = map(int, time_str.split(':'))

        if hour == 0:
            return f"12:{minute:02d} de la madrugada"
        elif hour < 12:
            return f"{hour}:{minute:02d} de la mañana"
        elif hour == 12:
            return f"12:{minute:02d} del mediodía"
        elif hour < 19:
            hour_12 = hour - 12
            return f"{hour_12}:{minute:02d} de la tarde"
        else:
            hour_12 = hour - 12
            return f"{hour_12}:{minute:02d} de la noche"

    except Exception as e:
        logger.error(f"Error formateando tiempo {time_str}: {e}")
        return time_str


def generate_confirmation_code(length: int = 6) -> str:
    """
    Generar código de confirmación aleatorio.

    Args:
        length: Longitud del código

    Returns:
        Código de confirmación
    """
    import random
    import string

    # Usar solo números y letras mayúsculas (evitar confusión)
    chars = string.digits + 'ABCDEFGHJKLMNPQRSTUVWXYZ'  # Sin I, O para evitar confusión
    return ''.join(random.choice(chars) for _ in range(length))


def sanitize_filename(filename: str) -> str:
    """
    Sanitizar nombre de archivo removiendo caracteres problemáticos.

    Args:
        filename: Nombre original del archivo

    Returns:
        Nombre sanitizado
    """
    # Remover caracteres problemáticos
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)

    # Limitar longitud
    if len(sanitized) > 200:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:200-len(ext)] + ext

    return sanitized


def calculate_duration_minutes(start_time: str, end_time: str) -> int:
    """
    Calcular duración en minutos entre dos horarios.

    Args:
        start_time: Hora de inicio (HH:MM)
        end_time: Hora de fin (HH:MM)

    Returns:
        Duración en minutos
    """
    try:
        from datetime import datetime, timedelta

        start = datetime.strptime(start_time, "%H:%M")
        end = datetime.strptime(end_time, "%H:%M")

        # Manejar caso donde end_time es al día siguiente
        if end < start:
            end += timedelta(days=1)

        duration = end - start
        return int(duration.total_seconds() / 60)

    except Exception as e:
        logger.error(f"Error calculando duración: {e}")
        return 30  # Default 30 minutos


def mask_phone_number(phone: str) -> str:
    """
    Enmascarar número de teléfono para logs/privacy.

    Args:
        phone: Número completo

    Returns:
        Número enmascarado
    """
    if not phone or len(phone) < 4:
        return "***"

    return phone[:2] + "*" * (len(phone) - 4) + phone[-2:]


def mask_email(email: str) -> str:
    """
    Enmascarar email para logs/privacy.

    Args:
        email: Email completo

    Returns:
        Email enmascarado
    """
    if not email or '@' not in email:
        return "***@***"

    local, domain = email.split('@', 1)

    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]

    domain_parts = domain.split('.')
    if len(domain_parts[0]) <= 2:
        masked_domain = "*" * len(domain_parts[0])
    else:
        masked_domain = domain_parts[0][0] + "*" * (len(domain_parts[0]) - 2) + domain_parts[0][-1]

    return f"{masked_local}@{masked_domain}.{'.'.join(domain_parts[1:])}"


def is_business_hours(check_time: Optional[datetime] = None) -> bool:
    """
    Verificar si es horario de negocio.

    Args:
        check_time: Tiempo a verificar (por defecto: ahora)

    Returns:
        True si es horario de negocio
    """
    if check_time is None:
        check_time = get_current_time_mexico()

    # Horario de negocio: Lunes a Sábado, 9:00 AM - 7:00 PM
    weekday = check_time.weekday()  # 0 = Monday, 6 = Sunday
    hour = check_time.hour

    # Domingo cerrado
    if weekday == 6:
        return False

    # Verificar horario (9 AM - 7 PM)
    return 9 <= hour < 19


def get_next_business_day(from_date: Optional[datetime] = None) -> datetime:
    """
    Obtener el próximo día hábil.

    Args:
        from_date: Fecha desde la cual calcular (por defecto: hoy)

    Returns:
        Próximo día hábil
    """
    if from_date is None:
        from_date = get_current_time_mexico()

    next_day = from_date + timedelta(days=1)

    # Si es domingo, pasar a lunes
    while next_day.weekday() == 6:  # 6 = Sunday
        next_day += timedelta(days=1)

    return next_day


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncar texto a longitud máxima con sufijo.

    Args:
        text: Texto a truncar
        max_length: Longitud máxima
        suffix: Sufijo para texto truncado

    Returns:
        Texto truncado
    """
    if not text or len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)].strip() + suffix


def safe_get(dictionary: Dict, key: str, default: Any = None, expected_type: type = None) -> Any:
    """
    Obtener valor de diccionario de forma segura con validación de tipo.

    Args:
        dictionary: Diccionario fuente
        key: Clave a obtener
        default: Valor por defecto
        expected_type: Tipo esperado (opcional)

    Returns:
        Valor obtenido o valor por defecto
    """
    if not isinstance(dictionary, dict):
        return default

    value = dictionary.get(key, default)

    if expected_type and value is not None and not isinstance(value, expected_type):
        logger.warning(f"Valor {value} para clave {key} no es del tipo esperado {expected_type}")
        return default

    return value
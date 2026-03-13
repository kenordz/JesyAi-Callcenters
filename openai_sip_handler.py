"""
OpenAI SIP Handler - Call Center Edition
Maneja llamadas entrantes via OpenAI Realtime API con SIP (sin lógica de barbershop/restaurante)
"""

import os
import json
import asyncio
import requests
import logging
import time
import hashlib
import websockets
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from openai import OpenAI
from config import Config

# Configurar logging
logger = logging.getLogger(__name__)

# Import servicios OOP
from core.database import DatabaseManager
from services.tenant_service import TenantService
from services.ai_actions_service import AIActionsService
from services.transcription_service import TranscriptionService
from services.call_history_service import CallHistoryService
from services.function_call_handler_service import FunctionCallHandlerService
from services.tenant_validation_service import TenantValidationService
from services.post_ai_call_service import PostAICallService
from services.client_service import ClientService
from services.whatsapp_service import WhatsAppService

# Import call center tools and instructions
from core.callcenter_instructions import get_callcenter_instructions
from core.callcenter_function_definitions import get_callcenter_tools
from services.vicidial_service import VicidialService

# Import helpers
from core.base_instructions import get_base_instructions
from utils.helpers import (
    format_phone_number,
    get_mexico_timezone,
    extract_client_name_from_text,
    normalize_date_string,
    normalize_time_string,
    format_time_spanish
)
from utils.call_logger import CallLogger


class OpenAISIPHandler:
    def __init__(self):
        self.openai_client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", "")
        )
        self.webhook_secret = os.environ.get("OPENAI_WEBHOOK_SECRET", "")
        self.auth_header = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
        }

        # PROJECT_ID para el SIP endpoint
        self.project_id = Config.OPENAI_PROJECT_ID

        # Initialize OOP services
        self.db = DatabaseManager()
        self.tenant_service = TenantService(database_manager=self.db)
        self.ai_actions_service = AIActionsService(
            database_manager=self.db,
            tenant_service=self.tenant_service
        )
        self.transcription_service = TranscriptionService()
        self.call_history_service = CallHistoryService(
            database_manager=self.db,
            tenant_service=self.tenant_service
        )

        # Vicidial service para call center operations
        self.vicidial_service = VicidialService(database_manager=self.db)

        # Client service para tracking de clientes recurrentes
        self.client_service = ClientService(database_manager=self.db)

        # Function call handler centralizado (now call center only)
        self.function_call_handler = FunctionCallHandlerService(
            database_manager=self.db,
            tenant_service=self.tenant_service,
            vicidial_service=self.vicidial_service,
            client_service=self.client_service
        )

        # Tenant validation service
        self.tenant_validation_service = TenantValidationService(
            database_manager=self.db
        )

        # WhatsApp service para confirmaciones y recordatorios
        self.whatsapp_service = WhatsAppService(db_manager=self.db)

        # Post AI Call service (debe ir DESPUÉS de client_service y whatsapp_service)
        self.post_ai_call_service = PostAICallService(
            database_manager=self.db,
            transcription_service=self.transcription_service,
            call_history_service=self.call_history_service,
            vicidial_service=self.vicidial_service
        )

        # Almacenar metadata de llamadas activas
        self.active_calls = {}

        # Diccionarios persistentes (no se limpian hasta el final)
        self.call_phone_numbers = {}  # {call_id: phone_number}
        self.call_start_times = {}  # {call_id: datetime}
        self.call_timezones = {}  # {call_id: timezone}
        self.call_ai_configs = {}  # {call_id: ai_config}
        self.call_loggers = {}  # {call_id: CallLogger}

        # Deduplicación por origen y tiempo para evitar múltiples llamadas
        self.recent_calls = {}  # {numero_origen: {"timestamp": timestamp, "call_id": call_id}}

        # Deduplicación de function calls para evitar ejecuciones duplicadas
        self.processed_function_calls = {}  # {call_id_from_event: timestamp}

        logger.info("[SIP-HANDLER] Servicios OOP inicializados exitosamente")

    async def get_call_accept_config(self, tenant_id: str, branch_id: str, from_number: str = None) -> Dict[str, Any]:
        """
        Genera configuración para aceptar llamada con instructions + herramientas call center.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la branch
            from_number: Número del cliente (para consultar historial)
        """
        try:
            # Consultar cliente antes de generar instructions
            client_info = None
            client_context = ""
            pending_client_info = None
            pending_client_phone = None

            if from_number:
                try:
                    logger.info(f"[CLIENT-CONTEXT] Consultando info de cliente: {from_number}")
                    client_info = await self.client_service.get_client_by_phone(
                        tenant_id=tenant_id,
                        branch_id=branch_id,
                        phone=from_number
                    )
                    pending_client_info = client_info
                    pending_client_phone = from_number

                    if client_info:
                        logger.info(f"[CLIENT-CONTEXT] Cliente encontrado: {client_info.get('name', 'Sin nombre')}")
                    else:
                        logger.info(f"[CLIENT-CONTEXT] Cliente nuevo detectado")

                except Exception as client_error:
                    logger.warning(f"[CLIENT-CONTEXT] Error consultando cliente: {client_error}")

            # OBTENER CONFIGURACIÓN DEL TENANT
            if branch_id and self.tenant_service:
                try:
                    branch_ai_config = await self.tenant_service.get_branch_ai_config(branch_id)

                    # Extraer campos del ai_config
                    instructions = branch_ai_config.get('instructions', '') or branch_ai_config.get('system_prompt', '')
                    greeting = branch_ai_config.get('greeting', '¡Hola! ¿En qué puedo ayudarte?')
                    voice = branch_ai_config.get('voice', 'sage')
                    assistant_name = branch_ai_config.get('assistant_name', 'Asistente Virtual')
                    business_name = branch_ai_config.get('business_name', 'Centro de Llamadas')

                    # Generar CORE PROMPT base
                    core_prompt = get_base_instructions(
                        assistant_name=assistant_name,
                        business_name=business_name,
                        language=branch_ai_config.get('language', 'es-MX')
                    )
                    logger.info(f"[ACCEPT-CONFIG] CORE PROMPT generado: {len(core_prompt)} caracteres")

                    # Generar client context si aplica
                    if pending_client_info or pending_client_phone:
                        client_context = self.client_service.build_client_context_for_instructions(
                            client_info=pending_client_info,
                            phone=pending_client_phone,
                            greeting=greeting
                        )
                        logger.info(f"[CLIENT-CONTEXT] Contexto generado: {len(client_context)} chars")

                    # Combinar: CORE + CALLCENTER + CUSTOM RULES + CLIENT_CONTEXT
                    callcenter_instructions = get_callcenter_instructions(
                        business_name=business_name,
                        assistant_name=assistant_name,
                        greeting=greeting
                    )

                    # Agregar custom rules si las hay
                    custom_rules = ""
                    if instructions:
                        custom_rules = f"""
# ═══════════════════════════════════════════════════════════════
# CUSTOM BUSINESS RULES (from Supabase)
# ═══════════════════════════════════════════════════════════════

{instructions}
"""

                    instructions = f"""{core_prompt}

# ═══════════════════════════════════════════════════════════════
# CALL CENTER INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════

{callcenter_instructions}
{custom_rules}
{client_context}"""

                    logger.info(f"[ACCEPT-CONFIG] Instructions completas: {len(instructions)} caracteres")

                except Exception as e:
                    logger.warning(f"[ACCEPT-CONFIG] Error obteniendo instructions: {e}")
                    assistant_name = 'Asistente Virtual'
                    business_name = 'Centro de Llamadas'
                    voice = 'sage'

                    core_prompt = get_base_instructions(
                        assistant_name=assistant_name,
                        business_name=business_name,
                        language="es-MX"
                    )
                    instructions = f"""{core_prompt}

# FALLBACK MODE
Eres {assistant_name} de {business_name}. Ayuda a los clientes con información."""

            else:
                logger.warning("[ACCEPT-CONFIG] No hay tenant_service, usando instructions genéricas")
                voice = 'sage'
                core_prompt = get_base_instructions(
                    assistant_name="Asistente Virtual",
                    business_name="Centro de Llamadas",
                    language="es-MX"
                )
                instructions = f"""{core_prompt}

# GENERIC FALLBACK MODE
Ayuda a los clientes con información general."""

            # Obtener tools de call center
            active_tools = get_callcenter_tools()
            logger.info(f"[ACCEPT-CONFIG] Tools de call center: {len(active_tools)} tools")

            # Configuración de transcripción
            transcription_config = {
                "model": "whisper-1",
                "language": "es"
            }

            call_accept_config = {
                "type": "realtime",
                "instructions": instructions,
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "tools": active_tools,
                "audio": {
                    "input": {
                        "transcription": transcription_config
                    },
                    "output": {
                        "voice": voice
                    }
                }
            }

            logger.info(f"[ACCEPT-CONFIG] Config lista - {len(instructions)} chars, {len(active_tools)} tools")
            return call_accept_config

        except Exception as e:
            logger.error(f"[ACCEPT-CONFIG] Error generando configuración: {e}")
            # Fallback genérico
            return {
                "type": "realtime",
                "instructions": """Eres un asistente virtual de call center. Saluda profesionalmente y ayuda a los clientes.""",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "tools": get_callcenter_tools(),
                "audio": {
                    "input": {
                        "transcription": {
                            "model": "whisper-1",
                            "language": "es"
                        }
                    },
                    "output": {
                        "voice": "sage"
                    }
                }
            }

    async def handle_function_call(self, event_data: Dict[str, Any], websocket, call_id: str, tenant_id: str, branch_id: str):
        """
        Maneja function calls usando el FunctionCallHandlerService centralizado.
        """
        try:
            function_name = event_data.get("name")
            call_id_from_event = event_data.get("call_id")
            arguments_str = event_data.get("arguments", "{}")

            # Deduplicación: Evitar ejecutar la misma function call dos veces
            current_time = time.time()

            # Limpiar call_ids antiguos (más de 10 segundos)
            self.processed_function_calls = {
                cid: ts for cid, ts in self.processed_function_calls.items()
                if current_time - ts < 10
            }

            # Parsear argumentos
            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError as e:
                logger.warning(f"[FUNCTION-CALL] JSON truncado detectado: {e}")
                repaired_str = self._repair_truncated_json(arguments_str)
                try:
                    arguments = json.loads(repaired_str)
                except json.JSONDecodeError:
                    logger.error(f"[FUNCTION-CALL] No se pudo reparar JSON")
                    arguments = {}

            # Crear hash único basado en función + argumentos
            content_key = f"{function_name}:{json.dumps(arguments, sort_keys=True)}"
            content_hash = hashlib.md5(content_key.encode()).hexdigest()

            logger.info(f"[FUNCTION-CALL] Función: {function_name}")
            logger.info(f"[FUNCTION-CALL] Argumentos: {arguments}")

            # Verificar duplicación
            if call_id_from_event in self.processed_function_calls:
                logger.warning(f"[FUNCTION-CALL] Ignorando duplicado por call_id: {function_name}")
                return

            if content_hash in self.processed_function_calls:
                logger.warning(f"[FUNCTION-CALL] Ignorando duplicado por contenido: {function_name}")
                return

            # Marcar como procesado
            self.processed_function_calls[call_id_from_event] = current_time
            self.processed_function_calls[content_hash] = current_time

            # Log function call recibido
            if call_id in self.call_loggers:
                self.call_loggers[call_id].log_function_call_received(
                    function_name=function_name,
                    arguments=arguments
                )

            # Obtener teléfono del cliente
            caller_phone = self.call_phone_numbers.get(call_id, "unknown")
            branch_timezone = self.call_timezones.get(call_id, "America/Mexico_City")

            logger.info(f"[FUNCTION-CALL] Teléfono del cliente: {caller_phone}")
            logger.info(f"[FUNCTION-CALL] Timezone: {branch_timezone}")

            # Preparar contexto para el handler
            context = {
                "call_id": call_id,
                "tenant_id": tenant_id,
                "branch_id": branch_id,
                "from_event_call_id": call_id_from_event,
                "phone": caller_phone,
                "timezone": branch_timezone
            }

            # Log: Ejecutando función
            if call_id in self.call_loggers:
                self.call_loggers[call_id].log_function_executing(function_name)

            # Usar FunctionCallHandlerService (call center)
            logger.info(f"[FUNCTION-CALL] Usando FunctionCallHandlerService para {function_name}")
            result = await self.function_call_handler.handle_function_call(
                function_name=function_name,
                arguments=arguments,
                context=context
            )

            # Log: Resultado de función
            if call_id in self.call_loggers:
                success = result.get("status") != "error"
                self.call_loggers[call_id].log_function_result(
                    function_name=function_name,
                    result=result,
                    success=success
                )

            # Enviar resultado de vuelta a OpenAI
            function_response = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id_from_event,
                    "output": json.dumps(result)
                }
            }

            logger.info(f"[FUNCTION-CALL] Enviando resultado: {result.get('message', 'Sin mensaje')}")
            await websocket.send(json.dumps(function_response))

            # Trigger response generation
            response_trigger = {
                "type": "response.create"
            }
            await websocket.send(json.dumps(response_trigger))

        except Exception as e:
            logger.error(f"[FUNCTION-CALL] Error general: {e}")
            try:
                call_id_from_event = event_data.get("call_id", "unknown")
                error_response = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id_from_event,
                        "output": json.dumps({
                            "status": "error",
                            "message": "Error ejecutando función. Intenta de nuevo."
                        })
                    }
                }
                await websocket.send(json.dumps(error_response))
            except Exception as send_error:
                logger.error(f"[FUNCTION-CALL] Error enviando error response: {send_error}")

    def _repair_truncated_json(self, json_str: str) -> str:
        """Repara JSON truncado agregando corchetes cerrados."""
        try:
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            open_brackets = json_str.count('[')
            close_brackets = json_str.count(']')

            repair = json_str
            repair += '}' * (open_braces - close_braces)
            repair += ']' * (open_brackets - close_brackets)
            return repair
        except Exception as e:
            logger.warning(f"[JSON-REPAIR] Error reparando JSON: {e}")
            return json_str

    async def process_realtime_event(self, event_data: Dict[str, Any], websocket, call_id: str, tenant_id: str, branch_id: str):
        """
        Procesa eventos en tiempo real del WebSocket de OpenAI.
        """
        try:
            event_type = event_data.get("type", "unknown")

            if event_type == "response.function_call_arguments.done":
                # Function call completado
                await self.handle_function_call(
                    event_data.get("delta", {}),
                    websocket,
                    call_id,
                    tenant_id,
                    branch_id
                )

        except Exception as e:
            logger.error(f"[REALTIME-EVENT] Error procesando evento: {e}")

    async def handle_websocket_session(self, call_id: str, tenant_id: str, branch_id: str):
        """
        Maneja la sesión WebSocket con OpenAI para recibir eventos de transcripción.
        """
        try:
            websocket_url = f"wss://api.openai.com/v1/realtime?call_id={call_id}"
            logger.info(f"[WEBSOCKET] Conectando a WebSocket SIP: {websocket_url}")

            headers_list = []
            for key, value in self.auth_header.items():
                headers_list.append((key, value))

            async with websockets.connect(
                websocket_url,
                extra_headers=headers_list,
            ) as websocket:
                logger.info(f"[WEBSOCKET] Conectado al WebSocket para call_id: {call_id}")

                # Procesar eventos de la conversación
                while True:
                    try:
                        response = await websocket.recv()
                        event_data = json.loads(response)

                        event_type = event_data.get("type", "unknown")

                        # Delegar el procesamiento del evento al servicio de transcripciones
                        event_silenced = self.transcription_service.process_websocket_event(
                            event_type, event_data, call_id
                        )

                        if not event_silenced:
                            logger.debug(f"[WEBSOCKET-EVENT] Evento: {event_type}")

                        await self.process_realtime_event(
                            event_data, websocket, call_id, tenant_id, branch_id
                        )

                    except websockets.exceptions.ConnectionClosed:
                        logger.info(f"[WEBSOCKET] WebSocket cerrado para call_id: {call_id}")
                        break
                    except Exception as e:
                        logger.error(f"[WEBSOCKET] Error en WebSocket: {e}")
                        break

                # WebSocket terminado - procesar finalización de llamada
                logger.info(f"[WEBSOCKET] Procesando finalización de llamada: {call_id}")

                call_metadata = self.active_calls.get(call_id, {})
                tenant_id = call_metadata.get('tenant_id', '')
                branch_id = call_metadata.get('branch_id', '')
                from_number = call_metadata.get('from_number', '')
                to_number = call_metadata.get('to_number', '')

                # Procesar finalización
                await self.handle_call_completion(
                    call_id=call_id,
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    from_number=from_number,
                    to_number=to_number
                )

                # Limpiar metadata
                if call_id in self.active_calls:
                    del self.active_calls[call_id]

        except Exception as e:
            logger.error(f"[WEBSOCKET] Error general en sesión: {e}")

    async def handle_call_ended_event(self, event_data: Dict) -> None:
        """
        Maneja el evento cuando termina una llamada.
        """
        try:
            call_id = event_data.get('data', {}).get('call_id', '')

            if not call_id:
                logger.warning("[CALL-ENDED] No se encontró call_id en el evento")
                return

            logger.info(f"[CALL-ENDED] Llamada finalizada - Call ID: {call_id}")

            call_metadata = self.active_calls.get(call_id, {})
            tenant_id = call_metadata.get('tenant_id', '')
            branch_id = call_metadata.get('branch_id', '')
            from_number = call_metadata.get('from_number', '')
            to_number = call_metadata.get('to_number', '')

            logger.info(f"[CALL-ENDED] Metadata recuperada - From: {from_number}")

            # Obtener transcript
            logger.info(f"[CALL-ENDED] Obteniendo transcript de OpenAI...")
            transcript_result = await self._get_call_transcript_simple(call_id)

            if transcript_result['success']:
                transcript = transcript_result['transcript']
                logger.info(f"[CALL-ENDED] Transcript obtenido exitosamente")

                duration = event_data.get('data', {}).get('duration', 0)

                # Si no hay duración, calcular desde metadata
                if duration == 0 and call_metadata.get('start_timestamp'):
                    duration = int(datetime.now().timestamp() - call_metadata['start_timestamp'])

                await self.handle_call_completion(
                    call_id=call_id,
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    from_number=from_number,
                    to_number=to_number,
                    duration=duration,
                    transcript=transcript
                )

                # Limpiar metadata
                if call_id in self.active_calls:
                    del self.active_calls[call_id]

            else:
                logger.error(f"[CALL-ENDED] No se pudo obtener transcript: {transcript_result.get('error')}")

        except Exception as e:
            logger.error(f"[CALL-ENDED] Error manejando fin de llamada: {e}")

    async def handle_call_completion(self, call_id: str, tenant_id: str, branch_id: str,
                                    from_number: str, to_number: str, duration: int = 0,
                                    transcript: str = ""):
        """
        Maneja la finalización de una llamada y guarda el historial.
        """
        try:
            logger.info(f"[CALL-COMPLETION] Finalizando llamada {call_id}")

            # Log: Llamada terminada
            if call_id in self.call_loggers:
                self.call_loggers[call_id].log_call_ended(duration)

            # Si no hay transcript del Session API, usar el almacenado localmente
            full_conversation = transcript
            if not full_conversation:
                full_conversation = self.transcription_service.get_full_transcript(call_id)

            transcript_to_save = full_conversation

            # Formatear números
            from_formatted = format_phone_number(from_number) if from_number else ""
            to_formatted = format_phone_number(to_number) if to_number else ""

            # Obtener logs técnicos
            technical_logs = []
            if call_id in self.call_loggers:
                technical_logs = self.call_loggers[call_id].get_logs()
                logger.info(f"[CALL-COMPLETION] Logs capturados: {len(technical_logs)} eventos")

            # Ejecutar Post AI Call Analysis
            logger.info(f"[CALL-COMPLETION] Ejecutando Post AI Call Analysis")
            await self._process_post_call_analysis(
                call_id=call_id,
                tenant_id=tenant_id,
                branch_id=branch_id,
                caller_phone=from_formatted,
                duration=duration,
                technical_logs=technical_logs
            )

            # Limpiar transcripción
            self.transcription_service.clear_transcript(call_id)

            # Actualizar información del cliente
            if from_formatted:
                await self.update_client_info(tenant_id, branch_id, from_formatted, call_id)

            # Si fue una llamada Vicidial, notificar fin
            try:
                await self.vicidial_service.hangup_call(call_id)
            except Exception as vicidial_error:
                logger.debug(f"[CALL-COMPLETION] Vicidial hangup (esperado si no es vicidial): {vicidial_error}")

        except Exception as e:
            logger.error(f"[CALL-COMPLETION] Error finalizando llamada: {e}")

    async def update_client_info(self, tenant_id: str, branch_id: str, phone: str, call_id: str):
        """
        Actualiza información del cliente después de la llamada.
        """
        try:
            if not self.client_service:
                logger.warning(f"[CLIENT-UPDATE] ClientService no disponible")
                return

            client_result = await self.client_service.get_or_create_client(
                tenant_id=tenant_id,
                branch_id=branch_id,
                phone=phone,
                name=None
            )

            if client_result:
                is_new = client_result.get('is_new', False)
                visit_count = client_result.get('visit_count', 1)

                if is_new:
                    logger.info(f"[CLIENT-UPDATE] Cliente nuevo registrado: {phone}")
                else:
                    logger.info(f"[CLIENT-UPDATE] Cliente actualizado (visitas: {visit_count})")

        except Exception as e:
            logger.error(f"[CLIENT-UPDATE] Error actualizando cliente: {e}")

    async def _process_post_call_analysis(self, call_id: str, tenant_id: str, branch_id: str,
                                         caller_phone: str, duration: int, technical_logs: list):
        """
        Procesa análisis post-llamada usando PostAICallService.
        """
        try:
            logger.info(f"[POST-CALL] Iniciando análisis post-llamada para {call_id}")

            await self.post_ai_call_service.process_call(
                call_id=call_id,
                tenant_id=tenant_id,
                branch_id=branch_id,
                caller_phone=caller_phone,
                call_duration=duration,
                technical_logs=technical_logs
            )

            logger.info(f"[POST-CALL] Análisis completado para {call_id}")

        except Exception as e:
            logger.error(f"[POST-CALL] Error en análisis post-llamada: {e}")

    async def _get_call_transcript_simple(self, call_id: str) -> Dict[str, Any]:
        """
        Obtiene el transcript de una llamada desde OpenAI Sessions API.
        """
        try:
            url = f"https://api.openai.com/v1/realtime/sessions/{call_id}/transcript"

            response = requests.get(
                url,
                headers=self.auth_header,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                transcript = data.get('transcript', '')
                return {
                    'success': True,
                    'transcript': transcript
                }
            else:
                logger.warning(f"[TRANSCRIPT] Status {response.status_code}: {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}"
                }

        except Exception as e:
            logger.error(f"[TRANSCRIPT] Error obteniendo transcript: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def handle_incoming_sip_call(self, request: Request) -> Dict[str, Any]:
        """
        Webhook principal para llamadas SIP de OpenAI.
        Punto de entrada principal para todas las llamadas entrantes.
        """
        try:
            body = await request.body()
            headers = dict(request.headers)

            logger.info(f"[SIP-WEBHOOK] Headers recibidos: {list(headers.keys())}")
            logger.info(f"[SIP-WEBHOOK] Body size: {len(body)} bytes")

            try:
                logger.info(f"[SIP-WEBHOOK] Procesando webhook")
                event_data = json.loads(body.decode())
                logger.info(f"[SIP-WEBHOOK] Event type: {event_data.get('type')}")

                # LOG detallado
                logger.info(f"[WEBHOOK-DEBUG] Estructura completa del webhook:")
                logger.info(f"[WEBHOOK-DEBUG] {json.dumps(event_data, indent=2)}")

                # Crear objeto compatible
                class MockEvent:
                    def __init__(self, data):
                        self.type = data.get('type', 'realtime.call.incoming')
                        data_section = data.get('data', {})
                        self.data = type('obj', (object,), {
                            'call_id': data_section.get('call_id', 'mock_call_id'),
                            'sip_headers': data_section.get('sip_headers', [])
                        })()

                event = MockEvent(event_data)

            except Exception as parse_error:
                logger.error(f"[SIP-WEBHOOK] Error parseando evento: {parse_error}")
                return {"status": "error", "message": "Invalid event format"}

            # Manejar diferentes tipos de eventos
            if event.type == "realtime.call.incoming":
                call_id = event.data.call_id
                logger.info(f"[SIP-CALL] LLAMADA ENTRANTE - Call ID: {call_id}")

                # Extraer número origen
                from_number = "unknown"
                try:
                    sip_headers = event_data.get('data', {}).get('sip_headers', [])
                    for header in sip_headers:
                        if header.get('name') == 'From':
                            from_value = header.get('value', '')
                            logger.info(f"[EXTRACTION] Header From: {from_value}")
                            if '@' in from_value and 'sip:' in from_value:
                                from_number = from_value.split('@')[0].replace('<sip:', '').replace('sip:', '')
                                if from_number and not from_number.startswith('+'):
                                    from_number = '+' + from_number
                            break
                except Exception as e:
                    logger.warning(f"[DEDUP] Error extrayendo número origen: {e}")

                logger.info(f"[EXTRACTION] Número final: {from_number}")

                current_time = time.time()

                # Deduplicación: ignorar llamadas duplicadas en 15 segundos
                if from_number in self.recent_calls:
                    last_call = self.recent_calls[from_number]
                    time_diff = current_time - last_call["timestamp"]
                    if time_diff < 15:
                        logger.warning(f"[DEDUP] Llamada duplicada de {from_number} ignorada ({time_diff:.1f}s)")
                        return {"status": "duplicate_ignored", "from_number": from_number}

                self.recent_calls[from_number] = {
                    "timestamp": current_time,
                    "call_id": call_id
                }

                # Limpiar entradas viejas
                old_numbers = [num for num, data in self.recent_calls.items()
                              if current_time - data["timestamp"] > 60]
                for num in old_numbers:
                    del self.recent_calls[num]

                logger.info(f"[DEDUP] Llamada de {from_number} ACEPTADA - Call ID: {call_id}")

                # Crear CallLogger
                call_logger = CallLogger(call_id)
                self.call_loggers[call_id] = call_logger

                call_logger.log_call_received(
                    from_number=from_number,
                    to_number="detecting...",
                    headers={h.get('name'): h.get('value') for h in event_data.get('data', {}).get('sip_headers', [])}
                )

            elif event.type in ["realtime.call.completed", "realtime.call.ended", "realtime.call.disconnected"]:
                logger.info(f"[SIP-WEBHOOK] EVENTO DE FIN DE LLAMADA: {event.type}")
                asyncio.create_task(self.handle_call_ended_event(event_data))
                return {"status": "call_ended_processing"}

            # Continuar con flujo normal para llamadas entrantes
            if event.type == "realtime.call.incoming":

                # Detectar tenant/branch
                try:
                    to_number = None
                    for header in event_data.get('data', {}).get('sip_headers', []):
                        if header.get('name') == 'X-Original-Called':
                            to_number = header.get('value', '')
                            break

                    if not to_number:
                        for header in event_data.get('data', {}).get('sip_headers', []):
                            if header.get('name') == 'To':
                                to_value = header.get('value', '')
                                if '@' in to_value and 'sip:' in to_value:
                                    to_number = to_value.split('@')[0].replace('<sip:', '').replace('>', '')
                                break

                    logger.info(f"[MULTITENANT] X-Original-Called: {to_number}, From: {from_number}")

                    # Buscar branch en base de datos
                    phone_to_check = to_number
                    if phone_to_check and not phone_to_check.startswith('+'):
                        phone_to_check = f"+52{phone_to_check}"

                    logger.info(f"[MULTITENANT] Buscando branch para: {phone_to_check}")

                    branch_info = await self.db.get_branch_by_phone(phone_to_check)
                    if branch_info:
                        tenant_id = branch_info['tenant_id']
                        branch_id = branch_info['id']
                        branch_timezone = branch_info.get('timezone', 'America/Mexico_City')
                        self.call_timezones[call_id] = branch_timezone
                        logger.info(f"[MULTITENANT] Branch detectada: {branch_info.get('name')}, TZ: {branch_timezone}")

                        if call_id in self.call_loggers:
                            self.call_loggers[call_id].log_tenant_detected(
                                tenant_id=tenant_id,
                                tenant_name="Unknown",
                                branch_id=branch_id,
                                branch_name=branch_info.get('name', 'Unknown')
                            )
                    else:
                        logger.warning(f"[MULTITENANT] No se encontró branch para {phone_to_check}, usando default")
                        tenant_id = "default-tenant"
                        branch_id = "default-branch"
                        self.call_timezones[call_id] = "America/Mexico_City"

                    logger.info(f"[SIP-CALL] Call ID: {call_id}, Tenant: {tenant_id}, Branch: {branch_id}")

                    # Generar configuración
                    call_accept_config = await self.get_call_accept_config(tenant_id, branch_id, from_number=from_number)

                    # Guardar ai_config para post-call
                    if branch_id and self.tenant_service:
                        try:
                            branch_ai_config = await self.tenant_service.get_branch_ai_config(branch_id)
                            if branch_ai_config:
                                self.call_ai_configs[call_id] = branch_ai_config
                                logger.info(f"[SIP-CALL] AI config guardado para post-call")
                        except Exception as config_error:
                            logger.warning(f"[SIP-CALL] Error guardando ai_config: {config_error}")

                except Exception as tenant_error:
                    logger.error(f"[SIP-CALL] Error en detección tenant: {tenant_error}")
                    call_accept_config = {
                        "type": "realtime",
                        "instructions": "Eres un asistente virtual. Saluda y ayuda al cliente.",
                        "model": "gpt-4o-realtime-preview-2024-12-17",
                        "tools": get_callcenter_tools(),
                        "voice": "sage"
                    }
                    tenant_id = "default-tenant"
                    branch_id = "default-branch"
                    to_number = "unknown"

                # Log detallado
                logger.info(f"[SIP-CALL] Configuración enviada a OpenAI:")
                logger.info(f"[SIP-CALL] URL: https://api.openai.com/v1/realtime/calls/{call_id}/accept")
                logger.info(f"[SIP-CALL] Config size: {len(json.dumps(call_accept_config))} bytes")

                # Aceptar llamada
                response = requests.post(
                    f"https://api.openai.com/v1/realtime/calls/{call_id}/accept",
                    headers={**self.auth_header, "Content-Type": "application/json"},
                    json=call_accept_config,
                    timeout=30
                )

                logger.info(f"[SIP-CALL] Respuesta de OpenAI: Status {response.status_code}")

                if response.status_code == 200:
                    logger.info(f"[SIP-CALL] Llamada aceptada: {call_id}")

                    if call_id in self.call_loggers:
                        self.call_loggers[call_id].log_session_created(
                            session_id=call_id,
                            model=call_accept_config.get('model', 'unknown')
                        )

                        tools_count = len(call_accept_config.get('tools', []))
                        if tools_count > 0:
                            self.call_loggers[call_id].log_tools_sent(tools_count)

                    # Guardar metadata
                    self.active_calls[call_id] = {
                        'from_number': from_number,
                        'to_number': to_number,
                        'tenant_id': tenant_id,
                        'branch_id': branch_id,
                        'start_time': datetime.now(),
                        'start_timestamp': datetime.now().timestamp()
                    }

                    self.call_phone_numbers[call_id] = from_number
                    self.call_start_times[call_id] = datetime.now()
                    logger.info(f"[SIP-CALL] Metadata guardada - From: {from_number}, To: {to_number}")

                    # Match con Vicidial (si hay llamada pendiente en ventana de 10s)
                    vicidial_match = self.vicidial_service.match_vicidial_to_sip(call_id)
                    if vicidial_match:
                        logger.info(f"[SIP-CALL] Vicidial match encontrado: {vicidial_match}")
                    else:
                        logger.debug(f"[SIP-CALL] No Vicidial match (llamada directa o timing miss)")

                    # Conectar WebSocket
                    logger.info(f"[SIP-CALL] Conectando WebSocket para transcripciones...")
                    task = asyncio.create_task(
                        self.handle_websocket_session(call_id, tenant_id, branch_id)
                    )

                    return {"status": "call_accepted", "call_id": call_id}

                else:
                    logger.error(f"[SIP-CALL] Error aceptando llamada: {response.status_code} - {response.text}")
                    return {"status": "error", "message": f"Failed to accept call: {response.status_code}"}

        except Exception as e:
            logger.error(f"[SIP-WEBHOOK] Error general: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}


# Singleton instance used by main.py
openai_sip_handler = OpenAISIPHandler()

"""
Function Call Handler Service - Call Center Edition
Servicio centralizado para manejar ALL function calls de OpenAI Realtime API en call center.
Cerebro principal que coordina: transfer_to_human, hangup_call, lookup_customer_info
"""

import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from utils.log_helper import format_log_with_call_id

logger = logging.getLogger(__name__)


class FunctionCallHandlerService:
    """
    Servicio centralizado para manejar todas las function calls de OpenAI Realtime API
    en ambiente de call center.

    Responsabilidades:
    - Router central de todas las funciones para call center
    - Coordinación entre servicios especializados (Vicidial, Client)
    - Validación de argumentos según tenant
    - Logging uniforme de function calls
    - Respuestas estandarizadas a OpenAI
    """

    def __init__(
        self,
        database_manager=None,
        tenant_service=None,
        vicidial_service=None,
        client_service=None
    ):
        """
        Inicializa el handler de function calls para call center.

        Args:
            database_manager: Instancia del DatabaseManager
            tenant_service: Instancia del TenantService
            vicidial_service: Instancia del VicidialService para transferencias
            client_service: Instancia del ClientService para búsqueda de clientes
        """
        self.db = database_manager
        self.tenant_service = tenant_service
        self.vicidial_service = vicidial_service
        self.client_service = client_service

        # Registro de funciones disponibles para call center
        self.function_registry = {
            "transfer_to_human": self._handle_transfer_to_human,
            "hangup_call": self._handle_hangup_call,
            "lookup_customer_info": self._handle_lookup_customer_info,
        }

        logger.info("[FUNCTION-HANDLER] ✅ Servicio call center inicializado con funciones disponibles: " +
                   ", ".join(self.function_registry.keys()))

    async def handle_function_call(
        self,
        function_name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Router principal para todas las function calls.

        Args:
            function_name: Nombre de la función a ejecutar
            arguments: Argumentos de la función
            context: Contexto de la llamada (call_id, tenant_id, branch_id, phone, etc)

        Returns:
            Dict con resultado de la función para enviar a OpenAI
        """
        # Extraer call_id del contexto para logs
        call_id = context.get("call_id", "unknown")

        try:
            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 🚀 Ejecutando: {function_name}"))
            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 📝 Argumentos: {arguments}"))
            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 🏢 Contexto: tenant={context.get('tenant_id')}, phone={context.get('phone')}"))

            # Verificar si la función está registrada
            if function_name not in self.function_registry:
                error_msg = f"Función {function_name} no está disponible"
                logger.error(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ❌ {error_msg}"))
                return self._create_error_response(error_msg)

            # Ejecutar la función correspondiente
            handler = self.function_registry[function_name]
            result = await handler(arguments, context)

            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ✅ Resultado para {function_name}: {result.get('status', 'unknown')}"))
            return result

        except Exception as e:
            error_msg = f"Error ejecutando {function_name}: {str(e)}"
            logger.error(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ❌ {error_msg}"))
            return self._create_error_response(error_msg)

    async def _handle_transfer_to_human(
        self,
        arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Maneja transfer_to_human - Transfiere la llamada a un agente humano.

        Args:
            arguments: {
                "queue_name": str (opcional),
                "priority": str (optional: high, normal, low),
                "reason": str (opcional - razón de la transferencia)
            }
            context: Contexto con call_id, tenant_id, phone, etc.

        Returns:
            Dict con resultado de la transferencia
        """
        call_id = context.get("call_id", "unknown")
        phone = context.get("phone", "unknown")

        try:
            queue_name = arguments.get("queue_name", "general")
            priority = arguments.get("priority", "normal")
            reason = arguments.get("reason", "Cliente solicitó transferencia")

            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 🔄 Transfiriendo a agente humano"))
            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] Cola: {queue_name}, Prioridad: {priority}"))
            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] Razón: {reason}"))

            if not self.vicidial_service:
                logger.error(format_log_with_call_id(call_id, "[FUNCTION-HANDLER] ❌ VicidialService no disponible"))
                return self._create_error_response("No puedo transferirte en este momento. Intenta de nuevo.")

            # Transferir llamada a través de Vicidial
            # queue_name maps to Vicidial ingroup (e.g. "IN_ENTRADA")
            ingroup = queue_name if queue_name != "general" else "IN_ENTRADA"
            transfer_result = await self.vicidial_service.transfer_to_agent(
                openai_call_id=call_id,
                ingroup=ingroup
            )

            if transfer_result.get("success"):
                logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ✅ Transferencia exitosa a {queue_name}"))
                return self._create_success_response(
                    message=f"Te estoy transfiriendo a un agente. Por favor espera.",
                    data={"queue": queue_name, "agent_id": transfer_result.get("agent_id")}
                )
            else:
                error_msg = transfer_result.get("error", "Error desconocido en transferencia")
                logger.warning(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ⚠️ Transferencia fallida: {error_msg}"))
                return self._create_error_response(
                    f"No pude completar la transferencia. {error_msg}"
                )

        except Exception as e:
            logger.error(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ❌ Error en transfer_to_human: {e}"))
            return self._create_error_response("Error al transferir. Intenta de nuevo más tarde.")

    async def _handle_hangup_call(
        self,
        arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Maneja hangup_call - Termina la llamada.

        Args:
            arguments: {
                "reason": str (opcional - razón del cierre),
                "status": str (optional: completed, failed, abandoned, etc.)
            }
            context: Contexto con call_id, tenant_id, phone, etc.

        Returns:
            Dict con resultado del hangup
        """
        call_id = context.get("call_id", "unknown")
        phone = context.get("phone", "unknown")

        try:
            reason = arguments.get("reason", "Llamada finalizada")
            status = arguments.get("status", "INFO")

            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 📞 Finalizando llamada"))
            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] Estado: {status}, Razón: {reason}"))

            if not self.vicidial_service:
                logger.error(format_log_with_call_id(call_id, "[FUNCTION-HANDLER] ❌ VicidialService no disponible"))
                return self._create_error_response("No puedo finalizar la llamada en este momento.")

            # Finalizar llamada a través de Vicidial
            hangup_result = await self.vicidial_service.hangup_call(
                openai_call_id=call_id,
                status=status,
                notes=reason
            )

            if hangup_result.get("success"):
                logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ✅ Llamada finalizada exitosamente"))
                return self._create_success_response(
                    message="Gracias por llamar. Hasta luego.",
                    data={"status": status, "call_id": call_id}
                )
            else:
                error_msg = hangup_result.get("error", "Error desconocido al finalizar")
                logger.warning(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ⚠️ Hangup fallido: {error_msg}"))
                return self._create_error_response(
                    "Hubo un problema al finalizar. Intenta de nuevo."
                )

        except Exception as e:
            logger.error(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ❌ Error en hangup_call: {e}"))
            return self._create_error_response("Error finalizando la llamada.")

    async def _handle_lookup_customer_info(
        self,
        arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Maneja lookup_customer_info - Busca información del cliente.

        Args:
            arguments: {
                "phone": str (teléfono del cliente),
                "name": str (opcional - nombre del cliente),
                "lookup_type": str (optional: phone, name, id)
            }
            context: Contexto con call_id, tenant_id, branch_id, etc.

        Returns:
            Dict con información del cliente
        """
        call_id = context.get("call_id", "unknown")
        tenant_id = context.get("tenant_id")
        branch_id = context.get("branch_id")

        try:
            phone = arguments.get("phone", "").strip()
            name = arguments.get("name", "").strip()
            lookup_type = arguments.get("lookup_type", "phone")

            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 🔍 Buscando cliente"))
            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] Tipo: {lookup_type}, Phone: {phone}, Name: {name}"))

            if not self.client_service:
                logger.error(format_log_with_call_id(call_id, "[FUNCTION-HANDLER] ❌ ClientService no disponible"))
                return self._create_error_response("No puedo acceder a la información del cliente en este momento.")

            # Determinar qué búsqueda hacer
            customer_info = None

            if lookup_type == "phone" and phone:
                logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 🔍 Buscando por teléfono: {phone}"))
                customer_info = await self.client_service.get_client_by_phone(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    phone=phone
                )

            elif lookup_type == "name" and name:
                logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] 🔍 Buscando por nombre: {name}"))
                customer_info = await self.client_service.search_clients_by_name(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    name=name
                )

            else:
                return self._create_error_response(
                    "Necesito un teléfono o nombre para buscar al cliente."
                )

            # Procesar resultado
            if not customer_info:
                logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ℹ️ Cliente no encontrado"))
                return self._create_success_response(
                    message="No encontré ese cliente en el sistema.",
                    data={
                        "found": False,
                        "customer": None
                    }
                )

            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ✅ Cliente encontrado"))

            # Si es lista de clientes (búsqueda por nombre), devolver primero
            if isinstance(customer_info, list):
                if len(customer_info) == 0:
                    return self._create_success_response(
                        message="No encontré ese cliente.",
                        data={"found": False, "customer": None}
                    )
                customer_info = customer_info[0]

            # Formatear información para respuesta
            formatted_customer = {
                "id": customer_info.get("id"),
                "name": customer_info.get("name"),
                "phone": customer_info.get("phone"),
                "email": customer_info.get("email"),
                "created_at": customer_info.get("created_at"),
                "notes": customer_info.get("notes")
            }

            logger.info(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ✅ Información formateada: {formatted_customer.get('name')} ({formatted_customer.get('phone')})"))

            return self._create_success_response(
                message=f"Encontré el cliente: {formatted_customer.get('name')}. Tienen {len(customer_info.get('call_history', []))} llamadas registradas.",
                data={
                    "found": True,
                    "customer": formatted_customer,
                    "call_count": len(customer_info.get("call_history", []))
                }
            )

        except Exception as e:
            logger.error(format_log_with_call_id(call_id, f"[FUNCTION-HANDLER] ❌ Error en lookup_customer_info: {e}"))
            return self._create_error_response("Error buscando al cliente. Intenta de nuevo.")

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """
        Crea una respuesta de error estandarizada.

        Args:
            error_message: Mensaje de error para mostrar al usuario

        Returns:
            Dict con formato de error estándar
        """
        return {
            "status": "error",
            "message": error_message,
            "timestamp": datetime.now().isoformat(),
            "error": True
        }

    def _create_success_response(self, message: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Crea una respuesta de éxito estandarizada.

        Args:
            message: Mensaje de éxito para mostrar al usuario
            data: Datos adicionales (opcional)

        Returns:
            Dict con formato de éxito estándar
        """
        response = {
            "status": "success",
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "error": False
        }

        if data:
            response["data"] = data

        return response

    async def add_future_function(self, function_name: str, handler_method):
        """
        Permite agregar nuevas funciones dinámicamente.
        Útil para extensibilidad futura.

        Args:
            function_name: Nombre de la nueva función
            handler_method: Método que maneja la función
        """
        self.function_registry[function_name] = handler_method
        logger.info(f"[FUNCTION-HANDLER] ➕ Nueva función agregada: {function_name}")

    def get_available_functions(self) -> List[str]:
        """
        Retorna lista de funciones disponibles.
        """
        return list(self.function_registry.keys())

    def get_function_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas del servicio.
        Útil para monitoring.
        """
        return {
            "available_functions": len(self.function_registry),
            "function_names": list(self.function_registry.keys()),
            "service_status": "active",
            "mode": "call_center"
        }

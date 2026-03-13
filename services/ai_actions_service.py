"""
AI Actions Service - Servicio OOP para acciones de IA y manejo de clientes
Migrado desde ai_actions.py con arquitectura OOP limpia
"""

import logging
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AIActionsService:
    """
    Servicio para acciones de IA relacionadas con clientes y reservas.
    Maneja cancelaciones, reprogramaciones, búsquedas y mapeo de servicios.
    """

    def __init__(self, database_manager=None, tenant_service=None):
        """
        Inicializar servicio de acciones de IA.

        Args:
            database_manager: Instancia del DatabaseManager
            tenant_service: Instancia del TenantService
        """
        self.db = database_manager
        self.tenant_service = tenant_service
        self.mexico_tz = ZoneInfo('America/Mexico_City')

        # Configuraciones por defecto
        self.default_cancellation_window_minutes = 30
        self.default_reschedule_window_minutes = 30

        # Mapeo de servicios común
        self.service_mappings = {
            "corte": "Corte de Cabello",
            "corte de pelo": "Corte de Cabello",
            "corte de cabello": "Corte de Cabello",
            "solo corte": "Corte de Cabello",
            "corte normal": "Corte de Cabello",
            "corte y barba": "Corte y Barba",
            "corte con barba": "Corte y Barba",
            "barba": "Corte y Barba",
            "arreglo de barba": "Corte y Barba",
            "premium": "Corte Premium",
            "corte premium": "Corte Premium",
            "servicio completo": "Corte Premium",
            "tratamiento": "Tratamiento Capilar",
            "tratamiento capilar": "Tratamiento Capilar"
        }

    async def get_or_create_client(
        self,
        tenant_id: str,
        branch_id: str,
        phone: str,
        name: Optional[str] = None,
        call_sid: Optional[str] = None,
        email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Buscar cliente existente por teléfono o crear uno nuevo.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la sucursal
            phone: Número de teléfono del cliente
            name: Nombre del cliente (si es nuevo)
            call_sid: ID de la llamada actual
            email: Email del cliente (opcional)

        Returns:
            Dict con información del cliente (existente o nuevo)
        """
        try:
            logger.info(f"[CLIENT-LOOKUP] 🔍 Buscando cliente por teléfono: {phone}")

            if not self.db:
                raise ValueError("DatabaseManager no disponible")

            # Buscar cliente existente
            existing_client = await self.db.get_client_by_phone(tenant_id, phone)

            if existing_client:
                # Cliente existente encontrado
                logger.info(f"[CLIENT-LOOKUP] ✅ Cliente conocido: {existing_client['name']} (visitas: {existing_client.get('visit_count', 0)})")

                # Actualizar información del cliente
                visit_count = existing_client.get('visit_count', 0) + 1
                update_data = {
                    "last_seen_at": datetime.now(self.mexico_tz).isoformat(),
                    "visit_count": visit_count,
                    "updated_at": datetime.now(self.mexico_tz).isoformat()
                }

                if call_sid:
                    update_data["last_call_sid"] = call_sid

                # Actualizar cliente
                await self.db.update_client(existing_client["id"], update_data)
                logger.info(f"[CLIENT-LOOKUP] 📊 Cliente actualizado - nueva visita #{visit_count}")

                return {
                    "ok": True,
                    "is_new": False,
                    "client": {
                        "id": existing_client["id"],
                        "name": existing_client["name"],
                        "phone": existing_client["phone"],
                        "email": existing_client.get("email"),
                        "visit_count": visit_count,
                        "first_seen_at": existing_client["first_seen_at"],
                        "is_returning": True,
                        "loyalty_status": self._calculate_loyalty_status(visit_count)
                    }
                }
            else:
                # Cliente nuevo
                logger.info(f"[CLIENT-LOOKUP] 🆕 Cliente nuevo detectado: {phone}")

                if not name:
                    logger.warning("[CLIENT-LOOKUP] ⚠️ Cliente nuevo sin nombre")
                    return {
                        "ok": True,
                        "is_new": True,
                        "needs_name": True,
                        "client": {
                            "phone": phone,
                            "is_returning": False,
                            "loyalty_status": "new"
                        }
                    }

                # Crear nuevo cliente
                client_data = {
                    "tenant_id": tenant_id,
                    "branch_id": branch_id,
                    "phone": phone,
                    "name": name,
                    "email": email,
                    "first_seen_at": datetime.now(self.mexico_tz).isoformat(),
                    "last_seen_at": datetime.now(self.mexico_tz).isoformat(),
                    "visit_count": 1,
                    "created_at": datetime.now(self.mexico_tz).isoformat(),
                    "updated_at": datetime.now(self.mexico_tz).isoformat()
                }

                if call_sid:
                    client_data["last_call_sid"] = call_sid

                new_client = await self.db.create_client(client_data)

                if new_client:
                    logger.info(f"[CLIENT-LOOKUP] ✅ Nuevo cliente creado: {name} (ID: {new_client['id']})")
                    return {
                        "ok": True,
                        "is_new": True,
                        "client": {
                            "id": new_client["id"],
                            "name": new_client["name"],
                            "phone": new_client["phone"],
                            "email": new_client.get("email"),
                            "visit_count": 1,
                            "first_seen_at": new_client["first_seen_at"],
                            "is_returning": False,
                            "loyalty_status": "new"
                        }
                    }
                else:
                    logger.error("[CLIENT-LOOKUP] ❌ Error creando cliente")
                    return {"ok": False, "error": "Error creando cliente"}

        except Exception as e:
            logger.error(f"[CLIENT-LOOKUP] ❌ Error en get_or_create_client: {e}")
            return {"ok": False, "error": str(e)}

    def _calculate_loyalty_status(self, visit_count: int) -> str:
        """Calcular estado de lealtad del cliente basado en visitas."""
        if visit_count == 1:
            return "new"
        elif visit_count <= 3:
            return "regular"
        elif visit_count <= 10:
            return "frequent"
        else:
            return "vip"

    async def find_reservations_by_phone(
        self,
        tenant_id: str,
        phone: str,
        customer_name: Optional[str] = None,
        days_ahead: int = 30,
        include_past: bool = False
    ) -> Dict[str, Any]:
        """
        Buscar reservas por número de teléfono con información enriquecida.

        Args:
            tenant_id: ID del tenant
            phone: Número de teléfono del cliente
            customer_name: Nombre opcional para filtrar
            days_ahead: Días hacia adelante para buscar
            include_past: Incluir reservas pasadas

        Returns:
            Dict con reservas encontradas y información del cliente
        """
        try:
            logger.info(f"[RESERVATIONS-SEARCH] 🔍 Buscando reservas - phone: {phone}, name: {customer_name}")

            if not self.db:
                raise ValueError("DatabaseManager no disponible")

            # Buscar información del cliente
            client_info = await self.db.get_client_by_phone(tenant_id, phone)
            if client_info:
                logger.info(f"[RESERVATIONS-SEARCH] 👤 Cliente encontrado: {client_info['name']} (visitas: {client_info.get('visit_count', 0)})")

            # Definir rango de fechas
            today_mx = datetime.now(self.mexico_tz).date()

            if include_past:
                start_date = (today_mx - timedelta(days=30)).isoformat()
            else:
                start_date = today_mx.isoformat()

            end_date = (today_mx + timedelta(days=days_ahead)).isoformat()

            logger.info(f"[RESERVATIONS-SEARCH] 📅 Buscando desde {start_date} hasta {end_date}")

            # Buscar reservas
            filters = {
                "tenant_id": tenant_id,
                "client_phone": phone
            }

            if not include_past:
                filters["status__in"] = ["pending", "confirmed"]

            reservations = await self.db.get_reservations_by_filters(
                filters=filters,
                date_from=start_date,
                date_to=end_date,
                include_resource_info=True
            )

            logger.info(f"[RESERVATIONS-SEARCH] 📊 Encontradas {len(reservations)} reservas")

            # Filtrar por nombre si se proporciona
            if customer_name and reservations:
                reservations = self._filter_reservations_by_name(reservations, customer_name)
                logger.info(f"[RESERVATIONS-SEARCH] 📊 Después del filtro por nombre: {len(reservations)} reservas")

            # Formatear reservas para respuesta
            formatted_reservations = []
            for i, res in enumerate(reservations, 1):
                formatted_res = self._format_reservation_for_display(res, i)
                formatted_reservations.append(formatted_res)

            # Construir respuesta enriquecida
            result = {
                "ok": True,
                "found": len(formatted_reservations),
                "reservations": formatted_reservations,
                "phone": phone,
                "customer_name": customer_name,
                "client_info": {
                    "is_known_client": client_info is not None,
                    "name": client_info["name"] if client_info else None,
                    "visit_count": client_info.get("visit_count", 0) if client_info else 0,
                    "email": client_info.get("email") if client_info else None,
                    "loyalty_status": self._calculate_loyalty_status(client_info.get("visit_count", 0)) if client_info else "new"
                },
                "search_summary": {
                    "date_range": f"{start_date} to {end_date}",
                    "included_past": include_past,
                    "total_found": len(formatted_reservations),
                    "active_reservations": len([r for r in reservations if r.get('status') in ['pending', 'confirmed']])
                }
            }

            logger.info(f"[RESERVATIONS-SEARCH] ✅ Búsqueda completada: {len(formatted_reservations)} reservas para {phone}")
            return result

        except Exception as e:
            logger.error(f"[RESERVATIONS-SEARCH] ❌ Error buscando reservas: {e}")
            return {
                "ok": False,
                "found": 0,
                "reservations": [],
                "error": str(e),
                "phone": phone,
                "customer_name": customer_name,
                "client_info": {"is_known_client": False}
            }

    def _filter_reservations_by_name(self, reservations: List[Dict], customer_name: str) -> List[Dict]:
        """Filtrar reservas por nombre del cliente."""
        customer_name_lower = customer_name.lower().strip()
        filtered = []

        for res in reservations:
            res_name = (res.get("customer_name") or "").lower().strip()

            # Búsqueda flexible
            if (customer_name_lower in res_name or
                any(part in res_name for part in customer_name_lower.split()) or
                any(part in customer_name_lower for part in res_name.split())):
                filtered.append(res)
                logger.info(f"[RESERVATIONS-SEARCH] ✅ Nombre coincidente: '{res_name}' matches '{customer_name}'")

        return filtered

    def _format_reservation_for_display(self, res: Dict, number: int) -> Dict[str, Any]:
        """Formatear reserva para mostrar al usuario."""
        try:
            # Extraer nombre del recurso asignado
            resource_name = "Sin asignar"
            if res.get("resources") and isinstance(res["resources"], dict):
                resource_name = res["resources"].get("name", "Sin asignar")
            elif res.get("resource_name"):
                resource_name = res["resource_name"]

            # Formatear fecha y hora
            res_date = datetime.strptime(res["date"], "%Y-%m-%d").strftime("%A %d de %B")
            res_time = datetime.strptime(res["start_time"], "%H:%M:%S").strftime("%I:%M %p")

            # Determinar estado visual
            status = res.get("status", "pending")
            status_emoji = {
                "pending": "⏳",
                "confirmed": "✅",
                "completed": "✅",
                "cancelled": "❌",
                "no_show": "❌"
            }.get(status, "❓")

            return {
                "id": res["id"],
                "number": number,
                "customer_name": res.get("customer_name", "Sin nombre"),
                "date": res["date"],
                "time": res["start_time"],
                "formatted_date": res_date,
                "formatted_time": res_time,
                "resource": resource_name,
                "status": status,
                "status_emoji": status_emoji,
                "confirmation_code": res.get("confirmation_code"),
                "service_name": res.get("service_name", "Servicio"),
                "description": f"{number}. {status_emoji} {res_date} a las {res_time}",
                "can_cancel": self._can_cancel_reservation(res),
                "can_reschedule": self._can_reschedule_reservation(res)
            }

        except Exception as e:
            logger.error(f"[RESERVATIONS-SEARCH] Error formateando reserva: {e}")
            return {
                "id": res.get("id", "unknown"),
                "number": number,
                "error": "Error formateando reserva"
            }

    def _can_cancel_reservation(self, reservation: Dict) -> bool:
        """Verificar si una reserva puede ser cancelada."""
        try:
            if reservation.get("status") not in ["pending", "confirmed"]:
                return False

            # Verificar ventana de tiempo
            res_datetime = datetime.combine(
                date.fromisoformat(reservation["date"]),
                datetime.strptime(reservation["start_time"], "%H:%M:%S").time()
            )
            res_datetime_mx = res_datetime.replace(tzinfo=self.mexico_tz)
            now_mx = datetime.now(self.mexico_tz)

            time_diff_minutes = (res_datetime_mx - now_mx).total_seconds() / 60
            return time_diff_minutes >= self.default_cancellation_window_minutes

        except Exception as e:
            logger.error(f"[AI-ACTIONS] Error verificando cancelación: {e}")
            return False

    def _can_reschedule_reservation(self, reservation: Dict) -> bool:
        """Verificar si una reserva puede ser reprogramada."""
        return self._can_cancel_reservation(reservation)  # Misma lógica por ahora

    async def cancel_reservation_if_allowed(
        self,
        tenant_id: str,
        reservation_id: str,
        caller_phone: str,
        minutes_lock: int = None
    ) -> Dict[str, Any]:
        """
        Cancelar reserva si pertenece al teléfono y cumple ventana de tiempo.

        Args:
            tenant_id: ID del tenant
            reservation_id: ID de la reserva
            caller_phone: Teléfono del cliente que cancela
            minutes_lock: Minutos mínimos antes de la cita para cancelar

        Returns:
            Dict con resultado de la cancelación
        """
        try:
            if minutes_lock is None:
                minutes_lock = self.default_cancellation_window_minutes

            logger.info(f"[CANCEL-RESERVATION] Intentando cancelar reserva {reservation_id} por {caller_phone}")

            if not self.db:
                raise ValueError("DatabaseManager no disponible")

            # Obtener reserva
            reservation = await self.db.get_reservation_by_id(reservation_id, tenant_id)
            if not reservation:
                return {"ok": False, "reason": "not_found"}

            # Verificar pertenencia
            if (reservation.get("client_phone") or "").strip() != (caller_phone or "").strip():
                logger.warning(f"[CANCEL-RESERVATION] Phone mismatch: {reservation.get('client_phone')} != {caller_phone}")
                return {"ok": False, "reason": "forbidden"}

            # Verificar estado
            if reservation.get("status") not in ["pending", "confirmed"]:
                return {"ok": False, "reason": "not_active"}

            # Verificar ventana de tiempo
            time_check = self._check_time_window(reservation, minutes_lock, "CANCEL")
            if not time_check["allowed"]:
                return {"ok": False, "reason": "too_close", "time_remaining": time_check["minutes_remaining"]}

            # Cancelar reserva
            cancel_data = {
                "status": "cancelled",
                "updated_at": datetime.now(self.mexico_tz).isoformat(),
                "cancelled_by": "client",
                "cancellation_reason": "client_request",
                "cancelled_at": datetime.now(self.mexico_tz).isoformat()
            }

            updated_reservation = await self.db.update_reservation(reservation_id, cancel_data)
            if updated_reservation:
                logger.info(f"[CANCEL-RESERVATION] ✅ Reserva cancelada exitosamente: {reservation_id}")
                return {"ok": True, "reservation": updated_reservation}
            else:
                return {"ok": False, "reason": "update_failed"}

        except Exception as e:
            logger.error(f"[CANCEL-RESERVATION] ❌ Error cancelando reserva: {e}")
            return {"ok": False, "reason": "error", "error": str(e)}

    async def reschedule_reservation_if_allowed(
        self,
        tenant_id: str,
        reservation_id: str,
        caller_phone: str,
        new_date: str,
        new_time: str,
        minutes_lock: int = None
    ) -> Dict[str, Any]:
        """
        Reprogramar reserva si es permitido y hay disponibilidad.

        Args:
            tenant_id: ID del tenant
            reservation_id: ID de la reserva
            caller_phone: Teléfono del cliente
            new_date: Nueva fecha (YYYY-MM-DD)
            new_time: Nueva hora (HH:MM)
            minutes_lock: Ventana mínima en minutos

        Returns:
            Dict con resultado de la reprogramación
        """
        try:
            if minutes_lock is None:
                minutes_lock = self.default_reschedule_window_minutes

            logger.info(f"[RESCHEDULE-RESERVATION] Reprogramando {reservation_id} a {new_date} {new_time}")

            if not self.db:
                raise ValueError("DatabaseManager no disponible")

            # Obtener reserva
            reservation = await self.db.get_reservation_by_id(reservation_id, tenant_id)
            if not reservation:
                return {"ok": False, "reason": "not_found"}

            # Verificar pertenencia
            if (reservation.get("client_phone") or "").strip() != (caller_phone or "").strip():
                return {"ok": False, "reason": "forbidden"}

            # Verificar estado
            if reservation.get("status") not in ["pending", "confirmed"]:
                return {"ok": False, "reason": "not_active"}

            # Verificar ventana de tiempo para la reserva actual
            time_check = self._check_time_window(reservation, minutes_lock, "RESCHEDULE")
            if not time_check["allowed"]:
                return {"ok": False, "reason": "too_close", "time_remaining": time_check["minutes_remaining"]}

            # Verificar disponibilidad en el nuevo horario
            availability_check = await self._check_new_time_availability(
                tenant_id=tenant_id,
                resource_id=reservation.get("resource_id"),
                new_date=new_date,
                new_time=new_time,
                exclude_reservation_id=reservation_id
            )

            if not availability_check["available"]:
                return {
                    "ok": False,
                    "reason": "conflict",
                    "conflicts": availability_check.get("conflicts", [])
                }

            # Calcular nueva hora de fin (asumiendo 30 minutos por defecto)
            new_start_time = datetime.strptime(new_time, "%H:%M").time()
            new_end_time = (datetime.combine(date.today(), new_start_time) + timedelta(minutes=30)).time()

            # Actualizar reserva
            update_data = {
                "date": new_date,
                "start_time": f"{new_time}:00",
                "end_time": new_end_time.strftime("%H:%M:%S"),
                "updated_at": datetime.now(self.mexico_tz).isoformat(),
                "rescheduled_at": datetime.now(self.mexico_tz).isoformat(),
                "reschedule_count": reservation.get("reschedule_count", 0) + 1
            }

            updated_reservation = await self.db.update_reservation(reservation_id, update_data)
            if updated_reservation:
                logger.info(f"[RESCHEDULE-RESERVATION] ✅ Reserva reprogramada: {reservation_id}")
                return {"ok": True, "reservation": updated_reservation}
            else:
                return {"ok": False, "reason": "update_failed"}

        except Exception as e:
            logger.error(f"[RESCHEDULE-RESERVATION] ❌ Error reprogramando: {e}")
            return {"ok": False, "reason": "error", "error": str(e)}

    def _check_time_window(self, reservation: Dict, minutes_lock: int, operation: str) -> Dict[str, Any]:
        """Verificar ventana de tiempo para operaciones."""
        try:
            # Crear datetime de la reserva en zona horaria México
            res_date = date.fromisoformat(reservation["date"])
            res_time = datetime.strptime(reservation["start_time"], "%H:%M:%S").time()
            res_datetime = datetime.combine(res_date, res_time)
            res_datetime_mx = res_datetime.replace(tzinfo=self.mexico_tz)

            # Hora actual en México
            now_mx = datetime.now(self.mexico_tz)
            time_diff_minutes = (res_datetime_mx - now_mx).total_seconds() / 60

            logger.info(f"[{operation}-DEBUG] ⏰ Reserva: {res_datetime_mx}")
            logger.info(f"[{operation}-DEBUG] ⏰ Ahora: {now_mx}")
            logger.info(f"[{operation}-DEBUG] ⏰ Diferencia: {time_diff_minutes:.1f} min (req: {minutes_lock} min)")

            allowed = time_diff_minutes >= minutes_lock

            return {
                "allowed": allowed,
                "minutes_remaining": max(0, time_diff_minutes),
                "required_minutes": minutes_lock
            }

        except Exception as e:
            logger.error(f"[{operation}-DEBUG] Error verificando ventana de tiempo: {e}")
            return {"allowed": False, "minutes_remaining": 0, "required_minutes": minutes_lock}

    async def _check_new_time_availability(
        self,
        tenant_id: str,
        resource_id: str,
        new_date: str,
        new_time: str,
        exclude_reservation_id: str = None
    ) -> Dict[str, Any]:
        """Verificar disponibilidad en nuevo horario."""
        try:
            if not self.db:
                raise ValueError("DatabaseManager no disponible")

            # Obtener reservas existentes para el recurso y fecha
            filters = {
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "date": new_date,
                "status__in": ["pending", "confirmed"]
            }

            existing_reservations = await self.db.get_reservations_by_filters(filters)

            # Filtrar reserva actual si existe
            if exclude_reservation_id:
                existing_reservations = [r for r in existing_reservations if r["id"] != exclude_reservation_id]

            # Verificar conflictos de horario
            new_start = datetime.strptime(new_time, "%H:%M").time()
            new_end = (datetime.combine(date.today(), new_start) + timedelta(minutes=30)).time()

            conflicts = []
            for res in existing_reservations:
                existing_start = datetime.strptime(res["start_time"], "%H:%M:%S").time()
                existing_end = datetime.strptime(res["end_time"], "%H:%M:%S").time()

                # Verificar solapamiento
                if not (new_end <= existing_start or new_start >= existing_end):
                    conflicts.append({
                        "reservation_id": res["id"],
                        "time_range": f"{existing_start.strftime('%H:%M')} - {existing_end.strftime('%H:%M')}",
                        "customer": res.get("customer_name", "Cliente")
                    })

            return {
                "available": len(conflicts) == 0,
                "conflicts": conflicts
            }

        except Exception as e:
            logger.error(f"[RESCHEDULE-AVAILABILITY] Error verificando disponibilidad: {e}")
            return {"available": False, "conflicts": []}

    async def map_service_to_id(
        self,
        service_name: str,
        tenant_id: str,
        branch_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Mapear nombre de servicio a ID de base de datos.

        Args:
            service_name: Nombre del servicio extraído por IA
            tenant_id: ID del tenant
            branch_id: ID de la sucursal

        Returns:
            Dict con información del servicio o None si no se encuentra
        """
        try:
            if not service_name or service_name.lower() in ["null", "none", ""]:
                return None

            logger.info(f"[SERVICE-MAP] Buscando servicio: '{service_name}' para tenant {tenant_id}")

            if not self.tenant_service:
                raise ValueError("TenantService no disponible")

            # Obtener servicios del tenant
            services = await self.tenant_service.get_services(tenant_id, branch_id)
            if not services:
                logger.warning(f"[SERVICE-MAP] No hay servicios para tenant {tenant_id}")
                return None

            # Buscar coincidencia exacta primero
            for service in services:
                if service['name'].lower() == service_name.lower():
                    logger.info(f"[SERVICE-MAP] ✅ Coincidencia exacta: {service['name']} (ID: {service['id']})")
                    return {
                        'service_id': service['id'],
                        'service_name': service['name'],
                        'price': service.get('price', 150),
                        'duration': service.get('duration', 30)
                    }

            # Buscar mapeo aproximado
            service_lower = service_name.lower().strip()
            for key, mapped_name in self.service_mappings.items():
                if key in service_lower or service_lower in key:
                    # Buscar el servicio mapeado
                    for service in services:
                        if service['name'] == mapped_name:
                            logger.info(f"[SERVICE-MAP] ✅ Mapeo aproximado: '{service_name}' → '{mapped_name}' (ID: {service['id']})")
                            return {
                                'service_id': service['id'],
                                'service_name': service['name'],
                                'price': service.get('price', 150),
                                'duration': service.get('duration', 30)
                            }

            logger.warning(f"[SERVICE-MAP] ⚠️ No se encontró mapeo para: '{service_name}'")
            return None

        except Exception as e:
            logger.error(f"[SERVICE-MAP] Error mapeando servicio: {e}")
            return None

    async def get_client_preferences(self, tenant_id: str, phone: str) -> Dict[str, Any]:
        """
        Obtener preferencias del cliente basadas en historial.

        Args:
            tenant_id: ID del tenant
            phone: Teléfono del cliente

        Returns:
            Dict con preferencias del cliente
        """
        try:
            if not self.db:
                raise ValueError("DatabaseManager no disponible")

            # Obtener cliente
            client = await self.db.get_client_by_phone(tenant_id, phone)
            if not client:
                return {"found": False}

            # Obtener historial de reservas
            filters = {
                "tenant_id": tenant_id,
                "client_phone": phone,
                "status": "completed"
            }

            past_reservations = await self.db.get_reservations_by_filters(
                filters=filters,
                limit=10,
                include_resource_info=True
            )

            # Analizar preferencias
            preferences = self._analyze_client_preferences(past_reservations)

            return {
                "found": True,
                "client_id": client["id"],
                "client_name": client["name"],
                "visit_count": client.get("visit_count", 0),
                "loyalty_status": self._calculate_loyalty_status(client.get("visit_count", 0)),
                "preferences": preferences
            }

        except Exception as e:
            logger.error(f"[CLIENT-PREFERENCES] Error obteniendo preferencias: {e}")
            return {"found": False, "error": str(e)}

    def _analyze_client_preferences(self, reservations: List[Dict]) -> Dict[str, Any]:
        """Analizar preferencias del cliente basadas en historial."""
        if not reservations:
            return {}

        service_frequency = {}
        time_preferences = []

        for res in reservations:
            # Servicio preferido
            service = res.get("service_name", "Servicio")
            service_frequency[service] = service_frequency.get(service, 0) + 1

            # Horario preferido
            if res.get("start_time"):
                try:
                    time_obj = datetime.strptime(res["start_time"], "%H:%M:%S").time()
                    time_preferences.append(time_obj.hour)
                except:
                    pass

        # Determinar preferencias
        preferred_service = max(service_frequency.keys(), key=service_frequency.get) if service_frequency else None

        # Análisis de horarios
        avg_hour = sum(time_preferences) / len(time_preferences) if time_preferences else 12
        if avg_hour < 12:
            time_preference = "morning"
        elif avg_hour < 17:
            time_preference = "afternoon"
        else:
            time_preference = "evening"

        return {
            "preferred_service": preferred_service,
            "time_preference": time_preference,
            "avg_preferred_hour": round(avg_hour, 1),
            "total_visits": len(reservations),
            "service_history": service_frequency
        }

    async def get_upcoming_reservations_by_phone(
        self,
        tenant_id: str,
        phone: str,
        days_ahead: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Obtener próximas reservas para un teléfono.

        Args:
            tenant_id: ID del tenant
            phone: Teléfono del cliente
            days_ahead: Días hacia adelante

        Returns:
            Lista de próximas reservas
        """
        try:
            result = await self.find_reservations_by_phone(
                tenant_id=tenant_id,
                phone=phone,
                days_ahead=days_ahead,
                include_past=False
            )

            if result["ok"]:
                return result["reservations"]
            else:
                return []

        except Exception as e:
            logger.error(f"[UPCOMING-RESERVATIONS] Error: {e}")
            return []
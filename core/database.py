"""
DatabaseManager - Professional OOP approach for Supabase operations
Handles all database operations for JesyAI SIP Realtime system
"""

import os
from supabase import create_client, Client
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date, time, timedelta
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ReservationData:
    """Data class for reservation information"""
    resource_id: str
    date: date
    start_time: time
    end_time: time
    customer_name: str
    tenant_id: str
    branch_id: str
    client_phone: Optional[str] = None
    client_email: Optional[str] = None
    status: str = "pending"
    price: Optional[float] = None
    service_id: Optional[str] = None
    notes: Optional[str] = None


class DatabaseManager:
    """
    Singleton class for managing all database operations
    Provides a clean OOP interface to Supabase
    """

    _instance = None
    _client: Optional[Client] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the Supabase client"""
        try:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_ANON_KEY")

            if not supabase_url or not supabase_key:
                raise ValueError("Missing SUPABASE_URL or SUPABASE_ANON_KEY environment variables")

            self._client = create_client(supabase_url, supabase_key)
            logger.info("✅ DatabaseManager initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize DatabaseManager: {e}")
            raise

    @property
    def client(self) -> Client:
        """Get the Supabase client instance"""
        if self._client is None:
            raise RuntimeError("DatabaseManager not properly initialized")
        return self._client

    # Multitenant Methods
    async def health_check(self) -> Dict[str, Any]:
        """Check database connection health"""
        try:
            # Simple query to test connection
            response = self.client.table('tenants').select('id').limit(1).execute()
            return {
                "status": "healthy",
                "connection": "ok",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def get_branches(self, tenant_id: str = None) -> List[Dict[str, Any]]:
        """Get all branches or branches for specific tenant"""
        try:
            query = self.client.table('branches').select('*')

            if tenant_id:
                query = query.eq('tenant_id', tenant_id)

            response = query.execute()
            return response.data or []
        except Exception as e:
            logger.error(f"❌ Error getting branches: {e}")
            return []

    async def get_branch(self, branch_id: str) -> Optional[Dict[str, Any]]:
        """Get branch by ID"""
        try:
            response = self.client.table('branches').select('*').eq('id', branch_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"❌ Error getting branch {branch_id}: {e}")
            return None

    async def get_branch_by_phone(self, phone_number: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Get branch by phone number (multitenant key lookup) with retry on timeout"""
        # Deduplicar variantes de teléfono
        phone_variants = list(dict.fromkeys([
            phone_number,
            phone_number.replace('+', ''),
            f"+{phone_number.lstrip('+')}"
        ]))

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[MULTITENANT] Looking up branch by phone: {phone_number} (intento {attempt}/{max_retries})")

                for phone in phone_variants:
                    # Check twilio_phone_number field
                    response = self.client.table('branches').select('*').eq(
                        'twilio_phone_number', phone
                    ).execute()

                    if response.data:
                        branch = response.data[0]
                        logger.info(f"[MULTITENANT] Found branch: {branch.get('name')} for phone: {phone}")
                        return branch

                    # Also check regular phone field
                    response = self.client.table('branches').select('*').eq(
                        'phone', phone
                    ).execute()

                    if response.data:
                        branch = response.data[0]
                        logger.info(f"[MULTITENANT] Found branch: {branch.get('name')} for phone: {phone}")
                        return branch

                logger.warning(f"[MULTITENANT] No branch found for phone: {phone_number}")
                return None

            except Exception as e:
                logger.warning(f"[MULTITENANT] ⚠️ Intento {attempt}/{max_retries} falló para {phone_number}: {e}")
                if attempt < max_retries:
                    logger.info(f"[MULTITENANT] 🔄 Reintentando...")
                    continue
                logger.error(f"❌ Error getting branch by phone {phone_number} después de {max_retries} intentos: {e}")
                return None

    async def get_branch_by_project_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get branch by OpenAI project ID (multitenant key lookup)"""
        try:
            logger.info(f"[MULTITENANT] Looking up branch by project ID: {project_id}")

            response = self.client.table('branches').select('*').eq(
                'openai_project_id', project_id
            ).execute()

            if response.data:
                branch = response.data[0]
                logger.info(f"[MULTITENANT] Found branch: {branch.get('name')} for project: {project_id}")
                return branch

            logger.warning(f"[MULTITENANT] No branch found for project ID: {project_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Error getting branch by project ID {project_id}: {e}")
            return None

    async def get_tenant_by_id(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant configuration by ID"""
        try:
            response = self.client.table('tenants').select('*').eq('id', tenant_id).single().execute()
            return response.data if response.data else None
        except Exception as e:
            logger.error(f"❌ Error getting tenant {tenant_id}: {e}")
            return None

    async def get_resources_by_tenant(self, tenant_id: str, resource_type: str = None, branch_id: str = None) -> List[Dict[str, Any]]:
        """Get resources (barberos, etc.) for a tenant"""
        try:
            query = self.client.table('resources').select('*').eq('tenant_id', tenant_id)

            if resource_type:
                # Use 'type' column as per actual Supabase schema
                query = query.eq('type', resource_type)

            if branch_id:
                query = query.eq('branch_id', branch_id)

            response = query.execute()
            return response.data or []
        except Exception as e:
            logger.error(f"❌ Error getting resources for tenant {tenant_id}: {e}")
            return []

    async def get_resource_by_id(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Get resource by ID"""
        try:
            logger.info(f"[DATABASE] Getting resource by ID: {resource_id}")

            response = self.client.table('resources').select('*').eq('id', resource_id).single().execute()

            if response.data:
                logger.info(f"[DATABASE] ✅ Resource found: {response.data.get('name', 'Unknown')}")
                return response.data
            else:
                logger.warning(f"[DATABASE] ⚠️ Resource not found for ID: {resource_id}")
                return None

        except Exception as e:
            logger.error(f"[DATABASE] ❌ Error getting resource by ID {resource_id}: {e}")
            return None

    async def get_branch_staff(self, branch_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene el staff/personal de una branch específica.
        """
        try:
            response = self.client.table("resources").select(
                "id, name, type, is_active"
            ).eq("branch_id", branch_id).eq("type", "staff").eq("is_active", True).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"Error getting branch staff: {e}")
            return []

    async def get_tenant_services(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene los servicios disponibles para un tenant.
        """
        try:
            response = self.client.table("services").select(
                "id, name, price"  # 🔧 Quitado 'duration' - columna no existe en Supabase
            ).eq("tenant_id", tenant_id).eq("active", True).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"Error getting tenant services: {e}")
            return []

    async def get_client_reservations(
        self,
        tenant_id: str,
        branch_id: str,
        client_phone: str,
        future_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Obtiene reservas del cliente por teléfono.

        Usado para cancelaciones - lista todas las reservas activas del cliente.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la branch
            client_phone: Teléfono del cliente
            future_only: Si True, solo retorna reservas futuras (>= hoy)

        Returns:
            Lista de reservas ordenadas por fecha ASC
        """
        try:
            from datetime import date

            query = self.client.table("reservations").select(
                "id, date, start_time, end_time, status, "
                "customer_name, client_phone, service_id, "
                "resource_id, notes, price, created_at"
            ).eq("tenant_id", tenant_id).eq("branch_id", branch_id).eq("client_phone", client_phone)

            # Filtrar solo futuras si se solicita
            if future_only:
                today = date.today().isoformat()
                query = query.gte("date", today)

            # Solo reservas activas (no canceladas)
            query = query.in_("status", ["confirmed", "pending"])

            # Ordenar por fecha (más próximas primero)
            query = query.order("date", desc=False).order("start_time", desc=False)

            response = query.execute()

            logger.info(f"[DATABASE] 📋 Encontradas {len(response.data or [])} reservas para {client_phone}")
            return response.data or []

        except Exception as e:
            logger.error(f"[DATABASE] Error obteniendo reservas del cliente: {e}")
            return []

    async def cancel_reservation_by_id(
        self,
        tenant_id: str,
        reservation_id: str,
        cancellation_reason: str
    ) -> bool:
        """
        Cancela una reserva específica.

        Actualiza el status a "cancelled" y guarda la razón en notes.

        Args:
            tenant_id: ID del tenant (seguridad)
            reservation_id: ID de la reserva a cancelar
            cancellation_reason: Razón de la cancelación

        Returns:
            True si se canceló exitosamente, False si falló
        """
        try:
            from datetime import datetime
            from utils.helpers import get_mexico_timezone

            # Preparar datos de actualización
            update_data = {
                "status": "cancelled",
                "notes": cancellation_reason,
                "updated_at": datetime.now(get_mexico_timezone()).isoformat()
            }

            # Actualizar reserva
            response = self.client.table("reservations").update(update_data).eq(
                "id", reservation_id
            ).eq("tenant_id", tenant_id).execute()

            success = bool(response.data)
            if success:
                logger.info(f"[DATABASE] ✅ Reserva {reservation_id} cancelada exitosamente")
            else:
                logger.error(f"[DATABASE] ❌ No se pudo cancelar reserva {reservation_id}")

            return success

        except Exception as e:
            logger.error(f"[DATABASE] Error cancelando reserva: {e}")
            return False


class AppointmentService:
    """Service class for handling appointments and availability"""

    def __init__(self):
        self.db = DatabaseManager()

    async def get_resource_availability(
        self,
        resource_id: str,
        date: date,
        branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get availability for a specific resource on a specific date"""
        try:
            # Get resource working hours
            resource_response = self.db.client.table("resources").select(
                "working_hours, branch_id, name, type"
            ).eq("id", resource_id).single().execute()

            if not resource_response.data:
                return {"error": "Resource not found"}

            resource = resource_response.data
            working_hours = resource.get("working_hours", {})

            # Use default working hours if not specified
            if not working_hours:
                working_hours = self._get_default_working_hours()
                logger.info(f"[AVAILABILITY] Using default hours for resource {resource.get('name')}")

            # Get existing reservations for that date
            reservations_response = self.db.client.table("reservations").select(
                "start_time, end_time, status"
            ).eq("resource_id", resource_id).eq("date", date.isoformat()).execute()

            reservations = reservations_response.data

            # Calculate available slots
            available_slots = self._calculate_available_slots(
                working_hours, reservations, date
            )

            return {
                "resource_id": resource_id,
                "resource_name": resource.get("name"),
                "resource_type": resource.get("type"),
                "date": date.isoformat(),
                "working_hours": working_hours,
                "reservations": reservations,
                "available_slots": available_slots
            }

        except Exception as e:
            logger.error(f"Error getting resource availability: {e}")
            return {"error": str(e)}

    async def get_branch_availability(
        self,
        branch_id: str,
        date: date
    ) -> Dict[str, Any]:
        """Get availability for all resources in a branch"""
        try:
            # Get all active resources for the branch
            resources_response = self.db.client.table("resources").select(
                "id, name, type, working_hours"
            ).eq("branch_id", branch_id).eq("is_active", True).execute()

            resources = resources_response.data
            branch_availability = {}

            for resource in resources:
                resource_availability = await self.get_resource_availability(
                    resource["id"], date, branch_id
                )
                branch_availability[resource["id"]] = {
                    "resource_name": resource["name"],
                    "resource_type": resource["type"],
                    "availability": resource_availability
                }

            return {
                "branch_id": branch_id,
                "date": date.isoformat(),
                "resources": branch_availability
            }

        except Exception as e:
            logger.error(f"Error getting branch availability: {e}")
            return {"error": str(e)}

    async def create_reservation(self, reservation: ReservationData) -> Dict[str, Any]:
        """Create a new reservation"""
        try:
            # Check for schedule conflicts
            conflict_check = await self._check_schedule_conflicts(
                reservation.resource_id,
                reservation.date,
                reservation.start_time,
                reservation.end_time
            )

            if conflict_check.get("has_conflicts"):
                return {"error": "Schedule conflict", "conflicts": conflict_check["conflicts"]}

            # Prepare reservation data
            reservation_data = {
                "resource_id": reservation.resource_id,
                "date": reservation.date.isoformat(),
                "start_time": reservation.start_time.strftime("%H:%M:%S"),
                "end_time": reservation.end_time.strftime("%H:%M:%S"),
                "customer_name": reservation.customer_name,
                "tenant_id": reservation.tenant_id,
                "branch_id": reservation.branch_id,
                "client_phone": reservation.client_phone,
                "client_email": reservation.client_email,
                "status": reservation.status,
                "price": reservation.price,
                "service_id": reservation.service_id,
                "notes": reservation.notes,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            # Create the reservation
            response = self.db.client.table("reservations").insert(reservation_data).execute()

            if response.data:
                return {"success": True, "reservation": response.data[0]}
            else:
                return {"error": "Failed to create reservation"}

        except Exception as e:
            logger.error(f"Error creating reservation: {e}")
            return {"error": str(e)}

    async def update_reservation(
        self,
        reservation_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing reservation"""
        try:
            updates["updated_at"] = datetime.now().isoformat()

            response = self.db.client.table("reservations").update(updates).eq(
                "id", reservation_id
            ).execute()

            if response.data:
                return {"success": True, "reservation": response.data[0]}
            else:
                return {"error": "Reservation not found"}

        except Exception as e:
            logger.error(f"Error updating reservation: {e}")
            return {"error": str(e)}

    async def cancel_reservation(self, reservation_id: str) -> Dict[str, Any]:
        """Cancel a reservation"""
        try:
            response = self.db.client.table("reservations").update({
                "status": "cancelled",
                "updated_at": datetime.now().isoformat()
            }).eq("id", reservation_id).execute()

            if response.data:
                return {"success": True, "reservation": response.data[0]}
            else:
                return {"error": "Reservation not found"}

        except Exception as e:
            logger.error(f"Error cancelling reservation: {e}")
            return {"error": str(e)}

    def _get_default_working_hours(self) -> Dict[str, Any]:
        """Get default working hours"""
        return {
            "monday": {"start": "09:00", "end": "19:00"},
            "tuesday": {"start": "09:00", "end": "19:00"},
            "wednesday": {"start": "09:00", "end": "19:00"},
            "thursday": {"start": "09:00", "end": "19:00"},
            "friday": {"start": "09:00", "end": "19:00"},
            "saturday": {"start": "09:00", "end": "19:00"},
            "sunday": {"start": "09:00", "end": "19:00"}
        }

    def _calculate_available_slots(
        self,
        working_hours: Dict[str, Any],
        appointments: List[Dict[str, Any]],
        target_date: date
    ) -> List[Dict[str, Any]]:
        """Calculate available time slots"""
        # Default schedule: 9 AM to 7 PM
        default_start = time(9, 0)
        default_end = time(19, 0)
        slot_duration = 30  # 30 minutes per slot

        # Get specific hours for the day of the week
        day_name = target_date.strftime("%A").lower()
        day_hours = working_hours.get(day_name, {})

        start_time = day_hours.get("start", default_start)
        end_time = day_hours.get("end", default_end)

        # Convert to time objects if they are strings
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, "%H:%M").time()
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time, "%H:%M").time()

        # Generate all possible slots
        all_slots = []
        current_time = start_time

        while current_time < end_time:
            slot_end = (datetime.combine(date.today(), current_time) +
                       timedelta(minutes=slot_duration)).time()

            if slot_end <= end_time:
                all_slots.append({
                    "start_time": current_time.strftime("%H:%M"),
                    "end_time": slot_end.strftime("%H:%M"),
                    "available": True
                })

            current_time = slot_end

        # Mark occupied slots
        for reservation in appointments:
            if reservation["status"] in ["pending", "confirmed"]:
                res_start = self._parse_time(reservation["start_time"])
                res_end = self._parse_time(reservation["end_time"])

                # Mark overlapping slots as unavailable
                for slot in all_slots:
                    slot_start = datetime.strptime(slot["start_time"], "%H:%M").time()
                    slot_end = datetime.strptime(slot["end_time"], "%H:%M").time()

                    if (slot_start < res_end and slot_end > res_start):
                        slot["available"] = False
                        slot["conflict_with"] = reservation.get("id")

        return all_slots

    def _parse_time(self, time_str: Union[str, time]) -> time:
        """Parse time string to time object"""
        if isinstance(time_str, time):
            return time_str

        try:
            # Try format with seconds first (HH:MM:SS)
            return datetime.strptime(time_str, "%H:%M:%S").time()
        except ValueError:
            # Fallback to format without seconds (HH:MM)
            return datetime.strptime(time_str, "%H:%M").time()

    async def _check_schedule_conflicts(
        self,
        resource_id: str,
        date: date,
        start_time: time,
        end_time: time,
        tenant_id: str = None,
        branch_id: str = None
    ) -> Dict[str, Any]:
        """Check for schedule conflicts"""
        try:
            # Build base query
            query = self.db.client.table("reservations").select(
                "id, start_time, end_time, customer_name, status"
            ).eq("resource_id", resource_id).eq("date", date.isoformat()).in_(
                "status", ["confirmed", "pending", "blocked"]
            )

            # Add additional filters if available
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if branch_id:
                query = query.eq("branch_id", branch_id)

            response = query.execute()

            conflicts = []
            for reservation in response.data:
                res_start = self._parse_time(reservation["start_time"])
                res_end = self._parse_time(reservation["end_time"])

                # Check for overlap
                if (start_time < res_end and end_time > res_start):
                    conflicts.append({
                        "reservation_id": reservation["id"],
                        "customer_name": reservation["customer_name"],
                        "start_time": reservation["start_time"],
                        "end_time": reservation["end_time"],
                        "status": reservation["status"]
                    })

            return {
                "has_conflicts": len(conflicts) > 0,
                "conflicts": conflicts
            }

        except Exception as e:
            logger.error(f"Error checking schedule conflicts: {e}")
            return {"has_conflicts": True, "error": str(e)}


class ClientService:
    """Service class for managing client data"""

    def __init__(self):
        self.db = DatabaseManager()

    async def find_by_phone(self, tenant_id: str, phone: str) -> Optional[Dict[str, Any]]:
        """Find client by phone number"""
        try:
            response = self.db.client.table("clients").select("*").eq(
                "tenant_id", tenant_id
            ).eq("phone", phone).execute()

            data = response.data or []
            return data[0] if data else None
        except Exception as e:
            logger.error(f"Error finding client by phone: {e}")
            return None

    async def get_or_create_client(
        self,
        tenant_id: str,
        branch_id: Optional[str],
        phone: str,
        last_call_sid: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get or create a client by phone number"""
        try:
            existing = await self.find_by_phone(tenant_id, phone)
            if existing:
                # Update existing client
                new_count = (existing.get("visit_count") or 0) + 1
                updates = {
                    "last_seen_at": datetime.now().isoformat(),
                    "visit_count": new_count,
                }
                if last_call_sid:
                    updates["last_call_sid"] = last_call_sid

                response = self.db.client.table("clients").update(updates).eq(
                    "id", existing["id"]
                ).execute()

                if response.data:
                    return response.data[0]
                return existing
            else:
                # Create new client
                payload = {
                    "tenant_id": tenant_id,
                    "branch_id": branch_id,
                    "phone": phone,
                    "first_seen_at": datetime.now().isoformat(),
                    "last_seen_at": datetime.now().isoformat(),
                    "visit_count": 1,
                }
                if last_call_sid:
                    payload["last_call_sid"] = last_call_sid

                response = self.db.client.table("clients").insert(payload).execute()
                if response.data:
                    return response.data[0]
                return None

        except Exception as e:
            logger.error(f"Error getting or creating client: {e}")
            return None

    async def update_client_profile(
        self,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        phone: Optional[str] = None,
        name: Optional[str] = None,
        email: Optional[str] = None,
        last_call_sid: Optional[str] = None,
        last_reservation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update client profile"""
        try:
            updates: Dict[str, Any] = {"updated_at": datetime.now().isoformat()}

            if name is not None:
                updates["name"] = name
            if email is not None:
                updates["email"] = email
            if last_call_sid is not None:
                updates["last_call_sid"] = last_call_sid
            if last_reservation_id is not None:
                updates["last_reservation_id"] = last_reservation_id
            if metadata is not None:
                updates["metadata"] = metadata

            query = self.db.client.table("clients").update(updates)
            if client_id:
                query = query.eq("id", client_id)
            elif tenant_id and phone:
                query = query.eq("tenant_id", tenant_id).eq("phone", phone)
            else:
                logger.error("update_client_profile requires client_id or (tenant_id and phone)")
                return False

            response = query.execute()
            return bool(response.data)

        except Exception as e:
            logger.error(f"Error updating client profile: {e}")
            return False


class AnalyticsService:
    """Service class for analytics and dashboard data"""

    def __init__(self):
        self.db = DatabaseManager()

    async def get_tenant_analytics(
        self,
        tenant_id: str,
        date_from: date = None,
        date_to: date = None
    ) -> Dict[str, Any]:
        """Get analytics for a tenant"""
        try:
            # Use last 30 days if no dates specified
            if not date_from:
                date_from = date.today() - timedelta(days=30)
            if not date_to:
                date_to = date.today()

            # Get reservations for the period
            reservations_response = self.db.client.table("reservations").select(
                "id, status, date, price, created_at"
            ).eq("tenant_id", tenant_id).gte(
                "date", date_from.isoformat()
            ).lte(
                "date", date_to.isoformat()
            ).execute()

            reservations = reservations_response.data

            # Calculate metrics
            total_reservations = len(reservations)
            confirmed_reservations = len([r for r in reservations if r["status"] == "confirmed"])
            cancelled_reservations = len([r for r in reservations if r["status"] == "cancelled"])
            pending_reservations = len([r for r in reservations if r["status"] == "pending"])

            # Calculate revenue
            total_revenue = sum([float(r["price"] or 0) for r in reservations if r["status"] == "confirmed"])

            # Reservations by date
            reservations_by_date = {}
            for reservation in reservations:
                res_date = reservation["date"]
                if res_date not in reservations_by_date:
                    reservations_by_date[res_date] = 0
                reservations_by_date[res_date] += 1

            return {
                "tenant_id": tenant_id,
                "period": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat()
                },
                "metrics": {
                    "total_reservations": total_reservations,
                    "confirmed_reservations": confirmed_reservations,
                    "cancelled_reservations": cancelled_reservations,
                    "pending_reservations": pending_reservations,
                    "total_revenue": total_revenue,
                    "conversion_rate": (confirmed_reservations / total_reservations * 100) if total_reservations > 0 else 0
                },
                "reservations_by_date": reservations_by_date,
                "reservations": reservations
            }

        except Exception as e:
            logger.error(f"Error getting tenant analytics: {e}")
            return {"error": str(e)}
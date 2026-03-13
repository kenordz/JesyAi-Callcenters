"""
Tenant Validation Service - Servicio OOP para validar argumentos de function calls según tenant
Maneja las reglas específicas de cada tenant/branch para recursos, servicios, horarios, etc.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class TenantValidationService:
    """
    Servicio para validar argumentos de function calls según configuración del tenant.
    Centraliza las reglas de negocio específicas de cada tenant/branch.
    """

    def __init__(self, database_manager=None):
        """
        Inicializa el servicio de validación.

        Args:
            database_manager: Instancia del DatabaseManager para obtener configuraciones
        """
        self.db = database_manager

        # Cache de configuraciones de tenant para evitar consultas repetidas
        self.tenant_configs_cache = {}

        logger.info("[TENANT-VALIDATION] ✅ Servicio inicializado")

    async def validate_staff_name(
        self,
        staff_name: str,
        tenant_id: str,
        branch_id: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Valida si el nombre del personal es válido para el tenant/branch.

        Args:
            staff_name: Nombre proporcionado por el cliente
            tenant_id: ID del tenant
            branch_id: ID de la branch

        Returns:
            Tuple[is_valid, validated_name_or_error, normalized_staff_id]
        """
        try:
            # Obtener configuración del tenant
            tenant_config = await self._get_tenant_config(tenant_id, branch_id)
            valid_staff = tenant_config.get("staff", [])

            if not staff_name:
                # Si no especificó personal, está OK (mostrará disponibilidad general)
                return True, "", None

            # Normalizar nombre para comparación (case insensitive)
            staff_name_lower = staff_name.lower().strip()

            # Buscar coincidencia exacta o parcial
            for staff_member in valid_staff:
                staff_db_name = staff_member.get("name", "").lower()
                staff_id = staff_member.get("id")

                # Coincidencia exacta
                if staff_name_lower == staff_db_name:
                    return True, staff_member.get("name"), staff_id

                # Coincidencia parcial (ej: "eder" encuentra "Eder García")
                if staff_name_lower in staff_db_name or staff_db_name in staff_name_lower:
                    return True, staff_member.get("name"), staff_id

            # No se encontró - sugerir alternativas
            staff_names = [s.get("name") for s in valid_staff if s.get("name")]
            suggestions = ", ".join(staff_names)

            error_msg = f"No conozco a {staff_name}. "
            if staff_names:
                error_msg += f"Nuestro personal disponible es: {suggestions}"
            else:
                error_msg += "No hay personal configurado para esta sucursal."

            return False, error_msg, None

        except Exception as e:
            logger.error(f"[TENANT-VALIDATION] Error validando staff: {e}")
            return False, f"Error verificando personal. Intenta de nuevo.", None

    async def validate_service(
        self,
        service: str,
        tenant_id: str,
        branch_id: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Valida si el servicio es válido para el tenant/branch.

        Args:
            service: Servicio proporcionado por el cliente
            tenant_id: ID del tenant
            branch_id: ID de la branch

        Returns:
            Tuple[is_valid, validated_service_or_error, service_details]
        """
        try:
            tenant_config = await self._get_tenant_config(tenant_id, branch_id)
            valid_services = tenant_config.get("services", [])

            if not service:
                # Servicio por defecto
                default_service = tenant_config.get("default_service", "Corte de cabello")
                return True, default_service, None

            service_lower = service.lower().strip()

            # Buscar servicio válido
            for svc in valid_services:
                svc_name = svc.get("name", "").lower()

                if service_lower == svc_name or service_lower in svc_name:
                    return True, svc.get("name"), svc

            # No encontrado - sugerir alternativas
            service_names = [s.get("name") for s in valid_services if s.get("name")]
            suggestions = ", ".join(service_names)

            error_msg = f"No ofrecemos '{service}'. "
            if service_names:
                error_msg += f"Nuestros servicios son: {suggestions}"
            else:
                error_msg += "Servicios no configurados para esta sucursal."

            return False, error_msg, None

        except Exception as e:
            logger.error(f"[TENANT-VALIDATION] Error validando servicio: {e}")
            return False, f"Error verificando servicio. Intenta de nuevo.", None

    async def get_business_hours(self, tenant_id: str, branch_id: str) -> Dict[str, Any]:
        """
        Obtiene los horarios de negocio del tenant/branch.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la branch

        Returns:
            Dict con horarios de negocio
        """
        try:
            tenant_config = await self._get_tenant_config(tenant_id, branch_id)
            return tenant_config.get("business_hours", {
                "monday": {"open": "10:30", "close": "20:30"},
                "tuesday": {"open": "10:30", "close": "20:30"},
                "wednesday": {"open": "10:30", "close": "20:30"},
                "thursday": {"open": "10:30", "close": "20:30"},
                "friday": {"open": "10:30", "close": "20:30"},
                "saturday": {"open": "10:00", "close": "17:00"},
                "sunday": {"open": None, "close": None}  # Cerrado
            })

        except Exception as e:
            logger.error(f"[TENANT-VALIDATION] Error obteniendo horarios: {e}")
            return {}

    async def _get_tenant_config(self, tenant_id: str, branch_id: str) -> Dict[str, Any]:
        """
        Obtiene la configuración completa del tenant/branch con cache.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la branch

        Returns:
            Dict con configuración del tenant
        """
        cache_key = f"{tenant_id}:{branch_id}"

        # Verificar cache
        if cache_key in self.tenant_configs_cache:
            return self.tenant_configs_cache[cache_key]

        try:
            # DEBUG: Verificar que el método existe
            logger.info(f"[TENANT-VALIDATION] 🔍 DatabaseManager methods: {[method for method in dir(self.db) if not method.startswith('_')]}")

            config = await self._load_tenant_config_from_db(tenant_id, branch_id)

            # Guardar en cache
            self.tenant_configs_cache[cache_key] = config

            return config

        except Exception as e:
            logger.error(f"[TENANT-VALIDATION] Error cargando config: {e}")
            return self._get_fallback_config(tenant_id, branch_id)

    async def _load_tenant_config_from_db(self, tenant_id: str, branch_id: str) -> Dict[str, Any]:
        """
        Carga configuración del tenant desde base de datos.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la branch

        Returns:
            Dict con configuración cargada
        """
        if not self.db:
            return self._get_fallback_config(tenant_id, branch_id)

        # TEMPORAL: Usar fallback hasta que el método se cargue
        if not hasattr(self.db, 'get_branch_staff'):
            logger.warning(f"[TENANT-VALIDATION] ⚠️ get_branch_staff no existe, usando fallback")
            return self._get_fallback_config(tenant_id, branch_id)

        # Obtener personal/recursos de la branch
        staff_response = await self.db.get_branch_staff(branch_id)
        staff_list = []

        if staff_response:
            for staff_member in staff_response:
                staff_list.append({
                    "id": staff_member.get("id"),
                    "name": staff_member.get("name"),
                    "role": staff_member.get("type", "staff"),  # type -> role
                    "active": staff_member.get("is_active", True)  # is_active -> active
                })

        # Obtener servicios del tenant
        services_response = await self.db.get_tenant_services(tenant_id)
        services_list = []

        if services_response:
            for service in services_response:
                services_list.append({
                    "id": service.get("id"),
                    "name": service.get("name"),
                    "price": service.get("price"),
                    "duration": service.get("duration", 30)
                })

        return {
            "tenant_id": tenant_id,
            "branch_id": branch_id,
            "staff": staff_list,
            "services": services_list,
            "default_service": "Corte de cabello",
            "business_hours": {
                "monday": {"open": "10:30", "close": "20:30"},
                "tuesday": {"open": "10:30", "close": "20:30"},
                "wednesday": {"open": "10:30", "close": "20:30"},
                "thursday": {"open": "10:30", "close": "20:30"},
                "friday": {"open": "10:30", "close": "20:30"},
                "saturday": {"open": "10:00", "close": "17:00"},
                "sunday": {"open": None, "close": None}
            }
        }

    def _get_fallback_config(self, tenant_id: str, branch_id: str) -> Dict[str, Any]:
        """
        Configuración de fallback en caso de error.
        """
        # Configuración genérica para todos los tenants
        return {
            "tenant_id": tenant_id,
            "branch_id": branch_id,
            "staff": [],
            "services": [{"name": "Servicio general", "price": 100, "duration": 30}],
            "default_service": "Servicio general",
            "business_hours": {
                "monday": {"open": "09:00", "close": "18:00"},
                "tuesday": {"open": "09:00", "close": "18:00"},
                "wednesday": {"open": "09:00", "close": "18:00"},
                "thursday": {"open": "09:00", "close": "18:00"},
                "friday": {"open": "09:00", "close": "18:00"},
                "saturday": {"open": None, "close": None},
                "sunday": {"open": None, "close": None}
            }
        }

    def clear_cache(self):
        """
        Limpia el cache de configuraciones.
        Útil cuando se actualizan configuraciones en runtime.
        """
        self.tenant_configs_cache.clear()
        logger.info("[TENANT-VALIDATION] Cache limpiado")
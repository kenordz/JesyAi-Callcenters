"""
ClientService - Gestión de clientes y tracking de visitas
Integrado con tabla clients de Supabase (estructura actual)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ClientService:
    """
    Servicio para gestión de clientes recurrentes.

    Funcionalidades:
    - Buscar clientes por teléfono
    - Crear nuevos clientes automáticamente
    - Actualizar información (nombre, email)
    - Incrementar contador de visitas
    - Tracking de última visita

    Usa la estructura actual de Supabase:
    - visit_count (contador de visitas)
    - first_seen_at / last_seen_at (timestamps)
    - branch_id (multitenant a nivel sucursal)
    - metadata (JSONB para datos adicionales)
    """

    def __init__(self, database_manager):
        """
        Inicializa el servicio con conexión a Supabase.

        Args:
            database_manager: Instancia del DatabaseManager
        """
        self.db = database_manager
        logger.info("[CLIENT-SERVICE] ✅ Servicio inicializado")

    async def get_client_by_phone(
        self,
        tenant_id: str,
        branch_id: str,
        phone: str
    ) -> Optional[Dict[str, Any]]:
        """
        Busca un cliente por teléfono en un tenant/branch específico.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la sucursal
            phone: Número de teléfono del cliente (formato: +52XXXXXXXXXX)

        Returns:
            Dict con info del cliente si existe, None si no existe
            {
                "id": "uuid",
                "name": "Eugenio",
                "phone": "+528111222951",
                "email": "email@example.com",
                "visit_count": 3,
                "first_seen_at": "2025-09-01T...",
                "last_seen_at": "2025-09-29T...",
                "metadata": {...}
            }
        """
        try:
            logger.info(f"[CLIENT-SERVICE] 🔍 Buscando cliente: {phone} en branch {branch_id[:8]}...")

            # Query a Supabase
            response = self.db.client.table("clients").select(
                "id, name, phone, email, visit_count, first_seen_at, last_seen_at, metadata, notes"
            ).eq("tenant_id", tenant_id).eq("branch_id", branch_id).eq("phone", phone).execute()

            if response.data and len(response.data) > 0:
                client = response.data[0]
                logger.info(
                    f"[CLIENT-SERVICE] ✅ Cliente encontrado: {client.get('name', 'Sin nombre')} "
                    f"- {client['visit_count']} visitas"
                )
                return client

            logger.info(f"[CLIENT-SERVICE] 🆕 Cliente no encontrado: {phone}")
            return None

        except Exception as e:
            logger.error(f"[CLIENT-SERVICE] ❌ Error buscando cliente: {e}", exc_info=True)
            return None

    async def get_or_create_client(
        self,
        tenant_id: str,
        branch_id: str,
        phone: str,
        name: Optional[str] = None,
        email: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene un cliente existente o crea uno nuevo.

        Este método se usa en post-llamada cuando se crea una reserva.

        Args:
            tenant_id: ID del tenant
            branch_id: ID de la sucursal
            phone: Teléfono del cliente
            name: Nombre del cliente (opcional, extraído del transcript)
            email: Email del cliente (opcional)

        Returns:
            Dict con:
            {
                "client_id": "uuid",
                "is_new": True/False,
                "visit_count": 3,
                "name": "Eugenio"
            }
        """
        try:
            logger.info(f"[CLIENT-SERVICE] 🔄 get_or_create_client llamado")
            logger.info(f"[CLIENT-SERVICE] 📞 phone recibido: '{phone}' (type: {type(phone).__name__})")
            logger.info(f"[CLIENT-SERVICE] 👤 name recibido: '{name}'")
            logger.info(f"[CLIENT-SERVICE] 🏢 tenant_id: {tenant_id[:8]}..., branch_id: {branch_id[:8]}...")

            # 1. Buscar si existe
            existing = await self.get_client_by_phone(tenant_id, branch_id, phone)

            if existing:
                # Cliente existente
                logger.info(
                    f"[CLIENT-SERVICE] 👤 Cliente existente: {existing.get('name')} "
                    f"- {existing['visit_count']} visitas"
                )

                # Si el nombre nuevo es más completo, actualizar
                if name and (not existing.get('name') or len(name) > len(existing.get('name', ''))):
                    logger.info(f"[CLIENT-SERVICE] 📝 Actualizando nombre: '{existing.get('name')}' → '{name}'")
                    await self._update_client_name(existing['id'], name)
                    existing['name'] = name

                return {
                    "client_id": existing["id"],
                    "is_new": False,
                    "visit_count": existing.get("visit_count", 0),
                    "name": existing.get("name")
                }

            # 2. Cliente nuevo - crear
            logger.info(f"[CLIENT-SERVICE] 🆕 Creando nuevo cliente: {phone} - {name or 'Sin nombre'}")

            new_client_data = {
                "tenant_id": tenant_id,
                "branch_id": branch_id,
                "phone": phone,
                "name": name,
                "email": email,
                "visit_count": 0,  # Se incrementará al crear reserva
                "first_seen_at": datetime.utcnow().isoformat(),
                "last_seen_at": datetime.utcnow().isoformat(),
                "metadata": {}
            }

            logger.info(f"[CLIENT-SERVICE-DEBUG] 📝 Datos a insertar en Supabase:")
            logger.info(f"[CLIENT-SERVICE-DEBUG]   phone: '{new_client_data['phone']}'")
            logger.info(f"[CLIENT-SERVICE-DEBUG]   name: '{new_client_data['name']}'")
            logger.info(f"[CLIENT-SERVICE-DEBUG]   tenant_id: {new_client_data['tenant_id'][:8]}...")
            logger.info(f"[CLIENT-SERVICE-DEBUG]   branch_id: {new_client_data['branch_id'][:8]}...")

            response = self.db.client.table("clients").insert(new_client_data).execute()

            if response.data and len(response.data) > 0:
                new_client = response.data[0]
                logger.info(f"[CLIENT-SERVICE] ✅ Cliente creado exitosamente: {new_client['id']}")

                return {
                    "client_id": new_client["id"],
                    "is_new": True,
                    "visit_count": 0,
                    "name": name
                }
            else:
                logger.error("[CLIENT-SERVICE] ❌ No se pudo crear cliente (response vacía)")
                return None

        except Exception as e:
            logger.error(f"[CLIENT-SERVICE] ❌ Error en get_or_create_client: {e}", exc_info=True)
            return None

    async def increment_visit_count(
        self,
        client_id: str,
        call_id: Optional[str] = None,
        reservation_id: Optional[str] = None
    ) -> bool:
        """
        Incrementa el contador de visitas del cliente.

        Se llama después de crear una reserva exitosamente.

        Args:
            client_id: ID del cliente
            call_id: ID de la llamada (opcional, para tracking)
            reservation_id: ID de la reserva creada (opcional)

        Returns:
            True si se incrementó exitosamente, False si hubo error
        """
        try:
            logger.info(f"[CLIENT-SERVICE] 📈 Incrementando visit_count para client: {client_id[:8]}...")

            # PASO 1: Obtener visit_count actual
            current_response = self.db.client.table("clients").select("visit_count").eq("id", client_id).execute()

            if not current_response.data or len(current_response.data) == 0:
                logger.error(f"[CLIENT-SERVICE] ❌ Cliente no encontrado: {client_id[:8]}")
                return False

            current_count = current_response.data[0].get("visit_count", 0)
            new_count = current_count + 1

            logger.info(f"[CLIENT-SERVICE] 📊 Visit count actual: {current_count} → nuevo: {new_count}")

            # PASO 2: Actualizar con el nuevo valor
            update_data = {
                "visit_count": new_count,
                "last_seen_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            # Agregar tracking opcional
            if call_id:
                update_data["last_call_sid"] = call_id
            if reservation_id:
                update_data["last_reservation_id"] = reservation_id

            response = self.db.client.table("clients").update(update_data).eq("id", client_id).execute()

            if response.data and len(response.data) > 0:
                logger.info(f"[CLIENT-SERVICE] ✅ Visit count incrementado exitosamente: {current_count} → {new_count}")
                return True
            else:
                logger.warning("[CLIENT-SERVICE] ⚠️ No se pudo incrementar visit_count (update sin datos)")
                return False

        except Exception as e:
            logger.error(f"[CLIENT-SERVICE] ❌ Error incrementando visit_count: {e}", exc_info=True)
            return False

    async def _update_client_name(self, client_id: str, name: str) -> bool:
        """
        Actualiza el nombre de un cliente (método interno).

        Args:
            client_id: ID del cliente
            name: Nuevo nombre

        Returns:
            True si se actualizó, False si hubo error
        """
        try:
            response = self.db.client.table("clients").update({
                "name": name,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", client_id).execute()

            return bool(response.data)

        except Exception as e:
            logger.error(f"[CLIENT-SERVICE] ❌ Error actualizando nombre: {e}")
            return False

    async def get_client_reservations(
        self,
        client_id: str,
        limit: int = 5,
        include_cancelled: bool = False
    ) -> list:
        """
        Obtiene las últimas reservas de un cliente.

        Útil para:
        - Mostrar historial en conversación
        - Detectar patrones (siempre agenda con Eder)
        - Personalización futura

        Args:
            client_id: ID del cliente
            limit: Número máximo de reservas a retornar
            include_cancelled: Si incluir reservas canceladas

        Returns:
            Lista de reservas ordenadas por fecha (más reciente primero)
        """
        try:
            query = self.db.client.table("reservations").select(
                "id, date, start_time, end_time, status, resource_id, service_id, notes"
            ).eq("client_id", client_id).order("date", desc=True).limit(limit)

            if not include_cancelled:
                query = query.neq("status", "cancelled")

            response = await query.execute()

            if response.data:
                logger.info(f"[CLIENT-SERVICE] 📋 {len(response.data)} reservas encontradas para client {client_id[:8]}")
                return response.data

            return []

        except Exception as e:
            logger.error(f"[CLIENT-SERVICE] ❌ Error obteniendo reservas: {e}")
            return []

    def build_client_context_for_instructions(
        self,
        client_info: Optional[Dict[str, Any]],
        phone: str,
        greeting: str = "¡Hola! ¿En qué puedo ayudarte hoy?"
    ) -> str:
        """
        Construye el contexto del cliente para agregar a las instructions de Jessica.

        Este texto se agrega al accept call para que Jessica conozca al cliente.

        Args:
            client_info: Información del cliente (o None si es nuevo)
            phone: Teléfono del cliente
            greeting: Saludo del negocio desde branch_ai_config (multitenant)

        Returns:
            String formateado para agregar a instructions
        """
        if not client_info:
            return f"""

📞 CLIENTE NUEVO (Primera llamada):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 Teléfono: {phone}
🆕 Estado: Primera vez que llama al sistema

🎯 INSTRUCCIONES PARA CLIENTE NUEVO:

1️⃣ SALUDO INICIAL:
   Usa el saludo configurado del negocio (no tienes su nombre todavía)

2️⃣ PIDE EL NOMBRE CUANDO SEA NECESARIO:
   - Si el cliente quiere agendar una cita, pregunta su nombre
   - Di: "¿Me podrías decir tu nombre completo, por favor?"
   - Úsalo después de recibirlo: "Perfecto [nombre], tu cita está confirmada..."

3️⃣ ACTITUD:
   - Bríndales especial atención
   - NO menciones que es "cliente nuevo"
   - Solo sé amable y profesional

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        visits = client_info.get('visit_count', 0)
        name = client_info.get('name', '')

        if visits == 0:
            # Cliente registrado pero sin visitas completadas
            if name:
                # Extraer la parte del saludo antes de la coma para personalizar
                greeting_base = greeting.split(',')[0] if ',' in greeting else greeting.rstrip('?¿')

                # 🆕 Extraer PRIMER NOMBRE para conversación natural
                first_name = name.split()[0] if name else name

                return f"""

🚨 ¡ATENCIÓN! - CLIENTE REGISTRADO - PRIORIDAD MÁXIMA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 NOMBRE COMPLETO: {name}
👤 USA EN CONVERSACIÓN: {first_name} (solo el primer nombre)
📞 Teléfono: {phone}
🏷️ Estado: Primera visita pendiente (ya llamó antes)

🎯 INSTRUCCIONES OBLIGATORIAS PARA ESTE CLIENTE:

1️⃣ SALUDO INICIAL:
   Cuando respondas la llamada, di EXACTAMENTE:
   "¡Hola {first_name}! {greeting_base}, ¿en qué puedo ayudarte hoy?"

   IMPORTANTE: Usa solo "{first_name}" (primer nombre), NO el nombre completo.

2️⃣ ⛔ NO PIDAS EL NOMBRE - YA LO CONOCES:
   - El nombre completo del cliente es: {name}
   - Pero en la conversación usa SOLO: {first_name}
   - NO preguntes "¿cuál es tu nombre?"
   - NO digas "necesito tu nombre"
   - YA TIENES ESTA INFORMACIÓN

3️⃣ USA EL PRIMER NOMBRE DURANTE LA CONVERSACIÓN:
   - "Perfecto {first_name}, déjame verificar..."
   - "Claro {first_name}, tu cita está confirmada..."
   - "¡Listo {first_name}!"
   - SIEMPRE usa "{first_name}", NO "{name}"

4️⃣ CONTEXTO:
   - Este cliente ya llamó antes y tiene una cita agendada
   - Es su primera visita (aún no ha venido físicamente)
   - Trátalo con familiaridad pero profesionalismo

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            else:
                return f"""

📞 CLIENTE REGISTRADO (Primera visita):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 Teléfono: {phone}
🏷️ Estado: Ya llamó antes pero aún no ha venido

🎯 INSTRUCCIONES:

1️⃣ SALUDO INICIAL:
   Usa el saludo configurado del negocio (no tienes su nombre todavía)

2️⃣ PIDE EL NOMBRE:
   - Pregunta su nombre amablemente cuando quiera agendar
   - Di: "¿Me podrías decir tu nombre completo, por favor?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # Cliente recurrente
        visit_text = "vez" if visits == 1 else "veces"

        # Extraer la parte del saludo antes de la coma para personalizar
        greeting_base = greeting.split(',')[0] if ',' in greeting else greeting.rstrip('?¿')

        # 🆕 Extraer PRIMER NOMBRE para conversación natural
        first_name = name.split()[0] if name else (name if name else 'Cliente conocido')

        return f"""

🚨 ¡ATENCIÓN! - CLIENTE VIP RECURRENTE ⭐ - PRIORIDAD MÁXIMA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 NOMBRE COMPLETO: {name if name else 'Cliente conocido'}
👤 USA EN CONVERSACIÓN: {first_name} (solo el primer nombre)
📞 Teléfono: {phone}
🏆 Visitas completadas: {visits} {visit_text}
⭐ Estado: Cliente VIP de confianza

🎯 INSTRUCCIONES OBLIGATORIAS PARA ESTE CLIENTE VIP:

1️⃣ SALUDO INICIAL:
   Cuando respondas la llamada, di EXACTAMENTE:
   "¡Hola {first_name}! {greeting_base}, ¿en qué puedo ayudarte hoy?"

   IMPORTANTE: Usa solo "{first_name}" (primer nombre), NO el nombre completo.

2️⃣ ⛔ NO PIDAS EL NOMBRE - YA LO CONOCES:
   - El nombre completo del cliente es: {name if name else 'conocido'}
   - Pero en la conversación usa SOLO: {first_name}
   - NO preguntes "¿cuál es tu nombre?"
   - NO digas "necesito tu nombre"
   - YA TIENES ESTA INFORMACIÓN

3️⃣ USA EL PRIMER NOMBRE DURANTE LA CONVERSACIÓN:
   - "Perfecto {first_name}, déjame verificar..."
   - "Claro {first_name}, tu cita está confirmada..."
   - "¡Qué bueno verte de nuevo, {first_name}!"
   - SIEMPRE usa "{first_name}", NO el nombre completo

4️⃣ PERSONALIZACIÓN VIP:
   - Este cliente ha venido {visits} {visit_text}
   - Demuestra que lo conoces y aprecias su lealtad
   - Ofrece: "¿Quieres agendar como siempre?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

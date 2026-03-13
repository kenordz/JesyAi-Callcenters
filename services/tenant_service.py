"""
TenantService - Professional OOP approach for multi-tenant configuration
Handles all tenant, branch, and AI configuration management
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from core.database import DatabaseManager

logger = logging.getLogger(__name__)


class TenantService:
    """
    Service class for managing multi-tenant configuration
    Clean, efficient, and scalable approach
    """

    def __init__(self, database_manager=None):
        self.db = database_manager or DatabaseManager()
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

    async def get_tenant_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get tenant configuration by slug"""
        try:
            response = self.db.client.table('tenants').select('*').eq(
                'slug', slug
            ).eq('status', 'active').single().execute()

            if response.data:
                return response.data
            return None
        except Exception as e:
            logger.error(f"Error getting tenant by slug {slug}: {e}")
            return None

    async def get_branch_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get branch by phone number (key for multitenant detection)"""
        return await self.db.get_branch_by_phone(phone_number)

    async def get_tenant_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get tenant by phone number via branch lookup"""
        try:
            branch = await self.get_branch_by_phone(phone_number)
            if branch and branch.get('tenant_id'):
                return await self.db.get_tenant_by_id(branch['tenant_id'])
            return None
        except Exception as e:
            logger.error(f"Error getting tenant by phone {phone_number}: {e}")
            return None

    async def get_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get complete tenant configuration"""
        cache_key = f"tenant_config_{tenant_id}"

        # Check cache first
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if (datetime.now() - timestamp).seconds < self.cache_ttl:
                return cached_data

        try:
            response = self.db.client.table('tenants').select('*').eq(
                'id', tenant_id
            ).single().execute()

            if response.data:
                tenant_data = response.data

                config = {
                    'tenant_id': tenant_id,
                    'name': tenant_data.get('name'),
                    'slug': tenant_data.get('slug'),
                    'business_type': tenant_data.get('business_type'),
                    'business_config': tenant_data.get('business_config', {}),
                    'ai_config': tenant_data.get('ai_config', {}),
                    'primary_color': tenant_data.get('primary_color', '#2563eb'),
                    'secondary_color': tenant_data.get('secondary_color', '#1e40af'),
                    'timezone': tenant_data.get('business_config', {}).get('timezone', 'America/Mexico_City'),
                    'currency': tenant_data.get('business_config', {}).get('currency', 'MXN')
                }

                # Cache the result
                self.cache[cache_key] = (config, datetime.now())
                return config

            return {}
        except Exception as e:
            logger.error(f"Error getting tenant config {tenant_id}: {e}")
            return {}


    async def get_business_hours(self, tenant_id: str, date: datetime = None) -> Dict[str, Any]:
        """Get tenant working hours"""
        config = await self.get_tenant_config(tenant_id)
        business_config = config.get('business_config', {})
        return business_config.get('working_hours', {})

    async def get_slot_duration(self, tenant_id: str) -> int:
        """Get tenant slot duration"""
        config = await self.get_tenant_config(tenant_id)
        business_config = config.get('business_config', {})
        return business_config.get('slot_duration', 30)
    async def get_ai_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant AI configuration"""
        config = await self.get_tenant_config(tenant_id)
        return config.get('ai_config', {})

    async def get_branch_ai_config(self, branch_id: str) -> Dict[str, Any]:
        """Get branch-specific AI configuration"""
        try:
            response = self.db.client.table('branches').select('ai_config').eq(
                'id', branch_id
            ).single().execute()

            if response.data and response.data.get('ai_config'):
                return response.data['ai_config']
            return {}
        except Exception as e:
            logger.error(f"Error getting branch AI config {branch_id}: {e}")
            return {}

    async def get_services(self, tenant_id: str, branch_id: str = None) -> List[Dict[str, Any]]:
        """Get tenant services"""
        try:
            response = self.db.client.table('services').select('*').eq(
                'tenant_id', tenant_id
            ).eq('is_active', True).execute()

            logger.info(f"[SERVICES] Found {len(response.data) if response.data else 0} services for tenant {tenant_id}")
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting services for tenant {tenant_id}: {e}")
            return []

    async def get_resources(self, tenant_id: str, branch_id: str = None, resource_type: str = None) -> List[Dict[str, Any]]:
        """Get tenant resources (staff, equipment, etc.)"""
        try:
            logger.info(f"[RESOURCES] Searching: tenant_id={tenant_id}, branch_id={branch_id}, type={resource_type}")

            query = self.db.client.table('resources').select('*').eq(
                'tenant_id', tenant_id
            ).eq('is_active', True)

            if branch_id:
                query = query.eq('branch_id', branch_id)
            if resource_type:
                query = query.eq('type', resource_type)

            response = query.execute()
            logger.info(f"[RESOURCES] Found {len(response.data) if response.data else 0} resources")
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting resources for tenant {tenant_id}: {e}")
            return []

    async def get_branches(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Get tenant branches"""
        try:
            response = self.db.client.table('branches').select('*').eq(
                'tenant_id', tenant_id
            ).eq('is_active', True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting branches for tenant {tenant_id}: {e}")
            return []

    def get_resource_label(self, business_type: str, resource_type: str = 'staff') -> str:
        """Get appropriate resource label by business type"""
        labels = {
            'barbershop': {
                'staff': 'Barbero',
                'chair': 'Silla',
                'equipment': 'Equipo'
            },
            'restaurant': {
                'table': 'Mesa',
                'room': 'Sala Privada',
                'staff': 'Mesero'
            },
            'clinic': {
                'staff': 'Doctor',
                'room': 'Consultorio',
                'equipment': 'Equipo Médico'
            },
            'salon': {
                'staff': 'Estilista',
                'chair': 'Silla',
                'equipment': 'Equipo'
            }
        }

        return labels.get(business_type, {}).get(resource_type, 'Recurso')

    def get_service_label(self, business_type: str) -> str:
        """Get appropriate service label by business type"""
        labels = {
            'barbershop': 'Servicio',
            'restaurant': 'Menú',
            'clinic': 'Consulta',
            'salon': 'Servicio',
            'spa': 'Tratamiento'
        }
        return labels.get(business_type, 'Servicio')

    def get_reservation_label(self, business_type: str) -> str:
        """Get appropriate reservation label by business type"""
        labels = {
            'barbershop': 'Cita',
            'restaurant': 'Reserva',
            'clinic': 'Cita',
            'salon': 'Cita',
            'spa': 'Cita'
        }
        return labels.get(business_type, 'Reserva')

    def get_ai_greeting(self, tenant_config: Dict[str, Any]) -> str:
        """Get AI personalized greeting"""
        ai_config = tenant_config.get('ai_config', {})
        return ai_config.get('greeting', '¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte?')

    def get_ai_farewell(self, tenant_config: Dict[str, Any]) -> str:
        """Get AI personalized farewell"""
        ai_config = tenant_config.get('ai_config', {})
        return ai_config.get('farewell', '¡Gracias por tu llamada! Que tengas un excelente día.')

    def get_ai_voice(self, tenant_config: Dict[str, Any]) -> str:
        """Get configured AI voice"""
        ai_config = tenant_config.get('ai_config', {})
        return ai_config.get('voice', 'sage')

    def get_ai_language(self, tenant_config: Dict[str, Any]) -> str:
        """Get configured AI language"""
        ai_config = tenant_config.get('ai_config', {})
        return ai_config.get('language', 'es')

    def get_quick_intents(self, tenant_config: Dict[str, Any]) -> Dict[str, str]:
        """Get configured quick intents"""
        ai_config = tenant_config.get('ai_config', {})
        return ai_config.get('quick_intents', {})

    async def build_dynamic_prompt(self, branch_id: str) -> str:
        """Build dynamic prompt using branch AI configuration"""
        try:
            # Get branch AI config
            branch_ai_config = await self.get_branch_ai_config(branch_id)

            if not branch_ai_config or not branch_ai_config.get('system_prompt'):
                logger.warning(f"No system_prompt in branch {branch_id} ai_config")
                return self._get_fallback_prompt()

            # Get branch data for additional context
            branch_response = self.db.client.table('branches').select('*').eq(
                'id', branch_id
            ).single().execute()

            if not branch_response.data:
                logger.warning(f"Branch {branch_id} not found")
                return self._get_fallback_prompt()

            branch_data = branch_response.data
            tenant_id = branch_data['tenant_id']

            # Get services for this branch
            services = await self.get_services(tenant_id, branch_id)

            # Build dynamic prompt using existing configuration
            base_prompt = branch_ai_config['system_prompt']

            # Add natural conversation enhancements
            natural_gestures = self._get_natural_conversation_instructions()
            base_prompt += natural_gestures

            # Add service information
            if services:
                service_info = []
                for service in services:
                    price = service.get('price', 0)
                    name = service.get('name', '')
                    if price and name:
                        service_info.append(f"{name} - ${price}")

                if service_info:
                    services_text = ", ".join(service_info)
                    base_prompt += f"\n\nServicios disponibles: {services_text}"

            # Add voice and emotion adjustments
            base_prompt += self._get_voice_emotion_instructions()

            logger.info(f"[DYNAMIC-PROMPT] Prompt built for branch {branch_id}")
            return base_prompt

        except Exception as e:
            logger.error(f"Error building dynamic prompt for branch {branch_id}: {e}")
            return self._get_fallback_prompt()

    def _get_natural_conversation_instructions(self) -> str:
        """Get natural conversation instructions"""
        return """

🎭 INSTRUCCIONES CRÍTICAS DE VOZ Y NATURALIDAD - HABLA COMO HUMANA REAL:

🗣️ VARIACIÓN DE TONOS OBLIGATORIA:
- USA VOZ ALEGRE cuando saludes: "¡Hola! ¡Qué gusto escucharte!" (tono alto y animado)
- BAJA EL TONO cuando escuches: "Mmm, a ver..." (tono pensativo)
- SUBE LA VOZ con entusiasmo: "¡Perfecto!" (tono emocionado)
- HAZ PAUSAS NATURALES: "Pues mira... [pausa] déjame checarte..." (respiraciones)
- ALARGA PALABRAS cuando pienses: "Esteee... déjame ver..."
- RÍE SUAVEMENTE cuando sea apropiado

💬 EXPRESIONES NATURALES:
- "Ay, qué padre" / "¡Órale, qué bien!" / "Híjole" / "Ándale pues"
- "A ver, pérame tantito..." / "Ahorita te checo eso"
- "¿Mande?" (cuando no escuches bien)
- "¿Cómo ves?" / "¿Sale?" / "¿Te late?"

🌟 PERSONALIDAD CÁLIDA:
- SONRÍE mientras hablas (se nota en la voz)
- Muestra EMOCIÓN real: alegría, sorpresa, empatía
- Haz COMENTARIOS casuales cuando sea apropiado
- Sé AMIGABLE pero profesional

⚠️ NUNCA suenes robótica, monótona o sin emoción. SIEMPRE varía tonos, ritmo y emoción."""


    def _get_voice_emotion_instructions(self) -> str:
        """Get voice and emotion instructions"""
        return """

🎵 RITMO Y EMOCIÓN:
- Habla con un tono un poco más emocionado (alegre y cálido).
- Usa un ritmo ligeramente más rápido (≈1.25x) para sonar ágil.
- Prefiere oraciones cortas y evita pausas largas."""

    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if dynamic configuration fails"""
        return """Eres un asistente virtual profesional para un centro de llamadas.

COMPORTAMIENTO NATURAL:
- Saluda amigablemente y pregunta en qué puedes ayudar
- Mantén conversación natural y profesional
- Escucha activamente las necesidades del cliente

⚠️ REGLAS CRÍTICAS:
- NUNCA digas información no confirmada por el sistema
- Si no tienes información confirmada, di: "Déjame verificar eso para ti"
- NO inventes o asumas información
- Solo usa información que el sistema te proporcione explícitamente

Sé cálido, profesional y conversacional."""

    def clear_cache(self, tenant_id: str = None):
        """Clear configuration cache"""
        if tenant_id:
            cache_key = f"tenant_config_{tenant_id}"
            if cache_key in self.cache:
                del self.cache[cache_key]
        else:
            self.cache.clear()


# Singleton instance for global access
_tenant_service_instance = None


def get_tenant_service() -> TenantService:
    """Get singleton instance of TenantService"""
    global _tenant_service_instance
    if _tenant_service_instance is None:
        _tenant_service_instance = TenantService()
    return _tenant_service_instance
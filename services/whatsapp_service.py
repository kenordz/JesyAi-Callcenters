"""
WhatsApp Notification Service using Twilio
Handles confirmations and reminders
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)

# WhatsApp Template Content SIDs (Twilio approved templates)
BARBER_NEW_APPOINTMENT_TEMPLATE_SID = "HX3ecf7e44f3c651492d1467d27bc88c83"
BARBER_CANCELLATION_TEMPLATE_SID = "HX20e15482ccd6465d00dbe97f42711a0e"
REVIEW_REQUEST_TEMPLATE_SID = "HX5f1f5a774ee14e87d58366c3f0212c18"


class WhatsAppService:
    """
    Service for sending WhatsApp messages via Twilio
    """

    def __init__(self, db_manager=None):
        """
        Initialize WhatsApp service

        Args:
            db_manager: Database manager instance (for getting tenant config)
        """
        self.db = db_manager

        # Default Twilio config (can be overridden per tenant)
        self.default_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.default_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.default_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

        # Initialize default client
        if self.default_account_sid and self.default_auth_token:
            self.default_client = Client(self.default_account_sid, self.default_auth_token)
        else:
            self.default_client = None
            logger.warning("[WHATSAPP] ⚠️ No default Twilio credentials found")

    def _normalize_phone(self, phone: str, default_country_code: str = "+52") -> str:
        """
        Normaliza número de teléfono removiendo espacios y agregando código de país
        '56 5959 9413' -> '+525659599413'
        '8111234567' -> '+528111234567'
        '+528111234567' -> '+528111234567'
        """
        if not phone:
            return ""

        import re
        # Remover espacios, guiones, paréntesis
        cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)

        # Si ya tiene + al inicio, devolverlo limpio
        if cleaned.startswith('+'):
            return cleaned

        # Si empieza con código de país sin +
        if cleaned.startswith('52') and len(cleaned) >= 12:
            return f"+{cleaned}"

        # Si es número de 10 dígitos, agregar código de país
        if len(cleaned) == 10:
            return f"{default_country_code}{cleaned}"

        # Fallback: agregar código de país
        return f"{default_country_code}{cleaned}"

    async def send_confirmation(
        self,
        client_phone: str,
        reservation_data: Dict,
        tenant_config: Optional[Dict] = None
    ) -> Dict:
        """
        Send confirmation WhatsApp after booking

        Args:
            client_phone: Client's phone number (+52...)
            reservation_data: Dict with reservation details
            tenant_config: Optional tenant-specific config

        Returns:
            Dict with success status and message_sid
        """
        try:
            # Get Twilio client (tenant-specific or default)
            client, from_number = self._get_client_and_number(tenant_config)

            if not client:
                logger.error("[WHATSAPP] ❌ No Twilio client available")
                return {"success": False, "error": "Twilio not configured"}

            # Ensure phone has whatsapp: prefix
            to_number = f"whatsapp:{client_phone}" if not client_phone.startswith("whatsapp:") else client_phone

            # Check if template is available
            template_sid = os.getenv("WHATSAPP_TEMPLATE_SID", "")

            if template_sid:
                # Use approved template (works always, no 24h window restriction)
                logger.info(f"[WHATSAPP] 📤 Enviando confirmación con TEMPLATE a {client_phone}")
                logger.info(f"[WHATSAPP-DEBUG] Template SID: {template_sid}")

                # Build template variables
                template_variables = self._build_template_variables(
                    reservation_data,
                    tenant_config
                )

                logger.info(f"[WHATSAPP-DEBUG] Template variables: {list(template_variables.keys())}")

                # Send with template
                # Twilio requiere content_variables como JSON string, no dict
                message = client.messages.create(
                    from_=f"whatsapp:{from_number}",
                    to=to_number,
                    content_sid=template_sid,
                    content_variables=json.dumps(template_variables)
                )
            else:
                # Fallback: Use freeform text (only works within 24h window)
                logger.info(f"[WHATSAPP] 📤 Enviando confirmación con TEXTO LIBRE a {client_phone}")
                logger.warning(f"[WHATSAPP] ⚠️ No template configured, using freeform (24h window required)")

                message_body = self._build_confirmation_message(
                    reservation_data,
                    tenant_config
                )

                logger.info(f"[WHATSAPP-DEBUG] Message length: {len(message_body)} chars")

                # Send with freeform text
                message = client.messages.create(
                    from_=f"whatsapp:{from_number}",
                    to=to_number,
                    body=message_body
                )

            logger.info(f"[WHATSAPP] ✅ Confirmación enviada: {message.sid}")

            return {
                "success": True,
                "message_sid": message.sid,
                "status": message.status
            }

        except TwilioRestException as e:
            logger.error(f"[WHATSAPP] ❌ Twilio error: {e.msg} (code: {e.code})")
            return {
                "success": False,
                "error": e.msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"[WHATSAPP] ❌ Error inesperado: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def send_reminder(
        self,
        client_phone: str,
        reservation_data: Dict,
        tenant_config: Optional[Dict] = None
    ) -> Dict:
        """
        Send reminder WhatsApp 1 hour before appointment

        Args:
            client_phone: Client's phone number
            reservation_data: Dict with reservation details
            tenant_config: Optional tenant-specific config

        Returns:
            Dict with success status
        """
        try:
            client, from_number = self._get_client_and_number(tenant_config)

            if not client:
                return {"success": False, "error": "Twilio not configured"}

            message_body = self._build_reminder_message(
                reservation_data,
                tenant_config
            )

            to_number = f"whatsapp:{client_phone}" if not client_phone.startswith("whatsapp:") else client_phone

            logger.info(f"[WHATSAPP] 🔔 Enviando recordatorio a {client_phone}")

            message = client.messages.create(
                from_=f"whatsapp:{from_number}",
                to=to_number,
                body=message_body
            )

            logger.info(f"[WHATSAPP] ✅ Recordatorio enviado: {message.sid}")

            return {
                "success": True,
                "message_sid": message.sid,
                "status": message.status
            }

        except TwilioRestException as e:
            logger.error(f"[WHATSAPP] ❌ Twilio error: {e.msg}")
            return {"success": False, "error": e.msg}
        except Exception as e:
            logger.error(f"[WHATSAPP] ❌ Error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _get_client_and_number(self, tenant_config: Optional[Dict]) -> tuple:
        """
        Get Twilio client and phone number (tenant-specific or default)

        Returns:
            (twilio_client, phone_number)
        """
        if tenant_config and tenant_config.get("twilio_account_sid"):
            # Tenant-specific config
            client = Client(
                tenant_config["twilio_account_sid"],
                tenant_config["twilio_auth_token"]
            )
            number = tenant_config["twilio_whatsapp_number"]
            logger.debug(f"[WHATSAPP] Using tenant-specific Twilio config")
        else:
            # Default config
            client = self.default_client
            number = self.default_whatsapp_number
            logger.debug(f"[WHATSAPP] Using default Twilio config")

        return client, number

    def _build_template_variables(
        self,
        reservation_data: Dict,
        tenant_config: Optional[Dict]
    ) -> Dict[str, str]:
        """
        Build template variables for WhatsApp template

        Template structure:
        {{1}} = Business name
        {{2}} = Date (formatted)
        {{3}} = Time
        {{4}} = Barber/Professional name
        {{5}} = Service name
        {{6}} = Price
        {{7}} = Confirmation code
        {{8}} = Business phone
        """
        # Format date
        try:
            date_str = reservation_data.get('date', '')
            if isinstance(date_str, str):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                date_obj = date_str

            day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

            day_name = day_names[date_obj.weekday()]
            formatted_date = f"{day_name} {date_obj.day} de {month_names[date_obj.month - 1]}"
        except:
            formatted_date = reservation_data.get('date', 'Fecha no disponible')

        # Format time (remove seconds if present)
        time_str = reservation_data.get('start_time', '')
        if len(time_str) > 5:
            time_str = time_str[:5]  # "19:00:00" -> "19:00"

        # Get business info
        business_name = tenant_config.get('business_name', 'JesyAI') if tenant_config else 'JesyAI'
        business_phone = tenant_config.get('business_phone', '') if tenant_config else ''

        # Build variables dictionary
        variables = {
            "1": business_name,
            "2": formatted_date,
            "3": time_str,
            "4": reservation_data.get('barber_name', 'Profesional'),
            "5": reservation_data.get('service_name', 'Servicio'),
            "6": str(reservation_data.get('price', 0)),
            "7": reservation_data.get('confirmation_code', 'N/A'),
            "8": business_phone if business_phone else 'N/A'
        }

        return variables

    def _build_confirmation_message(
        self,
        reservation_data: Dict,
        tenant_config: Optional[Dict]
    ) -> str:
        """
        Build confirmation message body (fallback for freeform text)
        """
        # Parse date for nice formatting
        try:
            date_str = reservation_data.get('date', '')
            if isinstance(date_str, str):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                date_obj = date_str

            day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

            day_name = day_names[date_obj.weekday()]
            month_name = month_names[date_obj.month - 1]
            formatted_date = f"{day_name} {date_obj.day} de {month_name}"
        except:
            formatted_date = reservation_data.get('date', 'Fecha no disponible')

        # Format time (remove seconds if present)
        time_str = reservation_data.get('start_time', '')
        if len(time_str) > 5:
            time_str = time_str[:5]  # "19:00:00" -> "19:00"

        # Get business info
        business_name = tenant_config.get('business_name', 'JesyAI') if tenant_config else 'JesyAI'
        business_phone = tenant_config.get('business_phone', '') if tenant_config else ''

        # Build message
        message = f"""✅ ¡Cita confirmada en {business_name}!

📅 {formatted_date}
⏰ {time_str}
💈 {reservation_data.get('barber_name', 'Profesional')}
🔹 {reservation_data.get('service_name', 'Servicio')} (${reservation_data.get('price', 0)})

Código: {reservation_data.get('confirmation_code', 'N/A')}"""

        if business_phone:
            message += f"\n\nPara cambios: {business_phone}"

        message += f"\n\n- {business_name}"

        return message

    def _build_reminder_message(
        self,
        reservation_data: Dict,
        tenant_config: Optional[Dict]
    ) -> str:
        """
        Build reminder message body
        """
        time_str = reservation_data.get('start_time', '')
        if len(time_str) > 5:
            time_str = time_str[:5]

        business_name = tenant_config.get('business_name', 'JesyAI') if tenant_config else 'JesyAI'
        business_phone = tenant_config.get('business_phone', '') if tenant_config else ''

        message = f"""🔔 Recordatorio: Tu cita es en 1 hora

⏰ {time_str}
💈 {reservation_data.get('barber_name', 'Profesional')} en {business_name}

¿Confirmas tu asistencia?
Responde:
✅ SÍ - para confirmar
❌ NO - para cancelar"""

        if business_phone:
            message += f"\n\nPara cambios: {business_phone}"

        message += f"\n\n- {business_name}"

        return message

    async def send_reminder_for_cron(
        self,
        phone_number: str,
        client_name: str,
        business_name: str,
        appointment_time: str,
        barber_name: str,
        service_name: str,
        price: float
    ) -> bool:
        """
        Send reminder specifically for cron job
        Simplified interface that returns boolean

        Args:
            phone_number: Client phone with country code (e.g., +528111234567)
            client_name: Client's name
            business_name: Name of the business/branch
            appointment_time: Formatted time (e.g., "3:00 PM")
            barber_name: Barber/professional name
            service_name: Service name
            price: Price amount

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Ensure phone has whatsapp: prefix
            to_number = f"whatsapp:{phone_number}" if not phone_number.startswith("whatsapp:") else phone_number

            # Use default client (multitenant will come from branch config later)
            if not self.default_client:
                logger.error("[WHATSAPP-CRON] No Twilio client configured")
                return False

            # Build message using the template format
            # Once template is approved, we'll use content_sid instead
            message_body = f"""🔔 *Recordatorio de Cita - {business_name}*

Hola {client_name}! Te recordamos tu cita en 1 hora:

📅 Hoy a las {appointment_time}
💈 Con {barber_name}
💰 Servicio: {service_name} (${price})

📍 {business_name}

¿Confirmas tu asistencia?
Responde con SÍ o NO"""

            logger.info(f"[WHATSAPP-CRON] 📱 Enviando recordatorio a {phone_number}")

            # Send the message
            message = self.default_client.messages.create(
                from_=f"whatsapp:{self.default_whatsapp_number}",
                to=to_number,
                body=message_body
            )

            logger.info(f"[WHATSAPP-CRON] ✅ Recordatorio enviado exitosamente: {message.sid}")
            return True

        except TwilioRestException as e:
            logger.error(f"[WHATSAPP-CRON] ❌ Error Twilio: {e.msg} (código: {e.code})")
            return False
        except Exception as e:
            logger.error(f"[WHATSAPP-CRON] ❌ Error inesperado: {e}")
            return False

    async def send_barber_notification(
        self,
        barber_phone: str,
        reservation_data: Dict,
        tenant_config: Optional[Dict] = None
    ) -> Dict:
        """
        Envía notificación al barbero cuando se crea una nueva reserva
        """
        try:
            if not barber_phone:
                logger.warning("[WHATSAPP-BARBER] No barber phone provided, skipping")
                return {"success": False, "error": "no_phone", "skipped": True}

            # Normalizar teléfono del barbero
            normalized_phone = self._normalize_phone(barber_phone)
            if not normalized_phone:
                logger.warning("[WHATSAPP-BARBER] Invalid barber phone after normalization")
                return {"success": False, "error": "invalid_phone", "skipped": True}

            client, from_number = self._get_client_and_number(tenant_config)

            if not client or not from_number:
                logger.error("[WHATSAPP-BARBER] No Twilio client or number configured")
                return {"success": False, "error": "twilio_not_configured"}

            # Extraer datos para el template
            customer_name = reservation_data.get('customer_name', 'Cliente')
            client_phone = reservation_data.get('client_phone', 'N/A')
            date_str = reservation_data.get('date', '')
            start_time = reservation_data.get('start_time', '')
            service_name = reservation_data.get('service_name', 'Servicio')
            business_name = tenant_config.get('business_name', 'Tu negocio') if tenant_config else 'Tu negocio'

            # Formatear fecha
            formatted_date = date_str
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
                formatted_date = f"{dias[date_obj.weekday()]} {date_obj.day} de {meses[date_obj.month - 1]}"
            except:
                pass

            # Formatear hora
            formatted_time = start_time
            try:
                time_parts = start_time.replace(':00', '').split(':')
                hour = int(time_parts[0])
                minute = time_parts[1] if len(time_parts) > 1 else '00'
                period = 'AM' if hour < 12 else 'PM'
                if hour > 12:
                    hour -= 12
                elif hour == 0:
                    hour = 12
                formatted_time = f"{hour}:{minute} {period}"
            except:
                pass

            # Log detallado antes de enviar
            template_variables = {
                "1": customer_name,
                "2": client_phone,
                "3": formatted_date,
                "4": formatted_time,
                "5": service_name,
                "6": business_name
            }

            logger.info(f"[WHATSAPP-BARBER] 📤 Enviando notificación con TEMPLATE a {normalized_phone}")
            logger.info(f"[WHATSAPP-BARBER] 📋 Template SID: {BARBER_NEW_APPOINTMENT_TEMPLATE_SID}")
            logger.info(f"[WHATSAPP-BARBER] 📋 Variables: {template_variables}")
            logger.info(f"[WHATSAPP-BARBER] 📋 From: whatsapp:{from_number}")

            # Enviar vía Twilio con template aprobado
            message = client.messages.create(
                from_=f"whatsapp:{from_number}",
                to=f"whatsapp:{normalized_phone}",
                content_sid=BARBER_NEW_APPOINTMENT_TEMPLATE_SID,
                content_variables=json.dumps(template_variables)
            )

            logger.info(f"[WHATSAPP-BARBER] ✅ Notification sent to {normalized_phone}")
            logger.info(f"[WHATSAPP-BARBER] ✅ Message SID: {message.sid}")
            logger.info(f"[WHATSAPP-BARBER] ✅ Status: {message.status}")

            return {
                "success": True,
                "message_sid": message.sid,
                "to": normalized_phone
            }

        except TwilioRestException as e:
            logger.error(f"[WHATSAPP-BARBER] ❌ Twilio error sending to {barber_phone}")
            logger.error(f"[WHATSAPP-BARBER] ❌ Error code: {e.code}")
            logger.error(f"[WHATSAPP-BARBER] ❌ Error message: {e.msg}")
            logger.error(f"[WHATSAPP-BARBER] ❌ More info: {e.uri if hasattr(e, 'uri') else 'N/A'}")
            return {
                "success": False,
                "error": e.msg,
                "error_code": e.code,
                "barber_phone": barber_phone,
                "normalized_phone": normalized_phone if 'normalized_phone' in locals() else None
            }
        except Exception as e:
            logger.error(f"[WHATSAPP-BARBER] ❌ Unexpected error sending to {barber_phone}")
            logger.error(f"[WHATSAPP-BARBER] ❌ Exception type: {type(e).__name__}")
            logger.error(f"[WHATSAPP-BARBER] ❌ Exception: {str(e)}")
            import traceback
            logger.error(f"[WHATSAPP-BARBER] ❌ Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e), "barber_phone": barber_phone}

    def _build_barber_notification_message(
        self,
        reservation_data: Dict,
        tenant_config: Optional[Dict]
    ) -> str:
        """Construye mensaje de notificación para el barbero"""
        customer_name = reservation_data.get('customer_name', 'Cliente')
        client_phone = reservation_data.get('client_phone', 'N/A')
        date_str = reservation_data.get('date', '')
        start_time = reservation_data.get('start_time', '')
        service_name = reservation_data.get('service_name', 'Servicio')
        business_name = tenant_config.get('business_name', 'Tu negocio') if tenant_config else 'Tu negocio'

        # Formatear fecha si es posible
        formatted_date = date_str
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
            formatted_date = f"{dias[date_obj.weekday()]} {date_obj.day} de {meses[date_obj.month - 1]}"
        except:
            pass

        # Formatear hora
        formatted_time = start_time
        try:
            time_parts = start_time.replace(':00', '').split(':')
            hour = int(time_parts[0])
            minute = time_parts[1] if len(time_parts) > 1 else '00'
            period = 'AM' if hour < 12 else 'PM'
            if hour > 12:
                hour -= 12
            elif hour == 0:
                hour = 12
            formatted_time = f"{hour}:{minute} {period}"
        except:
            pass

        message = f"""📅 Nueva cita agendada

👤 Cliente: {customer_name}
📱 Tel: {client_phone}
📆 {formatted_date}
⏰ {formatted_time}
💇 {service_name}

- {business_name}"""

        return message

    async def send_barber_cancellation(
        self,
        barber_phone: str,
        reservation_data: Dict,
        tenant_config: Optional[Dict] = None
    ) -> Dict:
        """
        Envía notificación al barbero cuando se cancela una cita
        """
        try:
            if not barber_phone:
                return {"success": False, "error": "no_phone", "skipped": True}

            normalized_phone = self._normalize_phone(barber_phone)
            if not normalized_phone:
                return {"success": False, "error": "invalid_phone", "skipped": True}

            client, from_number = self._get_client_and_number(tenant_config)

            if not client or not from_number:
                return {"success": False, "error": "twilio_not_configured"}

            # Extraer datos para el template
            customer_name = reservation_data.get('customer_name', 'Cliente')
            date_str = reservation_data.get('date', '')
            start_time = reservation_data.get('start_time', '')
            service_name = reservation_data.get('service_name', 'Servicio')
            business_name = tenant_config.get('business_name', 'Tu negocio') if tenant_config else 'Tu negocio'

            # Formatear fecha
            formatted_date = date_str
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
                formatted_date = f"{dias[date_obj.weekday()]} {date_obj.day} de {meses[date_obj.month - 1]}"
            except:
                pass

            # Formatear hora
            formatted_time = start_time
            try:
                time_parts = start_time.replace(':00', '').split(':')
                hour = int(time_parts[0])
                minute = time_parts[1] if len(time_parts) > 1 else '00'
                period = 'AM' if hour < 12 else 'PM'
                if hour > 12:
                    hour -= 12
                elif hour == 0:
                    hour = 12
                formatted_time = f"{hour}:{minute} {period}"
            except:
                pass

            logger.info(f"[WHATSAPP-BARBER] 📤 Enviando cancelación con TEMPLATE a {normalized_phone}")

            # Enviar vía Twilio con template aprobado
            message = client.messages.create(
                from_=f"whatsapp:{from_number}",
                to=f"whatsapp:{normalized_phone}",
                content_sid=BARBER_CANCELLATION_TEMPLATE_SID,
                content_variables=json.dumps({
                    "1": customer_name,
                    "2": formatted_date,
                    "3": formatted_time,
                    "4": service_name,
                    "5": business_name
                })
            )

            logger.info(f"[WHATSAPP-BARBER] ✅ Cancellation sent to {normalized_phone}, SID: {message.sid}")

            return {"success": True, "message_sid": message.sid, "to": normalized_phone}

        except TwilioRestException as e:
            logger.error(f"[WHATSAPP-BARBER] Twilio error: {e.msg} (code: {e.code})")
            return {"success": False, "error": e.msg, "error_code": e.code}
        except Exception as e:
            logger.error(f"[WHATSAPP-BARBER] Error sending cancellation: {str(e)}")
            return {"success": False, "error": str(e)}

    def _build_barber_cancellation_message(
        self,
        reservation_data: Dict,
        tenant_config: Optional[Dict]
    ) -> str:
        """Construye mensaje de cancelación para el barbero"""
        customer_name = reservation_data.get('customer_name', 'Cliente')
        date_str = reservation_data.get('date', '')
        start_time = reservation_data.get('start_time', '')
        service_name = reservation_data.get('service_name', 'Servicio')
        business_name = tenant_config.get('business_name', 'Tu negocio') if tenant_config else 'Tu negocio'

        message = f"""❌ Cita cancelada

👤 Cliente: {customer_name}
📆 {date_str}
⏰ {start_time}
💇 {service_name}

La cita ha sido cancelada.

- {business_name}"""

        return message

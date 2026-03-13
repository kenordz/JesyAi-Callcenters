"""
Configuration for JesyAI SIP Realtime Call Center System
"""
import os
from typing import Dict, Any
import pytz


class Config:
    """
    OpenAI SIP Realtime API configuration for call center operations.
    Supports environment variable overrides for multi-project deployments.
    """

    # OpenAI SIP Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_CALLCENTER", "")
    OPENAI_PROJECT_ID = "proj_9iTewA2CctKm7UGJO2jz4VWo"
    OPENAI_WEBHOOK_SECRET = os.getenv("OPENAI_WEBHOOK_SECRET") or os.getenv("OPENAI_WEBHOOK_CALLCENTER", "")
    OPENAI_SIP_ENDPOINT = "sip:proj_9iTewA2CctKm7UGJO2jz4VWo@sip.api.openai.com;transport=tls"
    OPENAI_MODEL = "gpt-4o-mini-realtime-preview-2024-12-17"

    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://okoaavyfahvopbjhbplu.supabase.co")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

    # ViciDial Integration (Enlaza Comunicaciones)
    VICIDIAL_API_URL = os.getenv("VICIDIAL_API_URL", "https://d1-au0.enlaza.mx/agc/api.php")
    VICIDIAL_USER = os.getenv("VICIDIAL_USER", "api_user")
    VICIDIAL_PASS = os.getenv("VICIDIAL_PASS", "FkCtJ4wMpcTDa4nv")
    VICIDIAL_AGENT_USER = os.getenv("VICIDIAL_AGENT_USER", "2000")

    # Timezone
    TIMEZONE = pytz.timezone("America/Mexico_City")

    # Voice Configuration
    VOICE = "sage"

    @classmethod
    def get_realtime_config(cls) -> Dict[str, Any]:
        """
        Get OpenAI Realtime API configuration for call center operations.
        This is a generic template - implement specific instructions per tenant/use case.
        """
        return {
            "modalities": ["text", "audio"],
            "instructions": """You are a professional call center assistant. Speak naturally and conversationally.

Your objectives:
1. Greet callers professionally
2. Understand their needs
3. Provide information or route calls appropriately
4. Maintain a professional and courteous tone

Communication guidelines:
- Speak clearly and at a natural pace
- Listen actively and ask clarifying questions
- Be empathetic and professional
- Use natural pauses and conversational flow
- Confirm important information before proceeding
- Offer alternatives when needed
""",
            "voice": cls.VOICE,
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.8,
                "prefix_padding_ms": 1000,
                "silence_duration_ms": 2000
            },
            "temperature": 0.8,
            "max_response_output_tokens": 4096
        }
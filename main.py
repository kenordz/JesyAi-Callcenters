"""
JesyAI Call Center - FastAPI Main Application
Webhook endpoint for OpenAI SIP calls with Vicidial integration
"""

import os
import json
import logging
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import Config

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ADMIN API AUTHENTICATION ====================
# API Key para dashboard admin (lee del secret de Cloud Run)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

if not ADMIN_API_KEY:
    logger.warning("⚠️ ADMIN_API_KEY no configurada - endpoints admin deshabilitados")

async def verify_admin_api_key(authorization: str = Header(None)):
    """Verifica que el request tenga API key válida"""
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API not configured")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing API Key")

    # Formato esperado: "Bearer API_KEY"
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API Key format")

    api_key = authorization.replace("Bearer ", "")

    if api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    return True

# Configurar variables de entorno
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY or "YOUR_OPENAI_API_KEY_HERE"
os.environ["OPENAI_WEBHOOK_SECRET"] = Config.OPENAI_WEBHOOK_SECRET
os.environ["SUPABASE_URL"] = Config.SUPABASE_URL
os.environ["SUPABASE_ANON_KEY"] = Config.SUPABASE_ANON_KEY or "YOUR_SUPABASE_KEY_HERE"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info("🚀 Starting JesyAI Call Center System")
    logger.info(f"📞 SIP Endpoint: {Config.OPENAI_SIP_ENDPOINT}")
    logger.info(f"🤖 Model: {Config.OPENAI_MODEL}")
    logger.info(f"🏢 Multitenant mode (per-branch detection)")
    logger.info(f"📞 Vicidial API: {Config.VICIDIAL_API_URL or 'not configured'}")
    yield
    logger.info("👋 Shutting down JesyAI Call Center System")

# Crear aplicación FastAPI
app = FastAPI(
    title="JesyAI Call Center",
    description="Call Center SIP Integration with Vicidial",
    version="1.0.0",
    lifespan=lifespan
)

# Configurar CORS para permitir llamadas desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.jesyai.com",
        "https://jesyai.com",
        "https://www.jesy.mx",  # Dominio adicional
        "https://jesy.mx",  # Sin www
        "https://jesy-ai-dashboard-5703xfnin-eugenio-rodriguezs-projects.vercel.app",  # Vercel preview
        "https://jesy-ai-dashboard.vercel.app",  # Vercel producción
        "https://*.vercel.app",  # Todos los subdominios de Vercel
        "http://localhost:3000",  # Para desarrollo local
        "http://localhost:3001",  # Para desarrollo local alternativo
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Importar el handler después de configurar las variables de entorno
from openai_sip_handler import openai_sip_handler

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "active",
        "service": "JesyAI Call Center",
        "description": "Call Center SIP Integration with Vicidial",
        "sip_endpoint": Config.OPENAI_SIP_ENDPOINT
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "supabase_configured": bool(os.environ.get("SUPABASE_ANON_KEY")),
        "webhook_secret_configured": bool(Config.OPENAI_WEBHOOK_SECRET),
        "model": Config.OPENAI_MODEL,
        "voice": Config.VOICE
    }

@app.post("/webhook/openai-sip")
async def handle_openai_sip_webhook(request: Request):
    """
    Main webhook endpoint for OpenAI SIP calls
    This endpoint receives incoming call notifications from OpenAI
    """
    try:
        logger.info("[WEBHOOK] Received OpenAI SIP webhook request")
        logger.info(f"[WEBHOOK] Headers: {dict(request.headers)}")

        # Delegar al handler
        result = await openai_sip_handler.handle_incoming_sip_call(request)

        logger.info(f"[WEBHOOK] Response: {result}")
        return JSONResponse(content=result)

    except HTTPException as he:
        logger.error(f"[WEBHOOK] HTTP Exception: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"[WEBHOOK] Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/webhook/openai-events")
async def handle_openai_events_webhook(request: Request):
    """
    Webhook endpoint for OpenAI Realtime events (transcriptions, etc.)
    This endpoint receives conversation events during calls
    """
    try:
        body = await request.body()
        event_data = json.loads(body.decode())

        logger.info(f"[EVENTS-WEBHOOK] 📨 Received event: {event_data.get('type', 'unknown')}")

        # Procesar eventos de transcripción
        event_type = event_data.get('type')

        # Log detallado para transcripciones
        if 'transcription' in event_type or 'audio' in event_type:
            logger.info(f"[EVENTS-WEBHOOK] 🎤📝 EVENTO DE TRANSCRIPCIÓN:")
            logger.info(f"[EVENTS-WEBHOOK] Tipo: {event_type}")
            logger.info(f"[EVENTS-WEBHOOK] Datos: {json.dumps(event_data, indent=2)}")

        # Eventos específicos de transcripción
        if event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event_data.get('transcript', '')
            call_id = event_data.get('call_id', 'unknown')
            logger.info(f"[TRANSCRIPT] 🎤 Cliente (call {call_id}): '{transcript}'")

        elif event_type == "response.output_audio_transcript.done":
            transcript = event_data.get('transcript', '')
            call_id = event_data.get('call_id', 'unknown')
            logger.info(f"[TRANSCRIPT] 🤖 Jessica (call {call_id}): '{transcript}'")

        elif event_type == "conversation.item.input_audio_transcription.delta":
            delta = event_data.get('delta', '')
            call_id = event_data.get('call_id', 'unknown')
            logger.debug(f"[TRANSCRIPT-DELTA] 🎤 Cliente delta: '{delta}'")

        elif event_type == "conversation.item.input_audio_transcription.failed":
            error = event_data.get('error', {})
            call_id = event_data.get('call_id', 'unknown')
            logger.warning(f"[TRANSCRIPT-ERROR] ❌ Fallo transcripción (call {call_id}): {error}")

        elif event_type == "response.output_audio_transcript.delta":
            delta = event_data.get('delta', '')
            call_id = event_data.get('call_id', 'unknown')
            logger.debug(f"[TRANSCRIPT-DELTA] 🤖 Jessica delta: '{delta}'")

        else:
            # Log otros eventos importantes
            logger.info(f"[EVENTS-WEBHOOK] Evento: {event_type}")

        return JSONResponse(content={"status": "received"})

    except Exception as e:
        logger.error(f"[EVENTS-WEBHOOK] Error: {str(e)}", exc_info=True)
        return JSONResponse(content={"status": "error", "message": str(e)})


@app.get("/transcript/{call_id}")
async def get_transcript_ga(call_id: str):
    """
    Endpoint para obtener transcript de una llamada usando servicio GA.
    Útil para debugging y análisis post-llamada.
    """
    try:
        # Usar el servicio GA para obtener transcript
        if openai_sip_handler.transcription_ga:
            transcript_data = openai_sip_handler.transcription_ga.get_call_transcript(call_id)
            return {
                "status": "success",
                "call_id": call_id,
                "transcript": transcript_data,
                "source": "GA_service"
            }
        else:
            # Fallback al sistema viejo si GA no está disponible
            old_transcript = openai_sip_handler.call_transcriptions.get(call_id, [])
            return {
                "status": "success",
                "call_id": call_id,
                "transcript": {
                    "messages": old_transcript,
                    "full_transcript": "\n".join(old_transcript)
                },
                "source": "legacy_fallback"
            }
    except Exception as e:
        logger.error(f"[TRANSCRIPT-API] Error obteniendo transcript: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

# ==================== VICIDIAL INTEGRATION ENDPOINTS ====================

@app.get("/api/vicidial/call-start")
async def vicidial_call_start(
    campaign: str = "",
    call_id: str = "",
    agent_user: str = "2000"
):
    """
    GET webhook from Vicidial when a call starts.
    Vicidial sends: GET /api/vicidial/call-start?campaign=X&call_id=Y&agent_user=Z
    Registers the call as pending, awaiting SIP match by timing.
    """
    try:
        if not call_id:
            logger.warning("[VICIDIAL] Missing call_id in request")
            raise HTTPException(status_code=400, detail="Missing call_id")

        logger.info(f"[VICIDIAL] Received call-start webhook - campaign: {campaign}, call_id: {call_id}, agent_user: {agent_user}")

        # Use the shared VicidialService instance from the SIP handler
        result = openai_sip_handler.vicidial_service.register_pending_call(
            vicidial_call_id=call_id,
            campaign=campaign,
            agent_user=agent_user
        )

        logger.info(f"[VICIDIAL] Pending call registered: {result}")

        return {
            "status": "success",
            "message": "Pending call registered, awaiting SIP match",
            "campaign": campaign,
            "call_id": call_id,
            "agent_user": agent_user
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VICIDIAL] Error registering pending call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ADMIN API ENDPOINTS ====================
# Estos endpoints son para el dashboard de monitoreo (Luis)

@app.get("/api/admin/calls")
async def get_all_calls(
    tenant_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    authorization: str = Header(None)
):
    """
    Lista todas las llamadas con filtros

    Query params:
    - tenant_id: Filtrar por tenant específico
    - start_date: Fecha inicio (ISO format: 2025-11-25)
    - end_date: Fecha fin
    - status: completed, error, abandoned
    - limit: Número de resultados (default: 100)
    - offset: Para paginación (default: 0)
    """
    # Verificar autenticación
    await verify_admin_api_key(authorization)

    try:
        from core.database import DatabaseManager
        db_manager = DatabaseManager()

        # Construir query base
        query = db_manager.client.table('call_history').select(
            'call_sid, tenant_id, branch_id, from_number, to_number, '
            'duration, status, reservation_id, reservation_created, created_at'
        )

        # Aplicar filtros
        if tenant_id:
            query = query.eq('tenant_id', tenant_id)
        if start_date:
            query = query.gte('created_at', start_date)
        if end_date:
            query = query.lte('created_at', end_date)
        if status:
            query = query.eq('status', status)

        # Ordenar y paginar
        query = query.order('created_at', desc=True).range(offset, offset + limit - 1)

        response = query.execute()

        return {
            "success": True,
            "count": len(response.data),
            "calls": response.data
        }

    except Exception as e:
        logger.error(f"[ADMIN-API] Error getting calls: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/calls/{call_id}")
async def get_call_detail(
    call_id: str,
    authorization: str = Header(None)
):
    """
    Detalle completo de una llamada específica
    Incluye: metadata, transcripción completa, logs técnicos
    """
    # Verificar autenticación
    await verify_admin_api_key(authorization)

    try:
        from core.database import DatabaseManager
        db_manager = DatabaseManager()

        # 1. Obtener datos de call_history
        call_response = db_manager.client.table('call_history').select('*').eq('call_sid', call_id).execute()

        if not call_response.data:
            raise HTTPException(status_code=404, detail="Call not found")

        call_data = call_response.data[0]

        # 2. Obtener tenant y branch info
        tenant_info = {}
        branch_info = {}

        if call_data.get("tenant_id"):
            tenant_response = db_manager.client.table('tenants').select('name, contact_phone').eq('id', call_data.get("tenant_id")).execute()
            if tenant_response.data:
                tenant_info = tenant_response.data[0]

        if call_data.get("branch_id"):
            branch_response = db_manager.client.table('branches').select('name, address').eq('id', call_data.get("branch_id")).execute()
            if branch_response.data:
                branch_info = branch_response.data[0]

        # 3. Preparar respuesta completa
        return {
            "success": True,
            "call": {
                "metadata": {
                    "call_sid": call_data.get("call_sid"),
                    "tenant_id": call_data.get("tenant_id"),
                    "tenant_name": tenant_info.get("name", "N/A"),
                    "tenant_phone": tenant_info.get("contact_phone", "N/A"),
                    "branch_id": call_data.get("branch_id"),
                    "branch_name": branch_info.get("name", "N/A"),
                    "branch_address": branch_info.get("address", "N/A"),
                    "from_number": call_data.get("from_number"),
                    "to_number": call_data.get("to_number"),
                    "duration": call_data.get("duration"),
                    "status": call_data.get("status"),
                    "reservation_id": call_data.get("reservation_id"),
                    "reservation_created": call_data.get("reservation_created"),
                    "created_at": call_data.get("created_at")
                },
                "transcript": call_data.get("transcript", ""),
                "call_metadata": call_data.get("call_metadata", {}),
                "intent": call_data.get("intent")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADMIN-API] Error getting call detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/tenants")
async def get_all_tenants(
    authorization: str = Header(None)
):
    """
    Lista todos los tenants (para filtro en dashboard)
    """
    # Verificar autenticación
    await verify_admin_api_key(authorization)

    try:
        from core.database import DatabaseManager
        db_manager = DatabaseManager()

        response = db_manager.client.table('tenants').select(
            'id, name, contact_phone, business_type'
        ).execute()

        return {
            "success": True,
            "tenants": response.data
        }

    except Exception as e:
        logger.error(f"[ADMIN-API] Error getting tenants: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/stats")
async def get_admin_stats(
    tenant_id: Optional[str] = None,
    days: int = 7,
    authorization: str = Header(None)
):
    """
    Estadísticas generales para el dashboard

    Query params:
    - tenant_id: Filtrar por tenant
    - days: Últimos N días (default: 7)
    """
    # Verificar autenticación
    await verify_admin_api_key(authorization)

    try:
        from core.database import DatabaseManager
        from datetime import datetime, timedelta

        db_manager = DatabaseManager()

        # Fecha de inicio
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # Query base
        query = db_manager.client.table('call_history').select('*')

        if tenant_id:
            query = query.eq('tenant_id', tenant_id)

        query = query.gte('created_at', start_date)

        response = query.execute()
        calls = response.data

        # Calcular estadísticas
        total_calls = len(calls)
        total_duration = sum(call.get('duration', 0) for call in calls)

        status_breakdown = {}
        classification_breakdown = {}

        for call in calls:
            status = call.get('status', 'unknown')
            status_breakdown[status] = status_breakdown.get(status, 0) + 1

            classification = call.get('classification', 'unknown')
            classification_breakdown[classification] = classification_breakdown.get(classification, 0) + 1

        return {
            "success": True,
            "stats": {
                "total_calls": total_calls,
                "total_duration_minutes": round(total_duration / 60, 2) if total_duration > 0 else 0,
                "average_duration_seconds": round(total_duration / total_calls, 2) if total_calls > 0 else 0,
                "status_breakdown": status_breakdown,
                "classification_breakdown": classification_breakdown,
                "period_days": days
            }
        }

    except Exception as e:
        logger.error(f"[ADMIN-API] Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    logger.warning(f"404 Not Found: {request.url.path}")
    return JSONResponse(
        status_code=404,
        content={"detail": "Endpoint not found"}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"500 Internal Error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn

    # Configuración para desarrollo local
    port = int(os.environ.get("PORT", 8080))

    logger.info(f"🎯 Starting server on port {port}")
    logger.info(f"📝 Webhook URL: http://localhost:{port}/webhook/openai-sip")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
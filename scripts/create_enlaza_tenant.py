"""
Script to create Enlaza Comunicaciones tenant and branch in Supabase.
Usage: python scripts/create_enlaza_tenant.py
"""

import os
import sys
import json

# Add parent directory to path so we can import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase import create_client


def get_supabase_client():
    """Create Supabase client from env vars or config."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        try:
            from config import Config
            url = url or Config.SUPABASE_URL
            key = key or Config.SUPABASE_ANON_KEY
        except ImportError:
            pass

    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY are required.")
        print("Set them as environment variables or in config.py")
        sys.exit(1)

    return create_client(url, key)


def main():
    supabase = get_supabase_client()
    print("Connected to Supabase")

    # 1. Check if tenant already exists
    existing = supabase.table("tenants").select("id, name").eq(
        "name", "Enlaza Comunicaciones"
    ).execute()

    if existing.data:
        print(f"Tenant 'Enlaza Comunicaciones' already exists with ID: {existing.data[0]['id']}")
        tenant_id = existing.data[0]["id"]
    else:
        # Create tenant
        tenant_data = {
            "name": "Enlaza Comunicaciones",
            "slug": "enlaza-comunicaciones",
            "business_type": "restaurant",  # DB constraint only allows barbershop/restaurant for now
            "contact_phone": "+5575906030",
            "contact_email": "carlos@enlaza.mx",
            "status": "active",
        }

        result = supabase.table("tenants").insert(tenant_data).execute()

        if not result.data:
            print(f"ERROR creating tenant: {result}")
            sys.exit(1)

        tenant_id = result.data[0]["id"]
        print(f"Tenant created: {tenant_id}")

    # 2. Check if branch already exists for this tenant
    existing_branch = supabase.table("branches").select("id, name").eq(
        "tenant_id", tenant_id
    ).eq("name", "Demo Enlaza").execute()

    ai_config = {
        "business_type": "callcenter",
        "assistant_name": "Jessica",
        "business_name": "Centro de Atencion",
        "greeting": "Hola, gracias por llamar al centro de atencion. Soy Jessica, en que puedo ayudarte hoy?",
        "voice": "sage",
        "language": "es-MX",
        "instructions": (
            "Eres Jessica, asistente virtual del centro de atencion. Tu trabajo es:\n"
            "1. Entender la necesidad del cliente\n"
            "2. Intentar resolver su consulta con la informacion disponible\n"
            "3. Si no puedes resolver, transferir a un agente humano\n"
            "4. Ser profesional, amable y concisa\n"
            "5. Hablar en espanol de Mexico\n"
            "6. No inventar informacion\n"
            "7. Si el cliente pide hablar con un humano, transferir inmediatamente"
        ),
        "tools": ["transfer_to_human", "hangup_call", "lookup_customer_info"],
    }

    if existing_branch.data:
        branch_id = existing_branch.data[0]["id"]
        print(f"Branch 'Demo Enlaza' already exists with ID: {branch_id}")

        # Update ai_config on existing branch
        supabase.table("branches").update({"ai_config": ai_config}).eq(
            "id", branch_id
        ).execute()
        print(f"AI config updated for branch: {branch_id}")
    else:
        # Create branch
        branch_data = {
            "tenant_id": tenant_id,
            "name": "Demo Enlaza",
            "slug": "demo-enlaza",
            "phone": "+528177703223",
            "twilio_phone_number": "+528177703223",
            "timezone": "America/Mexico_City",
            "is_active": True,
            "ai_config": ai_config,
        }

        result = supabase.table("branches").insert(branch_data).execute()

        if not result.data:
            print(f"ERROR creating branch: {result}")
            sys.exit(1)

        branch_id = result.data[0]["id"]
        print(f"Branch created: {branch_id}")

    # Summary
    print("\n" + "=" * 50)
    print("ENLAZA COMUNICACIONES - SETUP COMPLETE")
    print("=" * 50)
    print(f"Tenant ID:  {tenant_id}")
    print(f"Branch ID:  {branch_id}")
    print(f"Phone:      +528177703223")
    print(f"Assistant:  Jessica")
    print(f"Voice:      sage")
    print(f"AI Config:  {json.dumps(ai_config, indent=2, ensure_ascii=False)}")
    print("=" * 50)


if __name__ == "__main__":
    main()

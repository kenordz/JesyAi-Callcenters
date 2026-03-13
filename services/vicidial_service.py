"""
Vicidial/Enlaza API Service

OOP service for Vicidial/Enlaza Comunicaciones API integration.
Handles call hangup, transfers, and call mapping for Vicidial system.
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import time
import httpx

logger = logging.getLogger(__name__)


class VicidialService:
    """
    OOP service for Vicidial/Enlaza Comunicaciones API integration.

    Manages:
    - Call ID mapping (OpenAI → Vicidial)
    - Call hangup operations
    - Transfer to agent/ingroup
    - Call notes updates
    """

    def __init__(self, database_manager=None):
        """
        Initialize Vicidial service.

        Args:
            database_manager: Optional DatabaseManager instance for future persistence
        """
        self.db_manager = database_manager

        # Load config from environment
        self.api_url = os.getenv("VICIDIAL_API_URL", "https://d1-au0.enlaza.mx/agc/api.php")
        self.api_user = os.getenv("VICIDIAL_USER", "")
        self.api_pass = os.getenv("VICIDIAL_PASS", "")
        self.agent_user = os.getenv("VICIDIAL_AGENT_USER", "2000")

        # In-memory call mapping: OpenAI call_id → Vicidial call_id
        self._call_mapping: Dict[str, str] = {}

        # In-memory call metadata for logging
        self._call_metadata: Dict[str, Dict[str, Any]] = {}

        # Pending Vicidial calls awaiting SIP match (vicidial_call_id → metadata)
        self._pending_vicidial_calls: Dict[str, Dict[str, Any]] = {}

        logger.info("[VICIDIAL] Service initialized")
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate that required environment variables are set."""
        if not self.api_user or not self.api_pass:
            logger.warning(
                "[VICIDIAL] Missing VICIDIAL_USER or VICIDIAL_PASS in environment variables. "
                "API calls will fail. Set them before deploying to Cloud Run."
            )
        else:
            logger.info("[VICIDIAL] Configuration validated successfully")

    def register_pending_call(
        self, vicidial_call_id: str, campaign: str = "", agent_user: str = ""
    ) -> Dict[str, Any]:
        """
        Register a pending Vicidial call awaiting SIP match.
        Called when the Vicidial GET webhook arrives before/simultaneously with the SIP call.

        Args:
            vicidial_call_id: Vicidial system call ID
            campaign: Campaign name
            agent_user: Vicidial agent user (e.g. "2000")

        Returns:
            Dict with registration status
        """
        # Clean up old pending calls (older than 30 seconds)
        current = time.time()
        expired = [
            cid for cid, data in self._pending_vicidial_calls.items()
            if current - data["timestamp"] > 30
        ]
        for cid in expired:
            del self._pending_vicidial_calls[cid]

        self._pending_vicidial_calls[vicidial_call_id] = {
            "vicidial_call_id": vicidial_call_id,
            "campaign": campaign,
            "agent_user": agent_user or self.agent_user,
            "timestamp": current,
        }

        logger.info(
            f"[VICIDIAL] Pending call registered - Vicidial ID: {vicidial_call_id}, "
            f"Campaign: {campaign}, Agent: {agent_user or self.agent_user}"
        )

        return {
            "success": True,
            "vicidial_call_id": vicidial_call_id,
            "pending_count": len(self._pending_vicidial_calls),
        }

    def match_vicidial_to_sip(self, sip_call_id: str) -> Optional[str]:
        """
        Match a SIP call to a pending Vicidial call by timing (10-second window).
        If a match is found, registers the mapping and removes from pending.

        Args:
            sip_call_id: OpenAI SIP call ID

        Returns:
            Vicidial call ID if matched, None otherwise
        """
        current = time.time()
        best_match = None
        best_time_diff = float("inf")

        for vicidial_call_id, data in self._pending_vicidial_calls.items():
            time_diff = current - data["timestamp"]
            if time_diff <= 10 and time_diff < best_time_diff:
                best_match = vicidial_call_id
                best_time_diff = time_diff

        if best_match:
            pending_data = self._pending_vicidial_calls.pop(best_match)
            campaign = pending_data.get("campaign", "")
            agent_user = pending_data.get("agent_user", self.agent_user)

            # Register the mapping
            self.register_call(sip_call_id, best_match, campaign=campaign)

            # Store agent_user in metadata for later API calls
            if sip_call_id in self._call_metadata:
                self._call_metadata[sip_call_id]["agent_user"] = agent_user

            logger.info(
                f"[VICIDIAL] SIP matched to Vicidial - SIP: {sip_call_id} → "
                f"Vicidial: {best_match} (time_diff: {best_time_diff:.2f}s)"
            )
            return best_match

        logger.debug(f"[VICIDIAL] No pending Vicidial call found for SIP: {sip_call_id}")
        return None

    def register_call(self, openai_call_id: str, vicidial_call_id: str, campaign: str = "") -> None:
        """
        Register a mapping between OpenAI call ID and Vicidial call ID.

        Args:
            openai_call_id: OpenAI Realtime API call ID
            vicidial_call_id: Vicidial system call ID
            campaign: Campaign/ingroup name for reference
        """
        self._call_mapping[openai_call_id] = vicidial_call_id
        self._call_metadata[openai_call_id] = {
            "openai_call_id": openai_call_id,
            "vicidial_call_id": vicidial_call_id,
            "campaign": campaign,
            "registered_at": datetime.utcnow().isoformat(),
            "status": "ACTIVE",
        }
        logger.info(
            f"[VICIDIAL] Call registered - OpenAI: {openai_call_id} → Vicidial: {vicidial_call_id} (Campaign: {campaign})"
        )

    def get_vicidial_call_id(self, openai_call_id: str) -> Optional[str]:
        """
        Retrieve Vicidial call ID from OpenAI call ID mapping.

        Args:
            openai_call_id: OpenAI Realtime API call ID

        Returns:
            Vicidial call ID if exists, None otherwise
        """
        call_id = self._call_mapping.get(openai_call_id)
        if call_id:
            logger.debug(f"[VICIDIAL] Retrieved mapping for {openai_call_id}: {call_id}")
        else:
            logger.warning(f"[VICIDIAL] No mapping found for {openai_call_id}")
        return call_id

    async def hangup_call(
        self, openai_call_id: str, status: str = "OK", notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        End call in Vicidial system with specified status.

        API call:
        GET {api_url}?source=test&user={user}&pass={pass}&agent_user={agent}&
            function=ra_call_control&stage=HANGUP&status={status}&value={vicidial_call_id}

        Args:
            openai_call_id: OpenAI call ID to hangup
            status: Vicidial status code (SALE, NI, CALLBK, XFER, DNC, INFO)
            notes: Optional notes to store

        Returns:
            Dict with result status and response data
        """
        vicidial_call_id = self.get_vicidial_call_id(openai_call_id)

        if not vicidial_call_id:
            logger.error(f"[VICIDIAL] Cannot hangup: No call ID mapping for {openai_call_id}")
            return {
                "success": False,
                "error": f"No Vicidial call ID found for {openai_call_id}",
            }

        try:
            # Use per-call agent_user if available, fall back to default
            call_agent_user = self.agent_user
            if openai_call_id in self._call_metadata:
                call_agent_user = self._call_metadata[openai_call_id].get("agent_user", self.agent_user)

            params = {
                "source": "test",
                "user": self.api_user,
                "pass": self.api_pass,
                "agent_user": call_agent_user,
                "function": "ra_call_control",
                "stage": "HANGUP",
                "status": status,
                "value": vicidial_call_id,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params=params)
                response.raise_for_status()

                result = {
                    "success": True,
                    "status_code": response.status_code,
                    "response": response.text,
                    "vicidial_call_id": vicidial_call_id,
                    "disposition_status": status,
                }

                # Update metadata
                if openai_call_id in self._call_metadata:
                    self._call_metadata[openai_call_id]["status"] = "HUNGUP"
                    self._call_metadata[openai_call_id]["hangup_at"] = datetime.utcnow().isoformat()
                    self._call_metadata[openai_call_id]["hangup_status"] = status
                    if notes:
                        self._call_metadata[openai_call_id]["notes"] = notes

                logger.info(
                    f"[VICIDIAL] Hangup successful - OpenAI: {openai_call_id}, "
                    f"Vicidial: {vicidial_call_id}, Status: {status}"
                )

                return result

        except httpx.HTTPError as e:
            error_msg = f"[VICIDIAL] HTTP error during hangup: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
            }
        except Exception as e:
            error_msg = f"[VICIDIAL] Unexpected error during hangup: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
            }

    async def transfer_to_agent(
        self, openai_call_id: str, ingroup: str = "IN_ENTRADA"
    ) -> Dict[str, Any]:
        """
        Transfer call to ingroup/agent in Vicidial.

        API call:
        GET {api_url}?source=test&user={user}&pass={pass}&agent_user={agent}&
            function=ra_call_control&stage=INGROUPTRANSFER&ingroup_choices={ingroup}&
            value={vicidial_call_id}

        Args:
            openai_call_id: OpenAI call ID to transfer
            ingroup: Vicidial ingroup code (e.g., "IN_ENTRADA", "IN_SUPPORT")

        Returns:
            Dict with result status and response data
        """
        vicidial_call_id = self.get_vicidial_call_id(openai_call_id)

        if not vicidial_call_id:
            logger.error(f"[VICIDIAL] Cannot transfer: No call ID mapping for {openai_call_id}")
            return {
                "success": False,
                "error": f"No Vicidial call ID found for {openai_call_id}",
            }

        try:
            # Use per-call agent_user if available, fall back to default
            call_agent_user = self.agent_user
            if openai_call_id in self._call_metadata:
                call_agent_user = self._call_metadata[openai_call_id].get("agent_user", self.agent_user)

            params = {
                "source": "test",
                "user": self.api_user,
                "pass": self.api_pass,
                "agent_user": call_agent_user,
                "function": "ra_call_control",
                "stage": "INGROUPTRANSFER",
                "ingroup_choices": ingroup,
                "value": vicidial_call_id,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params=params)
                response.raise_for_status()

                result = {
                    "success": True,
                    "status_code": response.status_code,
                    "response": response.text,
                    "vicidial_call_id": vicidial_call_id,
                    "transfer_ingroup": ingroup,
                }

                # Update metadata
                if openai_call_id in self._call_metadata:
                    self._call_metadata[openai_call_id]["status"] = "TRANSFERRED"
                    self._call_metadata[openai_call_id]["transferred_at"] = datetime.utcnow().isoformat()
                    self._call_metadata[openai_call_id]["transfer_ingroup"] = ingroup

                logger.info(
                    f"[VICIDIAL] Transfer successful - OpenAI: {openai_call_id}, "
                    f"Vicidial: {vicidial_call_id}, Ingroup: {ingroup}"
                )

                return result

        except httpx.HTTPError as e:
            error_msg = f"[VICIDIAL] HTTP error during transfer: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
            }
        except Exception as e:
            error_msg = f"[VICIDIAL] Unexpected error during transfer: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
            }

    async def update_call_notes(self, openai_call_id: str, notes: str) -> Dict[str, Any]:
        """
        Update call notes for future implementation.

        Currently stores notes in metadata. Future version will sync to Vicidial database.

        Args:
            openai_call_id: OpenAI call ID
            notes: Notes to store

        Returns:
            Dict with result status
        """
        try:
            if openai_call_id not in self._call_metadata:
                logger.warning(f"[VICIDIAL] No metadata found for {openai_call_id}")
                return {
                    "success": False,
                    "error": "No call metadata found",
                }

            self._call_metadata[openai_call_id]["notes"] = notes
            self._call_metadata[openai_call_id]["notes_updated_at"] = datetime.utcnow().isoformat()

            logger.info(f"[VICIDIAL] Notes updated for {openai_call_id}: {notes[:50]}...")

            return {
                "success": True,
                "message": "Notes updated successfully",
            }

        except Exception as e:
            error_msg = f"[VICIDIAL] Error updating notes: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
            }

    def get_call_metadata(self, openai_call_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve metadata for a call.

        Args:
            openai_call_id: OpenAI call ID

        Returns:
            Call metadata dict if exists, None otherwise
        """
        return self._call_metadata.get(openai_call_id)

    def get_all_active_calls(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all active calls currently in memory.

        Returns:
            Dict of all calls with their metadata
        """
        return {
            call_id: metadata
            for call_id, metadata in self._call_metadata.items()
            if metadata.get("status") == "ACTIVE"
        }

    def cleanup_call(self, openai_call_id: str) -> None:
        """
        Clean up call mapping and metadata from memory.

        Args:
            openai_call_id: OpenAI call ID to remove
        """
        if openai_call_id in self._call_mapping:
            del self._call_mapping[openai_call_id]
        if openai_call_id in self._call_metadata:
            del self._call_metadata[openai_call_id]
        logger.info(f"[VICIDIAL] Call cleaned up: {openai_call_id}")

    def __repr__(self) -> str:
        """String representation of service."""
        active_calls = len(self.get_all_active_calls())
        return (
            f"VicidialService(active_calls={active_calls}, "
            f"api_url={self.api_url}, agent_user={self.agent_user})"
        )

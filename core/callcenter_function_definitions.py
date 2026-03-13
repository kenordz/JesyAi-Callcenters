"""
Call Center Function Definitions

OpenAI Realtime API compatible tool definitions for call center operations.
Includes transfer, hangup, and customer lookup functions.
"""

from typing import List, Dict, Any


def transfer_to_human() -> Dict[str, Any]:
    """
    Transfer call to human agent function definition.

    Returns:
        OpenAI function definition dict
    """
    return {
        "type": "function",
        "name": "transfer_to_human",
        "description": (
            "Transfer the call to a human agent when you cannot resolve the issue. "
            "Use this when the customer explicitly requests an agent, the issue is too complex, "
            "the customer is upset, or account changes are needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Reason for transfer (e.g., 'Customer requested agent', "
                        "'Complex billing issue', 'Account modification needed', 'Customer upset')"
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "Brief context summary for the human agent (what was discussed, "
                        "what was the issue, any relevant details). Keep to 1-2 sentences."
                    ),
                },
            },
            "required": ["reason"],
        },
    }


def hangup_call() -> Dict[str, Any]:
    """
    Hangup call function definition.

    Returns:
        OpenAI function definition dict
    """
    return {
        "type": "function",
        "name": "hangup_call",
        "description": (
            "End the call with appropriate disposition status. "
            "Use when the issue is resolved, customer is satisfied, or call cannot continue."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["SALE", "NI", "CALLBK", "XFER", "DNC", "INFO"],
                    "description": (
                        "Vicidial call disposition status. "
                        "SALE: Customer accepted/purchased. "
                        "NI: Not interested. "
                        "CALLBK: Customer requested a callback. "
                        "XFER: Call was transferred to human agent. "
                        "DNC: Do not call again. "
                        "INFO: Information was provided only."
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Optional brief notes about the call outcome for the record "
                        "(e.g., 'Password reset sent', 'Appointment scheduled for 3/15')"
                    ),
                },
            },
            "required": ["status"],
        },
    }


def lookup_customer_info() -> Dict[str, Any]:
    """
    Lookup customer information function definition.

    Returns:
        OpenAI function definition dict
    """
    return {
        "type": "function",
        "name": "lookup_customer_info",
        "description": (
            "Look up customer information in the database by phone number or name. "
            "Use when you need to verify identity, check account status, or gather context before resolving."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Customer phone number (e.g., '+5218177703223' or '8177703223')",
                },
                "name": {
                    "type": "string",
                    "description": "Customer full name or partial name for search",
                },
            },
            "required": [],
        },
    }


def get_callcenter_tools() -> List[Dict[str, Any]]:
    """
    Get all call center function definitions for OpenAI Realtime API.

    Returns:
        List of tool definition dicts in OpenAI format
    """
    return [
        transfer_to_human(),
        hangup_call(),
        lookup_customer_info(),
    ]


def get_callcenter_tools_json() -> str:
    """
    Get call center tools as JSON string for easy integration.

    Returns:
        JSON string of tools
    """
    import json

    return json.dumps(get_callcenter_tools(), indent=2, ensure_ascii=False)


# Tool definition utilities for reference
CALLCENTER_TOOLS_SCHEMA = {
    "transfer_to_human": {
        "required_params": ["reason"],
        "optional_params": ["summary"],
        "use_cases": [
            "Customer explicitly requests an agent",
            "Issue is too complex to resolve",
            "Customer is frustrated or upset",
            "Account modifications or billing changes needed",
        ],
    },
    "hangup_call": {
        "required_params": ["status"],
        "optional_params": ["notes"],
        "valid_statuses": ["SALE", "NI", "CALLBK", "XFER", "DNC", "INFO"],
        "use_cases": [
            "Issue resolved and customer satisfied",
            "Maximum resolution attempts made",
            "Call must end appropriately",
        ],
    },
    "lookup_customer_info": {
        "required_params": [],
        "optional_params": ["phone", "name"],
        "min_one_param_required": True,
        "use_cases": [
            "Verify customer identity",
            "Check account status",
            "Gather context before resolution",
        ],
    },
}

"""Prompt template for the LLM-backed triage classifier."""

from __future__ import annotations

TRIAGE_SYSTEM_PROMPT = """\
You are the Triage Agent of CompuFix, a system that diagnoses common computer
problems. Classify the user's problem into exactly one category and extract
relevant entities.

Categories:
- "python_missing_library": a Python import/module is missing
  (e.g. ModuleNotFoundError, ImportError, "No module named X").
- "network_slow": the internet / Wi-Fi is slow.
- "high_resource_usage": the computer is slow due to high CPU or RAM usage.
- "unknown": none of the above / not enough information.

Entities to extract when present:
- missing_module: the Python import name (e.g. "cv2", "sklearn").
- package_name: the pip package name if it differs from the import.
- current_network: the SSID/network mentioned by the user.
- suspected_process: a process name the user blames.
- operating_system: the OS if mentioned.

Respond with ONLY a JSON object of this exact shape (no prose, no code fences):
{
  "problem_type": "<category>",
  "confidence": <float 0..1>,
  "extracted_entities": { ... },
  "requires_retrieval": <bool>,
  "requires_system_tools": <bool>
}
"""

TRIAGE_USER_TEMPLATE = """\
{context_prefix}User problem:
\"\"\"{user_input}\"\"\"

Return the JSON object now.
"""

TRIAGE_CLARIFICATION_TEMPLATE = """\
Previous conversation:
{conversation_context}

User problem:
\"\"\"{user_input}\"\"\"

Return the JSON object now.
"""


def build_triage_messages(
    user_input: str,
    conversation_context: str = "",
) -> list[dict[str, str]]:
    """Build the chat messages for the triage LLM call."""
    if conversation_context:
        content = TRIAGE_CLARIFICATION_TEMPLATE.format(
            conversation_context=conversation_context,
            user_input=user_input,
        )
    else:
        content = TRIAGE_USER_TEMPLATE.format(
            context_prefix="",
            user_input=user_input,
        )
    return [
        {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

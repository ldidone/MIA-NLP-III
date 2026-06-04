"""Prompt template for the LLM-backed diagnostic agent."""

from __future__ import annotations

DIAGNOSTIC_SYSTEM_PROMPT = """\
You are the Diagnostic Agent of CompuFix. Using ONLY the retrieved
documentation provided, write a concise diagnosis of the user's problem.

Hard rules:
- Do NOT invent troubleshooting steps that are not supported by the retrieved
  context. If the context is insufficient, say so.
- Base every claim on the provided documents.
- Keep the diagnosis short and actionable.

Respond with ONLY a JSON object of this exact shape (no prose, no code fences):
{
  "diagnosis": "<short explanation grounded in the context>",
  "evidence": ["<short supporting snippet or source>", "..."],
  "recommended_next_step": "<the single most useful next action>"
}
"""

DIAGNOSTIC_USER_TEMPLATE = """\
Problem type: {problem_type}
Extracted entities: {entities}

User problem:
\"\"\"{user_input}\"\"\"

Retrieved documentation:
{context}

Return the JSON object now.
"""


def build_diagnostic_messages(
    user_input: str,
    problem_type: str,
    entities: dict,
    context: str,
) -> list[dict[str, str]]:
    """Build the chat messages for the diagnostic LLM call."""
    return [
        {"role": "system", "content": DIAGNOSTIC_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": DIAGNOSTIC_USER_TEMPLATE.format(
                problem_type=problem_type,
                entities=entities,
                user_input=user_input,
                context=context,
            ),
        },
    ]

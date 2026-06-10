"""Triage Agent: classify a user problem and extract entities.

Hybrid design:
    1. A deterministic **rule-based** classifier handles the common patterns and
       always works offline (no API key required).
    2. An optional **LLM-based** classifier refines results when configured.

The rule-based path is always the safety net: if the LLM is unavailable or
returns something unusable, we fall back to rules.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from compufix_agents.config import get_settings
from compufix_agents.logging_config import get_logger
from compufix_agents.schemas.triage import ProblemType, TriageResult
from compufix_agents.tools.python_env_tools import IMPORT_TO_PACKAGE, map_import_to_package

logger = get_logger(__name__)


def _normalize(text: str) -> str:
    """Lowercase and strip accents/diacritics for robust keyword matching."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# --- Rule patterns ----------------------------------------------------------

# Capture the module name in "No module named 'x'", "No module named x",
# or "ModuleNotFoundError: ... 'x'".
_MODULE_PATTERNS = [
    re.compile(r"no module named\s*['\"]?([\w.]+)['\"]?", re.IGNORECASE),
    re.compile(
        r"modulenotfounderror[^\w]+(?:no module named\s*)?['\"]?([\w.]+)['\"]?", re.IGNORECASE
    ),
    re.compile(r"importerror[^\w]+(?:no module named\s*)?['\"]?([\w.]+)['\"]?", re.IGNORECASE),
    re.compile(r"cannot import name .* from ['\"]?([\w.]+)['\"]?", re.IGNORECASE),
]

# Natural-language phrasings (English + Spanish) for a missing library, e.g.
# "I don't have torch installed", "no tengo instalado torch",
# "me falta la librería pandas", "how do I install numpy?".
_NAME = r"['\"`]?([A-Za-z_][\w.-]*)['\"`]?"
_NL_MODULE_PATTERNS = [
    # English
    re.compile(
        rf"(?:don'?t|do not|doesn'?t|does not) have (?:the )?{_NAME}\s+"
        r"(?:installed|library|module|package)",
        re.IGNORECASE,
    ),
    re.compile(rf"{_NAME} (?:is(?: not|n'?t)|was(?: not|n'?t)) (?:not )?installed", re.IGNORECASE),
    re.compile(
        rf"(?:need(?:s)? to|want to|trying to|how (?:do|can) i|how to) install {_NAME}",
        re.IGNORECASE,
    ),
    re.compile(rf"pip3? install {_NAME}", re.IGNORECASE),
    re.compile(
        rf"(?:can'?t|cannot|couldn'?t|unable to|fail(?:s|ed)? to) import {_NAME}", re.IGNORECASE
    ),
    re.compile(rf"missing (?:the )?{_NAME}\s+(?:library|module|package)", re.IGNORECASE),
    re.compile(
        rf"(?:the )?{_NAME}\s+(?:library|module|package) is (?:missing|not installed)",
        re.IGNORECASE,
    ),
    # Spanish
    re.compile(
        rf"no tengo (?:instalad[oa]s? )?(?:la |el )?(?:librer[ií]a |m[oó]dulo |paquete )?{_NAME}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:me )?faltan? (?:instalar )?(?:la |el )?(?:librer[ií]a |m[oó]dulo |paquete )?{_NAME}",
        re.IGNORECASE,
    ),
    re.compile(rf"(?:necesito|quiero|c[oó]mo) instal\w+ {_NAME}", re.IGNORECASE),
    re.compile(rf"no (?:me )?(?:puedo|deja|funciona) importar {_NAME}", re.IGNORECASE),
    re.compile(rf"{_NAME} no est[aá] instalad[oa]", re.IGNORECASE),
]

# Popular package names (lowercase) -> canonical *import* name. Mentioning one
# of these alongside install/need intent is a strong missing-library signal.
_KNOWN_PACKAGES: dict[str, str] = {
    # Import names with a different pip package (from the shared mapping).
    **{imp.lower(): imp for imp in IMPORT_TO_PACKAGE},
    # Pip package names users often mention instead of the import name.
    "scikit-learn": "sklearn",
    "scikitlearn": "sklearn",
    "opencv-python": "cv2",
    "opencv": "cv2",
    "pillow": "PIL",
    "pyyaml": "yaml",
    "python-dotenv": "dotenv",
    "beautifulsoup4": "bs4",
    "beautifulsoup": "bs4",
    "scikit-image": "skimage",
    "pytorch": "torch",
    # Common identity-named packages.
    **{
        name: name
        for name in (
            "numpy",
            "pandas",
            "torch",
            "requests",
            "flask",
            "django",
            "matplotlib",
            "scipy",
            "tensorflow",
            "keras",
            "seaborn",
            "streamlit",
            "plotly",
            "statsmodels",
            "nltk",
            "spacy",
            "transformers",
            "openai",
            "langchain",
            "fastapi",
            "sqlalchemy",
            "pymongo",
            "redis",
            "celery",
            "boto3",
            "xgboost",
            "lightgbm",
            "polars",
            "pytest",
            "jupyter",
            "selenium",
            "pygame",
            "kivy",
            "dash",
            "gradio",
            "uvicorn",
            "aiohttp",
            "httpx",
        )
    },
}

# Words that NL patterns may capture but are never module names.
_MODULE_NOISE_WORDS = frozenset(
    {
        # English
        "the",
        "a",
        "an",
        "it",
        "this",
        "that",
        "my",
        "any",
        "anything",
        "some",
        "something",
        "more",
        "yet",
        "python",
        "pip",
        "library",
        "module",
        "package",
        "installed",
        "internet",
        "wifi",
        "memory",
        "ram",
        "cpu",
        "space",
        "time",
        "computer",
        "laptop",
        "pc",
        "windows",
        "mac",
        "linux",
        "driver",
        "drivers",
        "printer",
        "program",
        "app",
        "apps",
        "idea",
        # Spanish
        "la",
        "el",
        "los",
        "las",
        "un",
        "una",
        "uno",
        "mi",
        "tu",
        "su",
        "este",
        "esta",
        "eso",
        "esto",
        "algo",
        "nada",
        "mas",
        "más",
        "libreria",
        "librería",
        "modulo",
        "módulo",
        "paquete",
        "instalado",
        "instalada",
        "memoria",
        "espacio",
        "tiempo",
        "computadora",
        "impresora",
        "programa",
        "aplicacion",
        "aplicación",
        "conexion",
        "conexión",
        "red",
        "señal",
        "senal",
        "ganas",
        "permisos",
    }
)

# Context hints that make an unknown captured name plausible as a Python module.
_PYTHON_CONTEXT_HINTS = (
    "python",
    "pip",
    "librer",
    "library",
    "module",
    "modulo",
    "package",
    "paquete",
    "import",
    "script",
    "code",
    "codigo",
    "jupyter",
    "notebook",
    "venv",
    "conda",
    "interprete",
    "interpreter",
)

# Intent hints (normalized text) that pair with a known-package mention.
_INSTALL_INTENT_HINTS = (
    "install",
    "instalar",
    "instalad",
    "import",
    "librer",
    "library",
    "module",
    "modulo",
    "package",
    "paquete",
    "pip",
    "falta",
    "faltan",
    "missing",
    "necesito",
    "need",
    "no tengo",
    "don't have",
    "dont have",
    "doesn't have",
    "can't",
    "cant ",
    "cannot",
    "no puedo",
    "no me anda",
    "no funciona",
    "not working",
    "no encuentra",
    "not found",
)

_PYTHON_TRIGGERS = (
    "modulenotfounderror",
    "no module named",
    "importerror",
    "cannot import name",
    "pip install",
    "pip3 install",
)

_PYTHON_ERROR_KEYWORDS = (
    "syntaxerror",
    "indentationerror",
    "nameerror",
    "typeerror",
    "indexerror",
    "syntax error",
    "indentation error",
    "name error",
    "type error",
    "index error",
    "missing indent",
    "typo in variable",
    "maximum index available",
    "invalid syntax",
)

_PYTHON_CODE_TRIGGERS = (
    "def ",
    "print(",
    "if x =",
    "items = ",
    "total = ",
    "import ",
)

# Keyword lexicons are matched against *normalized* (lowercase, accent-free)
# text with word boundaries. A trailing "*" marks a prefix/stem match
# (e.g. "pagina*" matches "pagina" and "paginas").
_NETWORK_KEYWORDS = (
    "internet",
    "wifi",
    "wi-fi",
    "wlan",
    "network",
    "red",
    "conexion*",
    "banda ancha",
    "buffering",
    "latencia",
    "ping",
    "2.4ghz",
    "5ghz",
    "router",
    "modem",
    "senal",
    "signal",
    "pagina*",
    "web",
    "online",
    "streaming",
    "video*",
    "descarga*",
    "download*",
    "navega*",
    "browser",
    "browsing",
    "youtube",
    "netflix",
    "zoom",
)

_RESOURCE_KEYWORDS = (
    "cpu",
    "ram",
    "memory",
    "memoria",
    "ventilador",
    "fan",
    "proceso*",
    "process*",
    "computadora",
    "computer",
    "pc",
    "laptop",
    "notebook",
    "macbook",
    "se traba",
    "traba*",
    "freez*",
    "frozen",
    "congela*",
    "cuelga*",
    "colgad*",
    "lag",
    "laggy",
    "lagging",
    "high usage",
    "consume",
    "consumo",
    "overheat*",
    "caliente",
    "calienta*",
    "hot",
    "ruido",
    "noise",
    "noisy",
    "no responde",
    "unresponsive",
    "stuck",
    "disco",
    "disk",
    "rendimiento",
    "performance",
    "aplicacion*",
    "apps",
)

_SLOW_HINTS = (
    "lento",
    "lenta",
    "lentisim*",
    "slow*",
    "despacio",
    "tarda*",
    "demora*",
    "forever",
    "eternidad",
)

_CLARIFICATION_THRESHOLD = 0.5


def _extract_module(text: str) -> str | None:
    """Return the missing module's top-level import name, if present."""
    for pattern in _MODULE_PATTERNS:
        match = pattern.search(text)
        if match:
            # Keep the top-level package (e.g. "sklearn.tree" -> "sklearn").
            return match.group(1).split(".")[0]
    return None


def _extract_module_natural(text: str) -> str | None:
    """Extract a module name from natural phrasings like "I don't have torch installed".

    Captures are validated to avoid false positives: a captured name is
    accepted if it is a *known* package, or — for unknown names — only when the
    text also contains Python-related context (e.g. "python", "library", "pip").
    """
    norm = _normalize(text)
    has_python_context = any(hint in norm for hint in _PYTHON_CONTEXT_HINTS)
    fallback: str | None = None
    for pattern in _NL_MODULE_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1).split(".")[0]
            lowered = _normalize(candidate)
            if lowered in _MODULE_NOISE_WORDS:
                continue
            known = _KNOWN_PACKAGES.get(lowered)
            if known:
                return known
            if has_python_context and fallback is None:
                fallback = candidate
    return fallback


def _find_known_package(text: str) -> str | None:
    """Return a known package's import name if it is mentioned in the text."""
    for token in re.findall(r"[A-Za-z_][\w-]*", text):
        known = _KNOWN_PACKAGES.get(token.lower())
        if known:
            return known
    return None


def _keyword_regex(keyword: str) -> re.Pattern[str]:
    """Compile a keyword into a word-boundary regex; trailing '*' = prefix match."""
    if keyword.endswith("*"):
        return re.compile(r"\b" + re.escape(keyword[:-1]) + r"\w*")
    return re.compile(r"\b" + re.escape(keyword) + r"\b")


_NETWORK_RES = tuple(_keyword_regex(k) for k in _NETWORK_KEYWORDS)
_RESOURCE_RES = tuple(_keyword_regex(k) for k in _RESOURCE_KEYWORDS)
_SLOW_RES = tuple(_keyword_regex(k) for k in _SLOW_HINTS)


def _count_hits(normalized_text: str, patterns: tuple[re.Pattern[str], ...]) -> int:
    """Count how many keyword patterns match the normalized text."""
    return sum(1 for p in patterns if p.search(normalized_text))


def _build_clarification_question(triage: TriageResult, text: str) -> str:
    """Generate a clarification question when confidence is low."""
    if triage.problem_type == ProblemType.UNKNOWN:
        return (
            "No pude identificar el problema con claridad. "
            "¿Podrías darme más detalles? Por ejemplo, ¿qué mensaje de error "
            "ves exactamente, o qué estabas haciendo cuando ocurrió?"
        )
    if triage.problem_type == ProblemType.PYTHON_MISSING_LIBRARY:
        return (
            "Parece que falta una librería de Python, pero no estoy seguro. "
            "¿Podrías copiar el mensaje de error completo?"
        )
    if triage.problem_type == ProblemType.NETWORK_SLOW:
        return (
            "Parece que tienes un problema de red, pero tengo poca información. "
            "¿Podrías describir qué pruebas de conexión has hecho?"
        )
    if triage.problem_type == ProblemType.HIGH_RESOURCE_USAGE:
        return (
            "Parece que tu computadora está lenta, pero necesito más detalles. "
            "¿Qué programas tienes abiertos y desde cuándo empezó el problema?"
        )
    return "¿Podrías proporcionar más detalles sobre el problema?"


def rule_based_triage(user_input: str, conversation_context: str = "") -> TriageResult:
    """Classify a problem using deterministic rules.

    Args:
        user_input: The raw problem description.
        conversation_context: Optional conversation history context.

    Returns:
        A :class:`TriageResult`.
    """
    text = user_input.lower()
    entities: dict[str, Any] = {}

    enriched = f"{conversation_context}\n{user_input}".strip()
    enriched_lower = enriched.lower()
    enriched_norm = _normalize(enriched)

    # 1. Python missing library (most specific / highest priority).
    #    a) Formal error messages ("No module named 'cv2'") -> 0.95
    #    b) Natural phrasings ("I don't have torch installed") -> 0.85
    #    c) Known package mentioned + install/need intent -> 0.8
    module = _extract_module(enriched)
    confidence = 0.95
    if module is None:
        module = _extract_module_natural(enriched)
        confidence = 0.85
    if module is None and any(hint in enriched_norm for hint in _INSTALL_INTENT_HINTS):
        module = _find_known_package(enriched)
        confidence = 0.8

    has_python_trigger = any(trig in enriched_lower for trig in _PYTHON_TRIGGERS)
    if module or has_python_trigger:
        if module:
            entities["missing_module"] = module
            entities["package_name"] = map_import_to_package(module)
        return TriageResult(
            problem_type=ProblemType.PYTHON_MISSING_LIBRARY,
            confidence=confidence if module else 0.7,
            extracted_entities=entities,
            requires_retrieval=True,
            requires_system_tools=True,
        )

    # 1b. Python syntax/runtime errors.
    has_python_error_trigger = any(kw in text for kw in _PYTHON_ERROR_KEYWORDS) or any(
        kw in text for kw in _PYTHON_CODE_TRIGGERS
    )
    if has_python_error_trigger:
        return TriageResult(
            problem_type=ProblemType.PYTHON_ERROR,
            confidence=0.9,
            extracted_entities=entities,
            requires_retrieval=True,
            requires_system_tools=False,
        )

    # 2. Network vs. high resource usage (accent-insensitive keyword scoring).
    network_hits = _count_hits(enriched_norm, _NETWORK_RES)
    resource_hits = _count_hits(enriched_norm, _RESOURCE_RES)
    has_slow = any(p.search(enriched_norm) for p in _SLOW_RES)

    if network_hits or resource_hits:
        if network_hits > resource_hits:
            confidence = 0.85 if has_slow else 0.7
            return TriageResult(
                problem_type=ProblemType.NETWORK_SLOW,
                confidence=confidence,
                extracted_entities=entities,
                requires_retrieval=True,
                requires_system_tools=True,
            )
        if resource_hits > 0:
            confidence = 0.85 if has_slow else 0.7
            return TriageResult(
                problem_type=ProblemType.HIGH_RESOURCE_USAGE,
                confidence=confidence,
                extracted_entities=entities,
                requires_retrieval=True,
                requires_system_tools=True,
            )

    # 3. A bare "slow" hint with no other signal leans toward resource usage.
    if has_slow:
        return TriageResult(
            problem_type=ProblemType.HIGH_RESOURCE_USAGE,
            confidence=0.5,
            extracted_entities=entities,
            requires_retrieval=True,
            requires_system_tools=True,
        )

    result = TriageResult(
        problem_type=ProblemType.UNKNOWN,
        confidence=0.3,
        extracted_entities=entities,
        requires_retrieval=True,
        requires_system_tools=False,
    )

    # If confidence is low, mark for clarification.
    if result.confidence < _CLARIFICATION_THRESHOLD:
        result.needs_clarification = True
        result.clarification_question = _build_clarification_question(result, text)

    return result


def _llm_triage(user_input: str, conversation_context: str = "") -> TriageResult | None:
    """Attempt LLM-based classification; return ``None`` on any failure."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        from langchain_openai import ChatOpenAI

        from compufix_agents.prompts.triage_prompt import build_triage_messages
    except ImportError:
        logger.info("langchain_openai not available; skipping LLM triage.")
        return None

    try:
        llm = ChatOpenAI(api_key=settings.openai_api_key, model="gpt-4o-mini", temperature=0)
        messages = build_triage_messages(user_input, conversation_context)
        response = llm.invoke(messages)
        raw = response.content if isinstance(response.content, str) else str(response.content)
        # Strip accidental code fences.
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
        result = TriageResult(**data)
        logger.info("LLM triage -> %s (%.2f)", result.problem_type, result.confidence)
        # Mark for clarification if confidence is too low.
        if (
            result.confidence < _CLARIFICATION_THRESHOLD
            and result.problem_type != ProblemType.UNKNOWN
        ):
            result.needs_clarification = True
            result.clarification_question = _build_clarification_question(result, user_input)
        return result
    except Exception as exc:  # pragma: no cover - network/parse failures
        logger.warning("LLM triage failed (%s); falling back to rules.", exc)
        return None


def triage(
    user_input: str,
    use_llm: bool | None = None,
    conversation_context: str = "",
) -> TriageResult:
    """Classify a user problem, preferring the LLM when available.

    Args:
        user_input: The raw problem description.
        use_llm: Force-enable/disable the LLM path. When ``None`` (default),
            the LLM is used only if an API key is configured.
        conversation_context: Optional conversation history context.

    Returns:
        A :class:`TriageResult` (rule-based fallback is always guaranteed).
    """
    if not user_input or not user_input.strip():
        return TriageResult(problem_type=ProblemType.UNKNOWN, confidence=0.0)

    settings = get_settings()
    want_llm = settings.llm_enabled if use_llm is None else use_llm
    if want_llm:
        llm_result = _llm_triage(user_input, conversation_context)
        if llm_result is not None:
            return llm_result

    return rule_based_triage(user_input, conversation_context)

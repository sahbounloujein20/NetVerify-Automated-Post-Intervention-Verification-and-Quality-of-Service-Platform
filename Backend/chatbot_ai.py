"""
chatbot_ai.py — NetVerify assistant (local model through Ollama; Gemini optional)
Project: NetVerify — Tunisie Telecom

Builds a context from the database (global KPIs, plus targeted data when the
question mentions a work-order reference, a technician or a technology), then
lets the model phrase the natural-language answer from that context only.

The model never touches the database: every figure is computed in SQL by
`_construire_contexte()`. Changing provider therefore only changes this file —
the business logic stays identical.

That property is also what carries the authorisation. Because the model may use
nothing but the supplied context, the caller's role is applied while *building*
that context and not through an instruction in the prompt: a technician asking
about a colleague never has the figures put in front of the model in the first
place. An instruction can be talked around; an absent fact cannot. Without this,
the assistant would be the way round the whole role model — "how is TECH-042
doing?" would hand back the name, the phone number and the anomaly count that
`/stats/anomalies-by-technician` refuses.

The call goes through the REST API via `requests`, like ai_comparator.py, and
not through the `google-generativeai` SDK: that one is end-of-life (no longer
maintained and it prints a warning on every import). REST adds no dependency
and freezes the call contract.

Two providers are supported behind the same `generate_answer()`. Ollama is the
default: it runs a small model on the machine itself, so the assistant needs no
key, no quota and no network — the demo survives a dead conference Wi-Fi and an
expired free tier, the two ways this endpoint has failed so far. Since customer
phone numbers and technician names go into the prompt, keeping the inference on
Tunisie Telecom's own machine also means that data never leaves it.

A 1-billion parameter model is enough here because the model only rephrases an
already computed context: nothing is ever asked of its own knowledge.

Gemini remains reachable through AI_PROVIDER for the case where a larger model
is wanted and a key is available.

Configuration:
    AI_PROVIDER      "ollama" (default) or "gemini"

    OLLAMA_MODEL     local model to use (default: llama3.2:1b)
                     -> install it once with `ollama pull llama3.2:1b`
    OLLAMA_URL       Ollama server (default: http://localhost:11434)

    GEMINI_API_KEY   Google AI Studio key (free tier), only when
                     AI_PROVIDER=gemini -> https://aistudio.google.com/apikey
    GEMINI_MODEL     model to use (default: gemini-3.6-flash)
"""

import os
import re
import time

import requests
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import Client, LogFollowup, WorkOrder, Technician
from security import ROLE_TECHNICIAN, SUPERVISION_ROLES

# The "Flash" range: available on the AI Studio free tier and largely
# sufficient here, since the model only rephrases an already computed context.
# Overridable without touching the code.
#
# Google withdraws older models for new keys without removing them from
# ListModels: `gemini-2.5-flash` is still listed but returns 404 "no longer
# available to new users" on generateContent. The default must therefore be a
# current model, and gets updated whenever another withdrawal happens.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

PROVIDER = os.environ.get("AI_PROVIDER", "ollama").strip().lower()

# llama3.2:1b weighs about 1.3 GB and answers in two or three seconds on a
# laptop GPU. Smaller still exists (gemma3:270m), but below one billion
# parameters the model stops honouring "use only the context" and starts
# inventing work-order references — precisely what this assistant must not do.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b").strip()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")

TIMEOUT = 20          # seconds, per attempt
BACKOFFS = [1, 2]     # backoff between attempts (3 tries in total)

# The first Ollama call after a restart loads the weights into VRAM, which the
# 20 s budget of a hosted API does not cover. Subsequent calls are fast: Ollama
# keeps the model resident for five minutes.
OLLAMA_TIMEOUT = 120


class AIProviderError(RuntimeError):
    """Failure attributable to the provider: quota, refused key, service down.

    Distinguished from a local configuration error (missing key) so that the
    API returns 502 (the third party is at fault) rather than 500 (NetVerify is
    at fault).
    """


# Exported so that main.py does not have to know the provider: this tuple is
# what gets translated into HTTP 502 on the API side.
PROVIDER_ERRORS = (AIProviderError,)

SYSTEM_PROMPT = (
    "You are the NetVerify assistant, the network work-order tracking and "
    "quality-of-service verification tool of Tunisie Telecom. Answer in "
    "English, concisely and professionally, with a few relevant emojis if "
    "useful. Use ONLY the data supplied in the context below — never invent "
    "figures, statuses or references. If the requested information is not "
    "present in the context, say so clearly and suggest that the user refines "
    "the question (work-order reference in the ADSL/VDSL/GPON format followed "
    "by a year and a number, technician ID in the TECH-XXX format, or a "
    "technology)."
)

# Factual answer: we want restitution, not creativity.
GENERATION_CONFIG = {
    "maxOutputTokens": 1024,
    "temperature": 0.2,
}


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set on the backend server. "
            "Create a free key at https://aistudio.google.com/apikey, "
            "then configure this environment variable before starting "
            "uvicorn to enable the AI assistant."
        )
    return key


def _query_gemini(prompt: str) -> str:
    """Calls Gemini and returns the generated text.

    Retries on transient errors (429 momentary quota, 5xx); an invalid key
    (401/403) or a malformed request (400) fails immediately, since retrying
    would change nothing.
    """
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": GENERATION_CONFIG,
    }
    # Key passed as a header and not as a URL parameter: a URL ends up in the
    # access logs, a header does not.
    headers = {"x-goog-api-key": _api_key(), "Content-Type": "application/json"}
    url = f"{API_BASE}/{MODEL}:generateContent"

    last_reason = "unknown cause"
    for attempt in range(len(BACKOFFS) + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            last_reason = f"timed out ({TIMEOUT}s)"
        except requests.exceptions.RequestException as exc:
            last_reason = f"service unreachable ({exc.__class__.__name__})"
        else:
            if response.status_code == 200:
                return _extract_text(response.json())

            detail = _error_reason(response)
            if response.status_code in (400, 401, 403, 404):
                # Definitive: refused key, unknown model, invalid request.
                raise AIProviderError(f"HTTP {response.status_code} — {detail}")
            last_reason = f"HTTP {response.status_code} — {detail}"

        if attempt < len(BACKOFFS):
            time.sleep(BACKOFFS[attempt])

    raise AIProviderError(last_reason)


def _error_reason(response: requests.Response) -> str:
    try:
        return response.json().get("error", {}).get("message", response.text[:200])
    except ValueError:
        return response.text[:200] or "unreadable response"


def _extract_text(data: dict) -> str:
    """Extracts the text of a Gemini response, or an empty string if it has none.

    A 200 response does not guarantee text: the prompt may have been blocked by
    a safety filter, or generation may have stopped before the first word.
    Those cases produce an explicit user-facing answer, not an exception.
    """
    blocage = data.get("promptFeedback", {}).get("blockReason")
    if blocage:
        return ""

    for candidat in data.get("candidates", []):
        for part in candidat.get("content", {}).get("parts", []):
            text = part.get("text", "").strip()
            if text:
                return text
    return ""


def _query_ollama(prompt: str) -> str:
    """Calls the local Ollama server and returns the generated text.

    Same contract as `_query_gemini()`: a string on success, AIProviderError on
    a provider failure, RuntimeError on a local configuration problem. The two
    error classes are not decorative — main.py turns the first into 502 and the
    second into 500, and with Ollama the distinction matters more than with a
    hosted API, since here the "provider" is a service NetVerify is responsible
    for starting.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        # Ollama streams token by token by default; the endpoint answers in one
        # block, so a single JSON object is what we want.
        "stream": False,
        "options": {
            "temperature": GENERATION_CONFIG["temperature"],
            "num_predict": GENERATION_CONFIG["maxOutputTokens"],
        },
    }
    url = f"{OLLAMA_URL}/api/chat"

    last_reason = "unknown cause"
    for attempt in range(len(BACKOFFS) + 1):
        try:
            response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
        except requests.exceptions.ConnectionError:
            # Not a third-party outage: the server simply is not running on this
            # machine. Retrying would only delay an error the operator has to
            # fix, so this fails immediately with the command that fixes it.
            raise RuntimeError(
                f"Ollama is not reachable at {OLLAMA_URL}. Start it with "
                "`ollama serve` (or launch the Ollama application), then retry. "
                "To fall back on the hosted provider instead, set AI_PROVIDER=gemini."
            )
        except requests.exceptions.Timeout:
            last_reason = f"timed out ({OLLAMA_TIMEOUT}s)"
        except requests.exceptions.RequestException as exc:
            last_reason = f"service unreachable ({exc.__class__.__name__})"
        else:
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "").strip()

            detail = _error_reason_ollama(response)
            if response.status_code == 404:
                # Ollama answers 404 when the model has never been pulled. Again
                # a local problem with a one-line fix, not a provider fault.
                raise RuntimeError(
                    f"The model \"{OLLAMA_MODEL}\" is not installed. "
                    f"Run `ollama pull {OLLAMA_MODEL}`, then retry. ({detail})"
                )
            if response.status_code == 400:
                raise AIProviderError(f"HTTP 400 — {detail}")
            last_reason = f"HTTP {response.status_code} — {detail}"

        if attempt < len(BACKOFFS):
            time.sleep(BACKOFFS[attempt])

    raise AIProviderError(last_reason)


def _error_reason_ollama(response: requests.Response) -> str:
    try:
        return response.json().get("error", response.text[:200])
    except ValueError:
        return response.text[:200] or "unreadable response"


def _query_model(prompt: str) -> str:
    """Routes to the configured provider.

    An unknown value is refused rather than silently falling back on Gemini: a
    typo in AI_PROVIDER would otherwise spend the quota of a key the operator
    believed unused.
    """
    if PROVIDER == "ollama":
        return _query_ollama(prompt)
    if PROVIDER == "gemini":
        return _query_gemini(prompt)
    raise RuntimeError(
        f"AI_PROVIDER=\"{PROVIDER}\" is not a known provider. "
        "Expected \"gemini\" or \"ollama\"."
    )


def _build_context(
    message: str,
    db: Session,
    role: str = ROLE_TECHNICIAN,
    id_technicien: str | None = None,
) -> str:
    """Assembles what the model is allowed to rephrase, for THIS caller.

    The context is the whole authorisation surface of the assistant: the model
    is instructed to use nothing else, so anything left out of it cannot be
    disclosed. The role is therefore applied here rather than in the prompt — an
    instruction can be talked around, an absent fact cannot.
    """
    parties = []

    total_work_order_count = db.query(func.count(WorkOrder.ref_demande)).scalar()
    total_processed_count = (
        db.query(func.count(WorkOrder.ref_demande))
        .filter(WorkOrder.etat_ot == "Traite")
        .scalar()
    )
    total_anomaly_count = (
        db.query(func.count(LogFollowup.id_log))
        .filter(LogFollowup.statut_test == "ANOMALIE")
        .scalar()
    )
    total_customer_count = db.query(func.count(Client.num_telephone)).scalar()
    parties.append(
        f"Global KPIs: {total_work_order_count} work orders in total, "
        f"{total_processed_count} processed, {total_anomaly_count} anomalies detected, "
        f"{total_customer_count} registered customers."
    )

    ref_match = re.search(r"(adsl|vdsl|gpon)/\d{4}/\d+", message, re.IGNORECASE)
    if ref_match:
        ref_demande = ref_match.group(0).upper()
        rec = (
            db.query(WorkOrder)
            .filter(func.upper(WorkOrder.ref_demande) == ref_demande)
            .first()
        )
        if rec:
            latest_log = (
                db.query(LogFollowup)
                .filter(LogFollowup.ref_demande == rec.ref_demande)
                .order_by(desc(LogFollowup.date_test))
                .first()
            )
            log_txt = (
                f"Latest compliance log: {latest_log.statut_test} — {latest_log.message_log}"
                if latest_log
                else "No compliance log recorded for this work order."
            )
            parties.append(
                f"Work order {rec.ref_demande}: customer {rec.num_appel}, ISP {rec.fsi}, "
                f"status {rec.etat_ot}, assigned technician {rec.id_technicien or 'none'}, "
                f"last updated on {rec.date_etat}. {log_txt}"
            )
        else:
            parties.append(f"No work order found with the reference {ref_demande}.")

    tech_match = re.search(r"tech-\d+", message, re.IGNORECASE)
    if tech_match:
        id_tech = tech_match.group(0).upper()

        # Same rule as the nominative endpoints: a supervisor may ask about any
        # agent, a technician only about themselves. The refusal is written into
        # the context rather than silently dropped, so the model answers "that is
        # restricted" instead of guessing that the technician does not exist.
        allowed = role in SUPERVISION_ROLES or id_tech == (id_technicien or "")
        if not allowed:
            parties.append(
                f"The figures of technician {id_tech} are not available to this "
                "account: individual performance is readable by the supervisor "
                "responsible for the team. Suggest the \"My results\" page, which "
                "shows the caller's own figures."
            )
            tech = None
        else:
            tech = db.query(Technician).filter(
                Technician.id_technicien == id_tech
            ).first()

        if tech:
            total_interventions = (
                db.query(func.count(WorkOrder.ref_demande))
                .filter(WorkOrder.id_technicien == id_tech)
                .scalar()
            )
            processed_by_technician = (
                db.query(func.count(WorkOrder.ref_demande))
                .filter(
                    WorkOrder.id_technicien == id_tech,
                    WorkOrder.etat_ot == "Traite",
                )
                .scalar()
            )
            anomalies_tech = (
                db.query(func.count(LogFollowup.id_log))
                .join(WorkOrder)
                .filter(
                    WorkOrder.id_technicien == id_tech,
                    LogFollowup.statut_test == "ANOMALIE",
                )
                .scalar()
            )
            parties.append(
                f"Technician {id_tech} ({tech.nom_technicien}, phone {tech.telephone_pro}): "
                f"{total_interventions} interventions assigned, {processed_by_technician} closed, "
                f"{anomalies_tech} D+14 anomalies detected."
            )
        elif allowed:
            # Only when the account was entitled to an answer: after a refusal
            # the context already says why, and adding "not found" on top would
            # contradict it — and would leak whether the identifier exists.
            parties.append(f"No technician {id_tech} found in the database.")

    for technology in ["ADSL", "VDSL", "GPON"]:
        if technology.lower() in message.lower():
            anomalies_count = (
                db.query(func.count(LogFollowup.id_log))
                .join(WorkOrder)
                .filter(
                    WorkOrder.ref_demande.like(f"{technology}%"),
                    LogFollowup.statut_test == "ANOMALIE",
                )
                .scalar()
            )
            parties.append(
                f"D+14 compliance anomalies detected on the {technology} technology: "
                f"{anomalies_count}."
            )

    return "\n".join(parties)


def generate_answer(
    message: str,
    db: Session,
    role: str = ROLE_TECHNICIAN,
    id_technicien: str | None = None,
) -> str:
    """Answers a question for a given caller.

    `role` defaults to the least privileged value: a call site that forgets to
    pass it gets the restricted context, never the full one.
    """
    context = _build_context(message, db, role=role, id_technicien=id_technicien)
    text = _query_model(
        f"NetVerify context:\n{context}\n\nUser question: {message}"
    )

    return text or (
        "I could not produce an answer from the available data. "
        "Rephrase your question with a work-order reference, "
        "a technician ID (TECH-XXX) or a technology."
    )

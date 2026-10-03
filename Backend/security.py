"""
security.py — Authentication, authorisation and abuse protection.
Project: NetVerify — Tunisie Telecom

The platform is open to technicians only: every endpoint that exposes customer
data or triggers a processing run therefore requires a valid token. Three
mechanisms share the work:

1. **bcrypt-hashed password.** Hashing is slow by construction and salted
   automatically: even if stolen, the contents of the `utilisateurs` table do
   not give up the passwords. The cost is set by `BCRYPT_COST`.
2. **Signed JWT (HS256).** The server keeps no session in memory: the token
   carries the login and the role, and its signature makes it unforgeable. It
   expires after one working shift.
3. **Service token.** n8n is not a human and has no password: on top of a
   supervisor JWT, the two automation endpoints also accept a shared secret
   passed in the `X-Service-Token` header.

Three roles, from least to most capable:

| Role          | Can do                                                         |
|---------------|----------------------------------------------------------------|
| `technician`  | read the estate, their own results, refresh one line            |
| `supervisor`  | + bulk operations, nominative analytics, audit trail            |
| `service`     | bulk operations only — reserved for automatons                  |

One rule decides where the line falls: **a technician sees their own work, a
supervisor sees comparisons across people.** It covers both halves of the
separation of duties — the estate-wide verification writes the numbers that
evaluate the field agents, so neither the run nor the resulting nominative
ranking may be in the hands of the agents being ranked. A technician is not
left blind for all that: `/stats/my-performance` returns their own figures
against an anonymous team benchmark.

Restricting an action is only half a control. `record_action()` writes the
other half — who asked for what, and whether they were allowed — into
`journal_actions`, readable by supervisors on `/audit`.

Accounts created before the platform was unified on English may still store the
French role values (`technicien`, `superviseur`); `normalise_role()` maps them
onto the canonical form on read, so no migration of the table is required.
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta
from typing import NamedTuple

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import AuditEntry, SessionLocal, User

# ══════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════

ALGORITHM = "HS256"

# Length of a working shift: beyond it, the user must sign in again. Long
# enough not to disturb a working day, short enough that a workstation left
# open does not stay authenticated indefinitely.
SESSION_DURATION_HOURS = int(
    os.environ.get("NETVERIFY_SESSION_HOURS")
    # Name used before the project was unified on English; still honoured so an
    # existing deployment does not silently fall back to the default.
    or os.environ.get("NETVERIFY_DUREE_SESSION_H")
    or "8"
)

# bcrypt cost. 12 ~ 250 ms per verification on an ordinary machine: negligible
# at sign-in, prohibitive for anyone attempting millions of offline guesses.
BCRYPT_COST = 12

ROLE_TECHNICIAN = "technician"
ROLE_SUPERVISOR = "supervisor"
ROLE_SERVICE = "service"
KNOWN_ROLES = (ROLE_TECHNICIAN, ROLE_SUPERVISOR, ROLE_SERVICE)

# The roles that see the estate as a whole, and the people in it. `service` is
# in there because the automaton runs the very operations a supervisor runs; it
# is named once here rather than repeated at every call site.
SUPERVISION_ROLES = (ROLE_SUPERVISOR, ROLE_SERVICE)

# Values written into `journal_actions.resultat`. French, like the rest of the
# schema and the values it already stores; the interface translates them.
OUTCOME_SUCCESS = "succes"
OUTCOME_FAILURE = "echec"
OUTCOME_DENIED = "refus"

# Accounts created before the platform was unified on English still carry the
# original French role values in `utilisateurs.role`. They are translated on
# read rather than migrated: no rewrite of the table is needed, and an operator
# never sees a French role on screen.
_ROLE_ALIASES = {
    "technicien": ROLE_TECHNICIAN,
    "superviseur": ROLE_SUPERVISOR,
    "service": ROLE_SERVICE,
}


def normalise_role(value: str | None) -> str:
    """Canonical (English) form of a role, whatever is stored in the database."""
    text = (value or "").strip().lower()
    return _ROLE_ALIASES.get(text, text)


def _signing_key() -> str:
    """Token signing key.

    No default value is written in the source: a key hard-coded in a repository
    lets anyone who reads it forge an administrator token. If the environment
    variable is missing, a random key is drawn so development stays possible —
    at the cost of a sign-out on every restart, which the warning makes
    explicit.
    """
    key = os.environ.get("NETVERIFY_SECRET_KEY", "").strip()
    if key:
        return key

    print(
        "[security] NETVERIFY_SECRET_KEY is missing: an ephemeral key has been "
        "drawn at random. Sessions will not survive a restart. Set this "
        "variable before any deployment.",
        file=sys.stderr,
    )
    return secrets.token_urlsafe(48)


SIGNING_KEY = _signing_key()

# Secret shared with the automatons (n8n). Missing = no automaton is admitted,
# which is the safe fallback: better a failing workflow than a bulk-processing
# endpoint open to everyone.
SERVICE_TOKEN = os.environ.get("NETVERIFY_SERVICE_TOKEN", "").strip()

# `auto_error=False`: we want to return the 401 ourselves, with the
# `WWW-Authenticate` header, and to distinguish "no token" from "invalid token".
_bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ══════════════════════════════════════════════════
# PASSWORDS
# ══════════════════════════════════════════════════

def hash_password(password: str) -> str:
    """Hashes a password with bcrypt (salt generated automatically)."""
    digest = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_COST)
    )
    return digest.decode("utf-8")


# Hash of a password that belongs to nobody. Used as a decoy when the submitted
# login does not exist: sign-in then costs the same computation time as for a
# real account, and the stopwatch no longer reveals whether a login exists.
# Computed once at start-up.
DECOY_HASH = bcrypt.hashpw(
    secrets.token_bytes(32), bcrypt.gensalt(rounds=BCRYPT_COST)
).decode("utf-8")


def verify_password(password: str, digest: str) -> bool:
    """Compares a password with its hash, in constant time.

    `bcrypt.checkpw` compares byte by byte without short-circuiting: the
    response time does not depend on the number of correct characters, which
    rules out guessing the password by timing the server.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), digest.encode("utf-8"))
    except (ValueError, TypeError):
        # Unreadable hash (empty column, legacy format): refuse.
        return False


# ══════════════════════════════════════════════════
# TOKENS
# ══════════════════════════════════════════════════

def create_token(identifiant: str, role: str) -> tuple[str, int]:
    """Issues a signed JWT. Returns (token, validity in seconds)."""
    duration = timedelta(hours=SESSION_DURATION_HOURS)
    expiration = datetime.utcnow() + duration
    payload = {
        "sub": identifiant,
        "role": role,
        "exp": expiration,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SIGNING_KEY, algorithm=ALGORITHM), int(duration.total_seconds())


def decode_token(token: str) -> dict:
    """Checks the signature and the expiry of a token, or raises a 401."""
    try:
        return jwt.decode(token, SIGNING_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired session ({exc}).",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ══════════════════════════════════════════════════
# JOURNAL OF THE PRIVILEGED ACTIONS
# ══════════════════════════════════════════════════

def record_action(
    auteur: str,
    action: str,
    resultat: str,
    details: str = "",
    role: str | None = None,
) -> None:
    """Writes one row into `journal_actions`.

    Its own session, on purpose, for two reasons. The trace of an attempt must
    survive the rollback of the operation it describes — a run that blew up
    halfway is exactly the one worth keeping. And a journal that is itself
    failing (table absent, database saturated) must never turn a verification
    that did work into a 500: the error goes to stderr, and the caller gets
    their answer.
    """
    db = SessionLocal()
    try:
        db.add(AuditEntry(
            auteur=auteur[:100],
            role=(role or "")[:20] or None,
            action=action[:120],
            resultat=resultat,
            details=details or None,
        ))
        db.commit()
    except Exception as exc:  # pragma: no cover - the journal must not break a run
        db.rollback()
        print(f"[security] unable to journal \"{action}\" by \"{auteur}\": {exc}",
              file=sys.stderr)
    finally:
        db.close()


# ══════════════════════════════════════════════════
# AUTHORISATION DEPENDENCIES
# ══════════════════════════════════════════════════

def _denied(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Authenticated user, or 401.

    The account is re-read from the database on every call: deactivating a
    technician must take effect immediately, without waiting for their token to
    expire.
    """
    if credentials is None or not credentials.credentials:
        raise _denied("Authentication required.")

    payload = decode_token(credentials.credentials)
    identifiant = payload.get("sub")
    if not identifiant:
        raise _denied("Token without a login.")

    user = db.query(User).filter_by(identifiant=identifiant).first()
    if user is None:
        raise _denied("Unknown account.")
    if not user.actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated. Contact the NetVerify administrator.",
        )
    return user


def require_role(*roles_autorises: str):
    """Builds a dependency that restricts access to certain roles.

    A refusal is journalled: an account probing an endpoint reserved for its
    hierarchy is precisely the event an audit trail exists for. A success is
    not — the nominative views are read constantly, and a journal drowned in
    routine reads is a journal nobody reads.
    """

    def checker(request: Request, user: User = Depends(current_user)) -> User:
        role_reel = normalise_role(user.role)
        if role_reel not in roles_autorises:
            record_action(
                user.identifiant, request.url.path, OUTCOME_DENIED,
                details=f"role \"{role_reel}\" outside {', '.join(roles_autorises)}",
                role=role_reel,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action restricted to the roles: {', '.join(roles_autorises)}. "
                       f"Your role is \"{role_reel}\".",
            )
        return user

    return checker


class Caller(NamedTuple):
    """Who is running a bulk operation — the pair the journal needs.

    A plain login string was enough while the identity was only echoed back in
    the response; `journal_actions` also stores the role, and inferring it from
    the shape of the name would put that guess in the wrong place.
    """

    name: str
    role: str


def automaton_or_supervisor(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Caller:
    """Authorises the bulk operations: service token OR supervisor.

    n8n calls these endpoints with no sign-in interface. It presents the shared
    secret; a human presents their JWT. The secret is compared through
    `secrets.compare_digest` so that neither its length nor its prefix leaks
    through the response time.
    """
    presente = (request.headers.get("X-Service-Token") or "").strip()
    if presente and SERVICE_TOKEN and secrets.compare_digest(presente, SERVICE_TOKEN):
        return Caller("n8n (service token)", ROLE_SERVICE)

    if presente and not SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No service token is configured on the server "
                   "(NETVERIFY_SERVICE_TOKEN).",
        )

    user = current_user(credentials, db)
    role_reel = normalise_role(user.role)
    if role_reel not in SUPERVISION_ROLES:
        record_action(
            user.identifiant, request.url.path, OUTCOME_DENIED,
            details=f"bulk operation refused to the role \"{role_reel}\"",
            role=role_reel,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bulk operations are restricted to supervisors.",
        )
    return Caller(user.identifiant, role_reel)

"""
manage_users.py — NetVerify account administration (command line)
Project: NetVerify — Tunisie Telecom

There is deliberately NO HTTP endpoint for account creation: an internal
platform has no open registration, and such an endpoint would be the first door
an attacker tries. Accounts are created from the server, by someone who already
has access.

    # create the first supervisor (password drawn at random and displayed)
    python manage_users.py create --login loujein --name "Loujein F." --role supervisor

    # create a technician, linked to their operational record
    python manage_users.py create --login tech001 --name "Sami Dridi" \
        --role technician --technician TECH-001

    # list, reset, deactivate
    python manage_users.py list
    python manage_users.py password --login tech001
    python manage_users.py deactivate --login tech001
    python manage_users.py activate --login tech001

    # remove an account for good (irreversible, unlike deactivate)
    python manage_users.py delete --login demo01 --yes

    # shared secret for n8n
    python manage_users.py service-token
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys
from datetime import datetime

from database import Base, SessionLocal, Technician, User, engine
from security import ROLE_TECHNICIAN, KNOWN_ROLES, hash_password, normalise_role

# Alphabet without the characters that get confused when copied out (O/0, l/1, I).
READABLE_ALPHABET = (
    "".join(c for c in string.ascii_letters + string.digits if c not in "Ol01I")
)
PASSWORD_LENGTH = 14
MINIMUM_LENGTH = 8


def _random_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(READABLE_ALPHABET) for _ in range(length))


def _ensure_tables() -> None:
    """Creates the `utilisateurs` table if it does not exist yet."""
    Base.metadata.create_all(engine)


def create_account(args) -> int:
    _ensure_tables()
    db = SessionLocal()
    try:
        if db.query(User).filter_by(identifiant=args.identifiant).first():
            print(f"✗ The login \"{args.identifiant}\" already exists.", file=sys.stderr)
            return 1

        if args.technician and not db.query(Technician).filter_by(
            id_technicien=args.technician
        ).first():
            print(f"✗ Technician \"{args.technician}\" not found in the referential.",
                  file=sys.stderr)
            return 1

        password = args.password or _random_password()
        if len(password) < MINIMUM_LENGTH:
            print(f"✗ Password too short ({MINIMUM_LENGTH} characters minimum).",
                  file=sys.stderr)
            return 1

        db.add(User(
            identifiant=args.identifiant,
            nom_complet=args.nom,
            mot_de_passe_hash=hash_password(password),
            role=args.role,
            actif=True,
            id_technicien=args.technician,
        ))
        db.commit()

        print(f"✓ Account \"{args.identifiant}\" created (role: {args.role}).")
        if not args.password:
            print(f"  Password: {password}")
            print("  Write it down now: only its hash is stored and it cannot be "
                  "read back.")
        return 0
    finally:
        db.close()


def list_accounts(args) -> int:
    _ensure_tables()
    db = SessionLocal()
    try:
        accounts = db.query(User).order_by(User.identifiant).all()
        if not accounts:
            print("No account yet. Create the first one with \"create --role supervisor\".")
            return 0

        print(f"{'LOGIN':<16} {'ROLE':<13} {'ACTIVE':<7} {'TECHNICIAN':<12} "
              f"{'LAST SIGN-IN':<20} NAME")
        for account in accounts:
            last_seen = (account.derniere_connexion.strftime("%d/%m/%Y %H:%M")
                        if account.derniere_connexion else "never")
            print(f"{account.identifiant:<16} {normalise_role(account.role):<13} "
                  f"{'yes' if account.actif else 'NO':<7} "
                  f"{account.id_technicien or '—':<12} {last_seen:<20} {account.nom_complet}")
        return 0
    finally:
        db.close()


def change_password(args) -> int:
    db = SessionLocal()
    try:
        account = db.query(User).filter_by(identifiant=args.identifiant).first()
        if account is None:
            print(f"✗ Account \"{args.identifiant}\" not found.", file=sys.stderr)
            return 1

        password = args.password or _random_password()
        if len(password) < MINIMUM_LENGTH:
            print(f"✗ Password too short ({MINIMUM_LENGTH} characters minimum).",
                  file=sys.stderr)
            return 1

        account.mot_de_passe_hash = hash_password(password)
        db.commit()
        print(f"✓ Password of \"{args.identifiant}\" has been reset.")
        if not args.password:
            print(f"  New password: {password}")
        return 0
    finally:
        db.close()


def _toggle_active(identifiant: str, actif: bool) -> int:
    db = SessionLocal()
    try:
        account = db.query(User).filter_by(identifiant=identifiant).first()
        if account is None:
            print(f"✗ Account \"{identifiant}\" not found.", file=sys.stderr)
            return 1
        account.actif = actif
        db.commit()
        # Deactivation takes effect on the next call: `utilisateur_courant`
        # re-reads the account from the database on every request, without
        # waiting for the already issued token to expire.
        print(f"✓ Account \"{identifiant}\" {'activated' if actif else 'deactivated'}.")
        return 0
    finally:
        db.close()


def deactivate(args) -> int:
    return _toggle_active(args.identifiant, False)


def activate(args) -> int:
    return _toggle_active(args.identifiant, True)


def delete_account(args) -> int:
    """Removes an account for good.

    Deactivation is the usual answer when someone leaves: the row stays, and
    with it the trace of who signed in and when. Deletion is for the accounts
    that should never have existed — a demonstration account, a typo in a
    login. It is irreversible, hence the explicit `--yes`.
    """
    db = SessionLocal()
    try:
        account = db.query(User).filter_by(identifiant=args.identifiant).first()
        if account is None:
            print(f"✗ Account \"{args.identifiant}\" not found.", file=sys.stderr)
            return 1

        if not args.yes:
            print(f"✗ Deleting \"{args.identifiant}\" ({account.nom_complet}, "
                  f"{normalise_role(account.role)}) is irreversible. "
                  f"Add --yes to confirm.", file=sys.stderr)
            return 1

        db.delete(account)
        db.commit()
        print(f"✓ Account \"{args.identifiant}\" deleted.")
        return 0
    finally:
        db.close()


def service_token_command(args) -> int:
    """Proposes a shared secret for the automatons (n8n)."""
    token = secrets.token_urlsafe(32)
    print("Service token to share with n8n:\n")
    print(f"  {token}\n")
    print("To be set on the backend side:")
    print(f'  $env:NETVERIFY_SERVICE_TOKEN = "{token}"')
    print("\nThen in every n8n HTTP node, add the header:")
    print(f"  X-Service-Token: {token}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NetVerify account administration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sous = parser.add_subparsers(dest="commande", required=True)

    p_create = sous.add_parser("create", help="create an account")
    p_create.add_argument("--login", dest="identifiant", required=True)
    p_create.add_argument("--name", dest="nom", required=True)
    p_create.add_argument("--role", default=ROLE_TECHNICIAN, choices=KNOWN_ROLES)
    p_create.add_argument("--technician", dest="technician", default=None,
                         help="id_technicien from the referential, if the account has one")
    p_create.add_argument("--password", dest="password", default=None,
                         help="default: drawn at random and displayed once")
    p_create.set_defaults(fonction=create_account)

    p_list = sous.add_parser("list", help="list the accounts")
    p_list.set_defaults(fonction=list_accounts)

    p_mdp = sous.add_parser("password", help="reset a password")
    p_mdp.add_argument("--login", dest="identifiant", required=True)
    p_mdp.add_argument("--password", dest="password", default=None)
    p_mdp.set_defaults(fonction=change_password)

    p_off = sous.add_parser("deactivate", help="deactivate an account")
    p_off.add_argument("--login", dest="identifiant", required=True)
    p_off.set_defaults(fonction=deactivate)

    p_on = sous.add_parser("activate", help="reactivate an account")
    p_on.add_argument("--login", dest="identifiant", required=True)
    p_on.set_defaults(fonction=activate)

    p_del = sous.add_parser("delete", help="delete an account for good")
    p_del.add_argument("--login", dest="identifiant", required=True)
    p_del.add_argument("--yes", action="store_true",
                      help="confirm the deletion, which cannot be undone")
    p_del.set_defaults(fonction=delete_account)

    p_token = sous.add_parser("service-token", help="generate a secret for n8n")
    p_token.set_defaults(fonction=service_token_command)

    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    sys.exit(arguments.fonction(arguments))

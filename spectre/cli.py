"""``spectre`` CLI: ``spectre`` / ``spectre start`` runs the app with uvicorn (a thin convenience
wrapper, not a service manager); ``spectre admin <email>`` promotes/demotes the strategy-layer
admin who manages management areas (:mod:`spectre.core.management`).
"""

from __future__ import annotations

import argparse
import sys


def _cmd_start(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("spectre.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def _cmd_admin(args: argparse.Namespace) -> int:
    from .core import accounts
    from .core.db import init_db

    init_db()
    try:
        user = accounts.set_admin(args.email, not args.revoke)
    except ValueError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    state = "n'est plus administrateur" if args.revoke else "est administrateur"
    print(f"{user.email} {state}.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="spectre", description="Suivi d'expériences - Spectre")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.set_defaults(func=_cmd_start)

    sub = parser.add_subparsers()
    start = sub.add_parser("start", help="démarrer le serveur (comportement par défaut)")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=8000)
    start.add_argument("--reload", action="store_true")
    start.set_defaults(func=_cmd_start)

    admin = sub.add_parser("admin", help="promouvoir (ou --revoke) un compte au rôle administrateur")
    admin.add_argument("email")
    admin.add_argument("--revoke", action="store_true", help="retirer le rôle administrateur")
    admin.set_defaults(func=_cmd_admin)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

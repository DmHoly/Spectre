"""``spectre start`` - run the app with uvicorn. A thin convenience wrapper, not a service
manager (unlike ``follow_api``'s pidfile-based start/stop): Spectre is meant to run as one
long-lived process per deployment, started the ordinary way (a process manager, a container).
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="spectre", description="Suivi d'expériences - Spectre")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("spectre.api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

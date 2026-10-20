"""Command-line entry point for an installed NIS2 Auditor package."""
from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="nis2-auditor", description="Auditeur documentaire NIS2 local")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Démarrer l'interface et l'API")
    serve.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute (défaut : 127.0.0.1)")
    serve.add_argument("--port", type=int, default=int(os.getenv("NIS2_PORT", "8000")))
    commands.add_parser("build-catalog", help="Télécharger et reconstruire le catalogue ReCyF local")
    args = parser.parse_args()

    if args.command == "build-catalog":
        from .recyf import OUTPUT, build

        catalog = build()
        print(f"{len(catalog['requirements'])} mesures ReCyF enregistrées dans {OUTPUT}")
    else:
        import uvicorn

        uvicorn.run("nis2_auditor.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

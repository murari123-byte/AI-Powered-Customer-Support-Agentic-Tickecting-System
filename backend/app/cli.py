"""Command-line admin tasks.

    .venv/bin/python -m app.cli create-admin --email admin@example.com --name "Site Admin"
    .venv/bin/python -m app.cli seed-teams      # the teams AI triage routes tickets to
    .venv/bin/python -m app.cli load-knowledge ../knowledge-base   # needs Ollama running

Sign-up only creates customers, so the very first admin is created here. The password is typed
in (hidden), not passed as an argument, so it never lands in your shell history. For scripts,
set ADMIN_PASSWORD instead.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_service
from app.core.roles import Role
from app.db.session import session_factory
from app.models import KnowledgeDocument
from app.schemas.auth import RegisterRequest
from app.services.auth_service import EmailAlreadyRegisteredError, create_user
from app.services.document_processing import ALLOWED_EXTENSIONS, InvalidDocumentError
from app.services.knowledge_service import create_document, process_document
from app.services.team_service import TeamNameTakenError, create_team
from app.services.triage_service import TEAM_FOR_CATEGORY


def create_admin(db: Session, *, email: str, name: str, password: str) -> int:
    """Create an ADMIN user. Returns an exit code: 0 ok, 1 email taken, 2 invalid input."""
    try:
        data = RegisterRequest(email=email, password=password, full_name=name)  # same rules as sign-up
    except ValidationError as exc:
        print(f"Invalid input: {exc.errors()[0]['msg']}", file=sys.stderr)
        return 2
    try:
        user = create_user(db, email=data.email, password=data.password, full_name=data.full_name, role=Role.ADMIN)
    except EmailAlreadyRegisteredError:
        print(f"A user with email {data.email} already exists.", file=sys.stderr)
        return 1
    print(f"Created admin {user.email}")
    return 0


def seed_teams(db: Session) -> list[str]:
    """Create the teams AI triage routes to (skips any that already exist). Returns the new names."""
    created = []
    for name in sorted(set(TEAM_FOR_CATEGORY.values())):
        try:
            create_team(db, name=name, description="Created by seed-teams")
            created.append(name)
        except TeamNameTakenError:
            pass
    return created


def load_knowledge(db: Session, folder: Path) -> list[str]:
    """Add every .md/.txt/.pdf file in `folder` and embed it right away (no worker needed).
    Files already in the knowledge base (same file name) are skipped. Returns one line per file."""
    report = []
    existing = set(db.execute(select(KnowledgeDocument.filename)).scalars())
    for path in sorted(p for p in folder.iterdir() if p.suffix.lower() in ALLOWED_EXTENSIONS):
        if path.name in existing:
            report.append(f"skipped {path.name} (already loaded)")
            continue
        try:
            document = create_document(db, filename=path.name, data=path.read_bytes(), title=None, uploaded_by=None)
        except InvalidDocumentError as exc:
            report.append(f"FAILED  {path.name}: {exc}")
            continue
        document = process_document(db, get_ai_service(), document.id)
        report.append(f"{document.status:7} {path.name}: {document.chunk_count} chunks")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="create a user with the ADMIN role")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    commands.add_parser("seed-teams", help="create the teams that AI triage routes tickets to")
    knowledge = commands.add_parser("load-knowledge", help="add all documents in a folder to the knowledge base")
    knowledge.add_argument("folder", type=Path)
    args = parser.parse_args()

    if args.command == "load-knowledge":
        with session_factory()() as db:
            for line in load_knowledge(db, args.folder):
                print(line)
        return 0

    if args.command == "seed-teams":
        with session_factory()() as db:
            created = seed_teams(db)
        print(f"Created teams: {', '.join(created)}" if created else "All teams already exist")
        return 0

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
    with session_factory()() as db:
        return create_admin(db, email=args.email, name=args.name, password=password)


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import json
import os

from .config import DATA, PACKAGE_ROOT

CATALOG_PATH = PACKAGE_ROOT / "catalog_data" / "nis2-demo.json"
RECYF_PATH = DATA / "recyf-v2.5-catalog.json"
BUNDLED_RECYF_PATH = PACKAGE_ROOT / "catalog_data" / "recyf-v2.5-catalog.json"


def load_catalog() -> dict:
    if os.getenv("CATALOG_MODE", "demo") == "recyf":
        path = RECYF_PATH if RECYF_PATH.exists() else BUNDLED_RECYF_PATH
    else:
        path = CATALOG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def applicability(requirement: dict, profile: dict) -> tuple[str, str]:
    entity_type = profile.get("entity_type", "unknown")
    if entity_type not in ("essential", "important"):
        return "undetermined", "Catégorie d'entité non confirmée dans le profil."
    if requirement.get("essential_only") and entity_type != "essential":
        return "not_applicable", "Mesure indiquée pour les entités essentielles dans le catalogue chargé."
    return "applicable", "Applicable selon le profil déclaré ; à confirmer par un auditeur."


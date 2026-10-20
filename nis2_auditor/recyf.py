"""Build a local, versioned ReCyF catalog from the ANSSI working PDF."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

import pymupdf

from .config import DATA

SOURCE = "https://messervices.cyber.gouv.fr/documents-ressources/20260317_NIS_V2_ReCyF_v2.5.pdf"
PDF = DATA / "recyf-v2.5.pdf"
OUTPUT = DATA / "recyf-v2.5-catalog.json"
IDENTIFIER = re.compile(r"(?m)^\s*(\d+(?:\.[A-Z])?\.\d+-(?:EI/EE|EE|EI))\s*$")
STOP = {"entite", "systeme", "information", "mesures", "securite", "pour", "dans", "avec",
        "cette", "chaque", "toute", "leurs", "celle", "ainsi", "sont", "fait", "doit", "elle",
        "leur", "dont", "afin", "mise", "oeuvre", "entre", "cette", "prevue", "presente"}


def clean(text: str) -> str:
    text = re.sub(r"RECYF : RÉFÉRENTIEL DE CYBERSÉCURITÉ FRANCE.*?(?=\n)", "", text)
    text = re.sub(r"DOCUMENT DE TRAVAIL|VERSION DE TRAVAIL", "", text)
    text = re.sub(r"\b(?:Oui|Non)\s+(?:Oui|Non)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build() -> dict:
    PDF.parent.mkdir(parents=True, exist_ok=True)
    if not PDF.exists():
        urllib.request.urlretrieve(SOURCE, PDF)
    pdf = pymupdf.open(PDF)
    try:
        requirements = []
        for page_number in range(7, min(len(pdf), 38) + 1):
            text = pdf[page_number - 1].get_text()
            found = list(IDENTIFIER.finditer(text))
            for index, match in enumerate(found):
                end = found[index + 1].start() if index + 1 < len(found) else len(text)
                passage = text[match.end():end]
                split = re.search(r"(?m)^\s*(?:Oui|Non)\s*$", passage)
                if split:
                    passage = passage[:split.start()]
                summary = clean(passage)
                if not summary or len(summary) < 15:
                    raise ValueError(f"Texte absent pour {match.group(1)} page {page_number}")
                words = re.findall(r"[A-Za-zÀ-ÿ]{6,}", summary.lower())
                terms = []
                for word in words:
                    if word not in STOP and word not in terms:
                        terms.append(word)
                identifier = match.group(1)
                requirements.append({
                    "id": identifier,
                    "title": summary[:95] + ("…" if len(summary) > 95 else ""),
                    "summary": summary,
                    "keywords": terms[:12],
                    "essential_only": identifier.endswith("-EE"),
                    "page": page_number,
                    "source_url": SOURCE,
                })
        ids = [r["id"] for r in requirements]
        if len(ids) != len(set(ids)) or len(ids) < 140:
            raise ValueError(f"Extraction incomplète ou doublons : {len(ids)} lignes, {len(set(ids))} identifiants")
        result = {
            "id": "recyf-v2.5-2026-03-17",
            "title": "ReCyF v2.5 — document de travail ANSSI",
            "disclaimer": "Version de travail. Texte extrait automatiquement du PDF officiel ; vérifier chaque ligne et sa portée avant usage réel.",
            "source_url": SOURCE,
            "requirements": requirements,
        }
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        pdf.close()


if __name__ == "__main__":
    result = build()
    print(f"{len(result['requirements'])} mesures ReCyF enregistrées dans {OUTPUT}")


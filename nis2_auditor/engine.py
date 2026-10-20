from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from . import ai, parsers
from .catalog import applicability, load_catalog
from .config import FILES
from .db import connect, now, uid


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in plain if not unicodedata.combining(c))


def score(text: str, requirement: dict) -> float:
    hay = normalize(text)
    hits = sum(1 for phrase in requirement["keywords"] if normalize(phrase) in hay)
    terms = set(re.findall(r"[a-z0-9]{4,}", normalize(requirement["title"] + " " + requirement["summary"])))
    overlap = sum(1 for term in terms if term in hay)
    return hits * 5 + overlap * 0.3


def parse_document(document_id: str) -> None:
    with connect() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if doc is None:
            return
        db.execute("UPDATE documents SET status='processing',error=NULL WHERE id=?", (document_id,))
    try:
        path = FILES / f"{document_id}{doc['ext']}"
        elements, pages, note = parsers.parse(path, doc["ext"], document_id)
        with connect() as db:
            db.execute("DELETE FROM elements WHERE document_id=?", (document_id,))
            for element in elements:
                db.execute("INSERT INTO elements(id,document_id,kind,locator,text,metadata_json) VALUES(?,?,?,?,?,?)",
                           (uid(), document_id, element["kind"], element["locator"],
                            element["text"], json.dumps(element["metadata"], ensure_ascii=False)))
            db.execute("UPDATE documents SET status=?,error=?,page_count=? WHERE id=?",
                       ("partial" if note else "ready", note, pages, document_id))
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE documents SET status='failed',error=? WHERE id=?", (str(exc)[:1000], document_id))


def _valid_evidence(raw: list, candidate_by_id: dict) -> list[dict]:
    accepted = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        element = candidate_by_id.get(item.get("element_id"))
        quote = str(item.get("quote", "")).strip()
        if element and quote and normalize(quote) in normalize(element["text"]):
            accepted.append({"element_id": element["id"], "quote": quote,
                             "explanation": str(item.get("explanation", ""))[:500]})
    return accepted[:8]


def run_audit(audit_id: str) -> None:
    catalog = load_catalog()
    with connect() as db:
        audit = db.execute("SELECT * FROM audits WHERE id=?", (audit_id,)).fetchone()
        if not audit:
            return
        db.execute("UPDATE audits SET status='processing',updated_at=? WHERE id=?", (now(), audit_id))
    try:
        profile = json.loads(audit["profile_json"])
        with connect() as db:
            rows = db.execute("""SELECT e.*,d.name AS document_name,d.status AS document_status
                              FROM elements e JOIN documents d ON d.id=e.document_id
                              WHERE d.audit_id=? AND d.status IN ('ready','partial') AND e.kind!='warning'""",
                              (audit_id,)).fetchall()
            incomplete = db.execute("""SELECT COUNT(*) FROM documents WHERE audit_id=?
                                      AND status IN ('partial','failed')""", (audit_id,)).fetchone()[0]
        elements = [dict(row) for row in rows]
        for requirement in catalog["requirements"]:
            app, app_reason = applicability(requirement, profile)
            candidates = sorted(((score(el["text"], requirement), el) for el in elements),
                                key=lambda pair: pair[0], reverse=True)
            candidates = [el for rank, el in candidates if rank >= 3][:12]
            if app == "not_applicable":
                status, rationale, source, ev = "not_applicable", app_reason, "rule", []
            elif app == "undetermined":
                status, rationale, source, ev = "uncertain", app_reason, "rule", []
            elif candidates and ai.enabled():
                try:
                    answer = ai.assess(requirement, candidates) or {}
                    ev = _valid_evidence(answer.get("evidence", []), {el["id"]: el for el in candidates})
                    status = answer["status"]
                    if status in {"supported", "partially_supported"} and not ev:
                        status = "uncertain"
                    rationale = str(answer.get("rationale", ""))[:2000]
                    source = "ai"
                except Exception as exc:
                    status, rationale, source = "uncertain", f"Analyse IA indisponible : {str(exc)[:250]}", "fallback"
                    ev = []
            elif candidates:
                status = "uncertain"
                rationale = "Passages candidats trouvés. Leur pertinence et l'application effective du contrôle nécessitent une revue."
                source = "local_search"
                ev = [{"element_id": el["id"], "quote": el["text"][:300], "explanation": "Correspondance documentaire candidate"}
                      for el in candidates[:5]]
            else:
                status = "uncertain" if incomplete else "no_evidence"
                rationale = ("Aucun passage trouvé et au moins un document est partiellement lu ou en échec ; la recherche est incomplète."
                             if incomplete else
                             "Aucune preuve trouvée dans les documents traités ; cela ne démontre pas l'absence du contrôle.")
                source, ev = "local_search", []
            with connect() as db:
                old = db.execute("SELECT id,reviewed FROM assessments WHERE audit_id=? AND requirement_id=?",
                                 (audit_id, requirement["id"])).fetchone()
                assessment_id = old["id"] if old else uid()
                if old:
                    db.execute("DELETE FROM evidence WHERE assessment_id=?", (assessment_id,))
                    db.execute("UPDATE assessments SET applicability=?,status=?,rationale=?,source=?,reviewed=0,reviewer_note='',updated_at=? WHERE id=?",
                               (app, status, rationale, source, now(), assessment_id))
                else:
                    db.execute("INSERT INTO assessments(id,audit_id,requirement_id,applicability,status,rationale,source,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                               (assessment_id, audit_id, requirement["id"], app, status, rationale, source, now()))
                for item in ev:
                    db.execute("INSERT INTO evidence(id,assessment_id,element_id,quote,explanation) VALUES(?,?,?,?,?)",
                               (uid(), assessment_id, item["element_id"], item["quote"], item["explanation"]))
        with connect() as db:
            db.execute("UPDATE audits SET status='ready',updated_at=? WHERE id=?", (now(), audit_id))
    except Exception:
        with connect() as db:
            db.execute("UPDATE audits SET status='failed',updated_at=? WHERE id=?", (now(), audit_id))
        raise


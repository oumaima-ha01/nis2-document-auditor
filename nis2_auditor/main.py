from __future__ import annotations

import csv
import hashlib
import io
import json
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, engine
from .catalog import load_catalog
from .config import FILES, MAX_UPLOAD_BYTES, PACKAGE_ROOT
from .db import connect, init_db, now, uid

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NIS2 Auditor Local", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
executor = ThreadPoolExecutor(max_workers=2)
ALLOWED = {".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}
MAGIC = {".pdf": b"%PDF", ".docx": b"PK", ".xlsx": b"PK", ".png": b"\x89PNG", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8"}


class AuditCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    entity_type: str = "unknown"
    sector: str = ""
    country: str = "France"


class ProfileUpdate(BaseModel):
    entity_type: str
    sector: str = ""
    country: str = "France"


class ReviewInput(BaseModel):
    status: str
    note: str = Field(min_length=2, max_length=2000)


@app.get("/", response_class=HTMLResponse)
def home():
    return (PACKAGE_ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {"ok": True, "ai_text": ai.enabled(), "ai_vision": ai.enabled("vision")}


@app.get("/api/catalog")
def catalog():
    return load_catalog()


@app.post("/api/audits")
def create_audit(payload: AuditCreate):
    if payload.entity_type not in {"unknown", "important", "essential"}:
        raise HTTPException(400, "Catégorie d'entité invalide")
    audit_id = uid()
    profile = payload.model_dump(exclude={"name"})
    with connect() as db:
        db.execute("INSERT INTO audits(id,name,profile_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                   (audit_id, payload.name, json.dumps(profile, ensure_ascii=False), "draft", now(), now()))
    return {"id": audit_id, "name": payload.name, "profile": profile, "status": "draft"}


@app.get("/api/audits")
def list_audits():
    with connect() as db:
        rows = db.execute("SELECT * FROM audits ORDER BY created_at DESC").fetchall()
    return [{**dict(row), "profile": json.loads(row["profile_json"])} for row in rows]


def require_audit(audit_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM audits WHERE id=?", (audit_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Audit introuvable")
    return row


@app.put("/api/audits/{audit_id}/profile")
def update_profile(audit_id: str, payload: ProfileUpdate):
    audit = require_audit(audit_id)
    if audit["status"] == "processing":
        raise HTTPException(409, "Attendez la fin de l'analyse avant de modifier le profil")
    if payload.entity_type not in {"unknown", "important", "essential"}:
        raise HTTPException(400, "Catégorie d'entité invalide")
    with connect() as db:
        db.execute("UPDATE audits SET profile_json=?,status='draft',updated_at=? WHERE id=?",
                   (payload.model_dump_json(), now(), audit_id))
        db.execute("DELETE FROM assessments WHERE audit_id=?", (audit_id,))
    return payload


@app.get("/api/audits/{audit_id}")
def get_audit(audit_id: str):
    row = require_audit(audit_id)
    return {**dict(row), "profile": json.loads(row["profile_json"])}


@app.post("/api/audits/{audit_id}/documents")
async def upload_document(audit_id: str, file: UploadFile = File(...)):
    audit = require_audit(audit_id)
    if audit["status"] == "processing":
        raise HTTPException(409, "Attendez la fin de l'analyse avant d'importer un document")
    original_name = Path(file.filename or "document").name[:200]
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Format non pris en charge")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Fichier vide ou trop volumineux")
    if ext in MAGIC and not content.startswith(MAGIC[ext]):
        raise HTTPException(415, "Le contenu ne correspond pas à l'extension")
    doc_id = uid()
    (FILES / f"{doc_id}{ext}").write_bytes(content)
    with connect() as db:
        db.execute("INSERT INTO documents(id,audit_id,name,ext,sha256,status,created_at) VALUES(?,?,?,?,?,?,?)",
                   (doc_id, audit_id, original_name, ext, hashlib.sha256(content).hexdigest(), "queued", now()))
        db.execute("UPDATE audits SET status='draft',updated_at=? WHERE id=?", (now(), audit_id))
        db.execute("DELETE FROM assessments WHERE audit_id=?", (audit_id,))
    executor.submit(engine.parse_document, doc_id)
    return {"id": doc_id, "name": original_name, "status": "queued"}


@app.get("/api/audits/{audit_id}/documents")
def documents(audit_id: str):
    require_audit(audit_id)
    with connect() as db:
        rows = db.execute("SELECT * FROM documents WHERE audit_id=? ORDER BY created_at DESC", (audit_id,)).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/documents/{document_id}/elements")
def elements(document_id: str):
    with connect() as db:
        doc = db.execute("SELECT id FROM documents WHERE id=?", (document_id,)).fetchone()
        if not doc:
            raise HTTPException(404, "Document introuvable")
        rows = db.execute("SELECT * FROM elements WHERE document_id=? ORDER BY rowid LIMIT 5000", (document_id,)).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/documents/{document_id}/file")
def document_file(document_id: str):
    with connect() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if not doc:
        raise HTTPException(404, "Document introuvable")
    media_types = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                   ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".csv": "text/csv",
                   ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    return FileResponse(FILES / f"{document_id}{doc['ext']}", filename=doc["name"],
                        media_type=media_types.get(doc["ext"]), content_disposition_type="inline")


@app.get("/api/elements/{element_id}/preview.png")
def element_preview(element_id: str):
    with connect() as db:
        row = db.execute("""SELECT e.metadata_json,d.id AS document_id,d.ext
                            FROM elements e JOIN documents d ON d.id=e.document_id WHERE e.id=?""",
                         (element_id,)).fetchone()
    if not row or row["ext"] != ".pdf":
        raise HTTPException(404, "Aperçu PDF introuvable")
    metadata = json.loads(row["metadata_json"])
    page_number = int(metadata.get("page", 1))
    pdf = pymupdf.open(FILES / f"{row['document_id']}.pdf")
    try:
        if page_number < 1 or page_number > len(pdf):
            raise HTTPException(404, "Page introuvable")
        page = pdf[page_number - 1]
        bbox = metadata.get("bbox")
        if bbox and len(bbox) == 4:
            page.draw_rect(pymupdf.Rect(*bbox), color=(0, 0.62, 0.48), width=2, overlay=True)
        image = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        return Response(image.tobytes("png"), media_type="image/png")
    finally:
        pdf.close()


@app.post("/api/audits/{audit_id}/run")
def start_run(audit_id: str):
    audit = require_audit(audit_id)
    if audit["status"] == "processing":
        raise HTTPException(409, "Analyse déjà en cours")
    with connect() as db:
        pending = db.execute("SELECT COUNT(*) FROM documents WHERE audit_id=? AND status IN ('queued','processing')", (audit_id,)).fetchone()[0]
        ready = db.execute("SELECT COUNT(*) FROM documents WHERE audit_id=? AND status IN ('ready','partial')", (audit_id,)).fetchone()[0]
    if pending:
        raise HTTPException(409, "Attendez la fin de la lecture des documents")
    if not ready:
        raise HTTPException(409, "Importez au moins un document lisible")
    with connect() as db:
        changed = db.execute("UPDATE audits SET status='processing',updated_at=? WHERE id=? AND status!='processing'",
                             (now(), audit_id)).rowcount
    if not changed:
        raise HTTPException(409, "Analyse déjà en cours")
    executor.submit(engine.run_audit, audit_id)
    return {"status": "processing"}


@app.get("/api/audits/{audit_id}/matrix")
def matrix(audit_id: str):
    require_audit(audit_id)
    catalog_data = load_catalog()
    with connect() as db:
        assessment_rows = db.execute("SELECT * FROM assessments WHERE audit_id=?", (audit_id,)).fetchall()
        evidence_rows = db.execute("""SELECT v.*,e.document_id,e.locator,e.text,e.metadata_json,d.name AS document_name
                                  FROM evidence v JOIN elements e ON e.id=v.element_id
                                  JOIN documents d ON d.id=e.document_id
                                  JOIN assessments a ON a.id=v.assessment_id WHERE a.audit_id=?""", (audit_id,)).fetchall()
    assessments = {row["requirement_id"]: dict(row) for row in assessment_rows}
    by_assessment = {}
    for row in evidence_rows:
        by_assessment.setdefault(row["assessment_id"], []).append(dict(row))
    return [{**req, "assessment": assessments.get(req["id"]),
             "evidence": by_assessment.get(assessments[req["id"]]["id"], []) if req["id"] in assessments else []}
            for req in catalog_data["requirements"]]


@app.post("/api/assessments/{assessment_id}/review")
def review(assessment_id: str, payload: ReviewInput):
    if payload.status not in {"supported", "partially_supported", "no_evidence", "conflicting_evidence", "uncertain", "not_applicable"}:
        raise HTTPException(400, "Statut invalide")
    with connect() as db:
        row = db.execute("SELECT id FROM assessments WHERE id=?", (assessment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Constat introuvable")
        db.execute("UPDATE assessments SET status=?,reviewed=1,reviewer_note=?,updated_at=? WHERE id=?",
                   (payload.status, payload.note, now(), assessment_id))
    return {"id": assessment_id, "status": payload.status, "reviewed": True}


@app.get("/api/audits/{audit_id}/export.csv")
def export_csv(audit_id: str):
    rows = matrix(audit_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Exigence", "Titre", "Applicabilité", "Statut", "Revu", "Justification", "Preuves"])
    for row in rows:
        a = row["assessment"] or {}
        writer.writerow([row["id"], row["title"], a.get("applicability", ""), a.get("status", ""),
                         a.get("reviewed", ""), a.get("rationale", ""),
                         " ; ".join(f"{e['document_name']} {e['locator']}: {e['quote']}" for e in row["evidence"])])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=nis2-audit-{audit_id[:8]}.csv"})


@app.get("/api/audits/{audit_id}/export.json")
def export_json(audit_id: str):
    audit = get_audit(audit_id)
    catalog_data = load_catalog()
    payload = {
        "exported_at": now(),
        "audit": {key: audit[key] for key in ("id", "name", "profile", "status", "created_at", "updated_at")},
        "catalog": {key: catalog_data[key] for key in ("id", "title", "source_url")},
        "matrix": matrix(audit_id),
    }
    return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=nis2-audit-{audit_id[:8]}.json"})


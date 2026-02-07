from datetime import datetime
import json
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from pipeline import OUT_IMG_DIR, REPORT_PATH, SUPPORTED_EXTS, process_file

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"
FRONTEND_DIR = BASE_DIR / "frontend"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            page_num INTEGER NOT NULL,
            language TEXT NOT NULL,
            image_path TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            pii_type TEXT NOT NULL,
            text_sample TEXT NOT NULL,
            confidence REAL NOT NULL,
            bbox_json TEXT NOT NULL,
            FOREIGN KEY(page_id) REFERENCES pages(id)
        )
        """
    )
    conn.commit()
    conn.close()


@app.route("/")
def root():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/frontend/<path:path>")
def frontend_asset(path):
    return send_from_directory(FRONTEND_DIR, path)


@app.route("/out/redacted_images/<path:filename>")
def redacted_image(filename):
    return send_from_directory(OUT_IMG_DIR, filename)


@app.route("/api/report")
def report():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            documents.filename,
            documents.stored_path,
            documents.sha256,
            pages.page_num,
            pages.language,
            pages.image_path,
            detections.pii_type,
            detections.text_sample,
            detections.confidence,
            detections.bbox_json
        FROM pages
        JOIN documents ON pages.document_id = documents.id
        LEFT JOIN detections ON detections.page_id = pages.id
        ORDER BY documents.id DESC, pages.page_num ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()

    report_entries = {}
    for row in rows:
        key = (row["stored_path"], row["page_num"])
        if key not in report_entries:
            report_entries[key] = {
                "file": row["stored_path"],
                "file_hash": row["sha256"],
                "page": row["page_num"],
                "language": row["language"],
                "detections": [],
                "image_path": row["image_path"],
            }
        if row["pii_type"]:
            report_entries[key]["detections"].append(
                {
                    "type": row["pii_type"],
                    "text_sample": row["text_sample"],
                    "confidence": row["confidence"],
                    "bbox_xyxy": json.loads(row["bbox_json"]),
                }
            )

    return jsonify(list(report_entries.values()))


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "empty filename"}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTS:
        return jsonify({"error": "unsupported file type"}), 400

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stored_name = f"{Path(file.filename).stem}_{timestamp}{suffix}"
    stored_path = UPLOAD_DIR / stored_name
    file.save(stored_path)

    entries = process_file(stored_path)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO documents (filename, stored_path, sha256, uploaded_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            file.filename,
            str(stored_path),
            entries[0]["file_hash"] if entries else "",
            datetime.utcnow().isoformat(),
        ),
    )
    document_id = cursor.lastrowid

    for entry in entries:
        cursor.execute(
            """
            INSERT INTO pages (document_id, page_num, language, image_path)
            VALUES (?, ?, ?, ?)
            """,
            (document_id, entry["page"], entry["language"], entry["image_path"]),
        )
        page_id = cursor.lastrowid
        for detection in entry["detections"]:
            cursor.execute(
                """
                INSERT INTO detections (page_id, pii_type, text_sample, confidence, bbox_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    detection["type"],
                    detection["text_sample"],
                    detection["confidence"],
                    json.dumps(detection["bbox_xyxy"]),
                ),
            )

    conn.commit()
    conn.close()

    return jsonify({"status": "processed", "pages": len(entries)})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000, debug=True)

# Invoice Redaction App

## Run the full stack (backend + frontend)

1. Install dependencies (example):

```bash
pip install flask paddleocr pdf2image opencv-python numpy Pillow langdetect
```

2. Start the backend server from the repo root:

```bash
python invoice_redaction/app.py
```

3. Open the app:

```
http://localhost:8000
```

## Upload documents

- Use the upload form to submit PDF or image invoices.
- The backend performs OCR + PII redaction, writes redacted images to `out/redacted_images`,
  and stores detections in a local SQLite database (`invoice_redaction/data/app.db`).

## Output locations

- Redacted images: `out/redacted_images`
- JSONL report: `out/pii_report.jsonl`
- SQLite DB: `invoice_redaction/data/app.db`

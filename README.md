# AI-Powered College Student Support and Intelligent Query Resolution Platform

Campus Guide is a local-first web application for answering student questions from college documents, keeping student documents private, tracking human support requests, and comparing policy versions.

## What is included

- Student registration, sign-in, and private profile fields for department, year, semester, courses, and preferences.
- Intent/domain classification and lightweight extraction of semesters, exam types, dates, course codes, departments, and document names.
- Admin-only uploads of official PDF, DOCX, TXT, and image documents, with title, version, department, semester, academic-year, and effective-date metadata.
- Best-effort metadata suggestions from document text and filenames; administrators can override inferred values during upload.
- Student uploads of private PDFs, DOCX, TXT, and images. A student's personal documents are retrieved only for that same account.
- Profile-aware retrieval ranking and a concise-answer preference when students save `concise` in their answer preferences.
- Page-aware PDF extraction, DOCX paragraph/table extraction, and image/scanned-PDF OCR through Tesseract.
- Document chunking and a local sparse TF-IDF-style term-vector index stored with SQLite. Retrieval is local and does not send documents to an AI provider.
- Evidence-first answers with document/page/section citations; low-evidence answers explicitly say they could not be verified and create a support ticket.
- Optional short "why" explanation, profile-context disclosure, and student feedback on answers.
- Admin dashboard metrics, FAQ signals, low-confidence questions, policy diffs, and ticket triage/response.
- Version comparison with metadata-based department/semester applicability hints.
- CSRF protection for form and JSON mutations; password hashing; role checks; HTTP-only, SameSite session cookies.

## Requirements

- Python 3.10 or newer.
- Tesseract OCR installed separately and available on `PATH` to OCR images or scanned PDFs. Searchable PDFs and text documents work without Tesseract.

## Setup on Windows

From PowerShell in the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Set a stable session key in `.env` before deployment. Generate a random value with:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output into `.env` as `SECRET_KEY=...`. Keep `.env` private and out of source control. Use `COOKIE_SECURE=1` when serving the app over HTTPS. For local HTTP development, leave it at `0`.

Create the first administrator interactively (the password is prompted without echo):

```powershell
.\.venv\Scripts\python.exe -m flask --app app create-admin
```

Run the development server:

```powershell
.\.venv\Scripts\python.exe -m flask --app app run
```

Open <http://127.0.0.1:5000>. Students can create their own accounts from the sign-in page. The public registration flow always creates a student, never an administrator.

## Using the platform

1. Sign in as an administrator and upload official rules, schedules, fee circulars, and other college documents. Add a stable title and version metadata; use the same title and department for successive versions.
2. Students complete their profile and ask questions in the assistant. When evidence is found, answers include citations; ask “why” for a short evidence/context explanation.
3. If the evidence match is too weak, the platform says it cannot verify the answer and opens a ticket routed by detected topic. Administrators can update status and write a response from the ticket queue.
4. Students can upload their own files and ask about them. Those files are isolated from other student accounts.
5. Select two versions of the same official document to review changed text and a profile-based applicability hint.

## OCR and indexing notes

Install the Tesseract OCR engine for your operating system and ensure `tesseract.exe` is on `PATH`. The Python `pytesseract` package is already in `requirements.txt`; it is only a wrapper and does not install the OCR engine.

The default retrieval index is a small, local, sparse term-frequency vector index in SQLite, not a hosted vector database or a neural semantic-embedding model. It is suitable for a prototype and avoids sending student or college data to a third party. Similarity is lexical, so test it against real campus documents and tune the evidence threshold before relying on it for operational decisions. No LLM provider is configured: the assistant returns relevant document excerpts rather than generating ungrounded policy claims.

OCR quality, PDF table layout, document metadata, and policy diffs should be reviewed by staff. The applicability check is a metadata-based hint, not an authoritative determination of an individual student's legal or academic eligibility.

## Data and deployment

SQLite data is created in `data/student_support.sqlite3`; uploaded source files are kept in `uploads/`. Both locations are ignored by Git and should be included in your secure backup plan. Do not expose the development server to the public internet. A real deployment should use HTTPS, a production WSGI server, managed secrets, backups, access monitoring, rate limiting, retention policies, and institution-approved identity and data-governance controls.

The admin dashboard currently displays recent low-confidence query text to authorized administrators so they can resolve knowledge gaps. Use the institution's privacy policy to determine appropriate access and retention for support records.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
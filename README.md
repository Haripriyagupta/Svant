# SVANT
<!--
> **Local-First Project & File Intelligence Desktop Application**  
> *Phase 1 — Foundation Build*

SVANT is a high-performance, privacy-respecting, local-first intelligence application designed to help developers comprehend, search, inspect, and maintain their local codebases and documents without cloud dependencies.

---

## 1. Overview & Purpose

Modern software projects and documentation are scattered across disks, nested directories, and distinct formats (code, documentation, configuration, notes). Developers spend substantial time finding where specific logic, configuration keys, or architectural guidelines reside.

SVANT solves this locally:
- Indexes local projects directly on your machine.
- Extracts text across code, documentation, and configuration files.
- Provides sub-millisecond keyword search via SQLite FTS5 (Full-Text Search 5) with BM25 relevance ranking.
- Keeps all source code and documents private on your machine—zero files are transmitted to the cloud.

---

## 2. Status: What is Implemented vs. Planned

###  IMPLEMENTED (Phase 1 — Foundation)
- **Local SQLite Database Layer**: Structured schema for projects, scanned files, text extractions, and FTS5 search index with WAL (Write-Ahead Logging) mode and cascading integrity.
- **Project Tracking**: Add local directories as tracked workspaces, monitor file counts, storage footprints, and scan statuses.
- **Recursive File Scanner**: Safe, fault-tolerant filesystem crawler that collects file metadata, computes hashes, and detects deleted/stale files.
- **Directory Exclusion Engine**: Automatic exclusion of dependency and generated folders (`.git`, `.venv`, `node_modules`, `dist`, `build`, `__pycache__`, etc.).
- **Multi-Format Text Extraction**:
  - Source Code: `.py`, `.js`, `.ts`, `.java`, `.cpp`, `.c`, `.cs`, `.html`, `.css`, etc.
  - Documents: `.txt`, `.md`, `.csv`, `.docx`, `.pdf`
  - Configurations: `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.env`
- **FTS5 Keyword Search Engine**: Fast local search across all or specific projects with highlight snippets and BM25 rank scoring.
- **FastAPI Backend**: Clean layered API (`/health`, `/api/projects`, `/api/files`, `/api/search`, `/api/stats`) with structured logging, secret redaction, and global error handling.
- **Modern Dark UI**: Zero-bloat, responsive desktop web interface with live stats, project manager, file inspector, search console, and roadmap placeholders.
- **Safe Untracking**: Removing projects from SVANT removes database metadata without modifying or deleting files on disk.

### ⏳ PLANNED (Future Phases)
- **Phase 2 (Local Intelligence)**: Text chunking, lightweight local CPU embeddings, FAISS vector indexing, Semantic Search, and Hybrid (BM25 + Semantic) search.
- **Phase 3 (RAG Pipeline)**: Local retrieval-augmented generation pipeline, context window builder, source citation tracking.
- **Phase 4 (Security Analysis)**: Static secret detection (API keys, tokens, private keys), leak prevention, local redaction before AI ingestion.
- **Phase 5 (Project Health)**: Duplicate file detection, orphaned/stale file detection, codebase size distribution, health hygiene scoring.
- **Phase 6 (Gemini Integration)**: Optional cloud AI integration using Google Gemini API for grounded code explanations, architectural Q&A, and documentation generation.
- **Phase 7 (Packaging & Polish)**: Desktop executable packaging (e.g. PyWebView / Tauri), onboarding tour, advanced indexing configuration.

---

## 3. Architecture

```
SVANT System Architecture
┌────────────────────────────────────────────────────────┐
│             Desktop Web Interface (UI)                 │
│       Dashboard · Projects · Files · Search Console    │
└───────────────────────────┬────────────────────────────┘
                            │ REST / JSON (HTTP loopback)
┌───────────────────────────▼────────────────────────────┐
│                  FastAPI Backend Server                │
│     Routes (/api/projects, /api/files, /api/search)    │
│        Structured Redacting Logging & Error Handlers   │
└─────────────┬───────────────────────────┬──────────────┘
              │                           │
┌─────────────▼─────────────┐   ┌─────────▼──────────────┐
│       Core Engines        │   │     Database Layer     │
│  - FileScanner            │   │  - SQLite (WAL Mode)   │
│  - FileClassifier         │   │  - Projects Table      │
│  - DocumentExtractor      │   │  - Files Table         │
│    (PDF, DOCX, CSV, Text) │   │  - Extractions Table   │
│  - SearchService          │   │  - SQLite FTS5 Index   │
└─────────────┬─────────────┘   └─────────▲──────────────┘
              │                           │
              └───────────────────────────┘
```

---

## 4. Storage & Database Location

To prevent filling limited system drives (C:), SVANT defaults to:
```
D:\SVANTData\
├── svant.db        # SQLite database & FTS5 full-text index
└── logs\
    └── svant.log   # Rotating structured log file (with secret redaction)
```
*(Configurable via the `SVANT_DATA_DIR` environment variable).*

---

## 5. Privacy & Security Model

1. **Local-Only Execution**: In Phase 1, SVANT does not connect to external servers or cloud AI providers.
2. **Zero Code Execution**: SVANT never executes scanned project code, scripts, or binaries.
3. **Non-Destructive**: Untracking a project only purges internal index entries; files on disk are never altered or deleted.
4. **Log Redaction**: Automatic regex masks prevent passwords, tokens, and API keys from appearing in application logs.
5. **Path Validation**: Canonical path validation prevents directory traversal attacks.

---

## 6. Setup & Installation

### Prerequisites
- Windows 10/11
- Python 3.11+ (Tested on Python 3.14.4)
- Existing virtual environment: `.venv`

### Installation
Activate the virtual environment and install dependencies:
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 7. Running SVANT

### Start the Application
```powershell
.\.venv\Scripts\python.exe -m svant.main
```
This boots the server on `http://127.0.0.1:8000` and opens the desktop UI in your default browser.

### Custom Host / Port / Headless Mode
```powershell
.\.venv\Scripts\python.exe -m svant.main --port 8080 --no-browser
```

### Run Automated Tests
```powershell
.\.venv\Scripts\pytest.exe -v
```

---

## 8. Current Limitations (Phase 1)
- **Keyword Search Only**: Search matches exact words and stemmed terms via SQLite FTS5. Natural-language semantic queries will be available in Phase 2.
- **In-Memory Concurrency**: Background tasks are coordinated synchronously or per-request; full job queues will expand as indexing grows.
- **Single-Host Loopback**: Designed for local desktop execution on `127.0.0.1`.

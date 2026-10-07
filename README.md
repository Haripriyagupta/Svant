# SVANT
<!--
> **Local-First Project & File Intelligence Desktop Application**  
> *Phase 2 — Local Intelligence Foundation*

SVANT is a high-performance, privacy-respecting, local-first intelligence application designed to help developers comprehend, search, inspect, and maintain their local codebases and documents without cloud dependencies or GPU hardware.

---

## 1. Overview & Purpose

Modern software projects and documentation are scattered across disks, nested directories, and distinct formats (code, documentation, configuration, notes). Developers spend substantial time finding where specific logic, configuration keys, or architectural guidelines reside.

SVANT delivers local intelligence directly on your machine:
- Indexes local projects directly on your machine without modifying original files.
- Extracts text across code, documentation, and configuration files.
- Provides sub-millisecond keyword search via SQLite FTS5 with BM25 relevance ranking.
- Generates CPU-friendly dense vector embeddings locally and indexes them with FAISS.
- Enables natural language **Semantic Search** and score-normalized **Hybrid Search** (FTS5 + FAISS).
- Operates 100% offline without Ollama, PyTorch, CUDA, or external cloud AI services.

---

## 2. Status: What is Implemented vs. Planned

### ✅ IMPLEMENTED (Phase 1 & Phase 2)

#### Phase 1: Foundation
- **Local SQLite Database Layer**: Structured schema for projects, scanned files, text extractions, and FTS5 search index with WAL (Write-Ahead Logging) mode and cascading integrity.
- **Project Tracking**: Add local directories as tracked workspaces, monitor file counts, storage footprints, and scan statuses.
- **Recursive File Scanner**: Safe, fault-tolerant filesystem crawler that collects file metadata, computes hashes, and detects deleted/stale files.
- **Directory Exclusion Engine**: Automatic exclusion of dependency and generated folders (`.git`, `.venv`, `node_modules`, `dist`, `build`, `__pycache__`, etc.).
- **Multi-Format Text Extraction**:
  - Source Code: `.py`, `.js`, `.ts`, `.java`, `.cpp`, `.c`, `.cs`, `.html`, `.css`, etc.
  - Documents: `.txt`, `.md`, `.csv`, `.docx`, `.pdf`
  - Configurations: `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.env`
- **FTS5 Keyword Search Engine**: Fast local keyword retrieval with highlight snippets and BM25 rank scoring.

#### Phase 2: Local Intelligence
- **Intelligent Text Chunking (`svant.core.chunker`)**:
  - Multi-strategy chunking aware of structural boundaries:
    - *Markdown*: Heading & section boundaries (`#`, `##`, `###`) preserving header context.
    - *Source Code*: Function, class, and definition block boundaries.
    - *Plain Text & Documents*: Paragraph (`\n\n`) and sentence boundaries with configurable overlap.
    - *CSV*: Header preservation across grouped rows.
    - *Configurations*: Section-aware chunking for INI, TOML, and structured configs.
  - Full chunk metadata retention (`chunk_id`, `project_id`, `file_id`, `relative_path`, `filename`, `chunk_index`, `char_count`, `word_count`, `metadata`).
- **CPU-Friendly Local Embeddings (`svant.core.embeddings`)**:
  - Lightweight ONNX-based embedding engine via `fastembed` (no PyTorch, no CUDA).
  - Selected Model: `BAAI/bge-small-en-v1.5` (quantized ONNX, 384 dimensions, ~64 MB disk footprint).
  - Unit normalization ($L_2$) ensuring inner product calculation equals cosine similarity.
  - Deterministic `MockEmbeddingProvider` for lightning-fast, offline test execution without model downloads.
- **FAISS Vector Store (`svant.core.vector_store`)**:
  - CPU-only `IndexIDMap2` wrapping `IndexFlatIP` for cosine similarity on unit-normalized vectors.
  - Authoritative metadata resides in SQLite; FAISS stores vectors and 64-bit integer IDs.
  - Persistent index files stored outside repository under `D:\SVANTData\indexes\<project-id>\chunks.index`.
- **Incremental Indexing Pipeline (`svant.core.indexing`)**:
  - Content hash (SHA-256) checking skips unchanged files (0 re-embeddings).
  - Changed files are automatically re-chunked, re-embedded, and old vectors purged.
  - Deleted files have associated chunks and FAISS vectors pruned.
  - Force-rebuild capability for complete index recreation.
- **Unified Multi-Mode Search Service (`svant.core.search`)**:
  - `keyword`: SQLite FTS5 BM25 search.
  - `semantic`: FAISS dense vector search mapping vector IDs back to SQLite chunks.
  - `hybrid`: Normalized linear score fusion combining BM25 relevance and semantic similarity with configurable weights ($w_{sem} = 0.6, w_{kw} = 0.4$).
- **API & UI Integration**:
  - Indexing endpoints: `POST /api/projects/{id}/index`, `GET /api/projects/{id}/index/status`, `POST /api/projects/{id}/index/rebuild`.
  - Multi-mode search endpoint: `GET /api/search?q=...&mode=keyword|semantic|hybrid`.
  - Interactive Search console with mode tabs (Keyword, Semantic, Hybrid).
  - Project cards featuring live Index Status badges (`Not Indexed`, `Indexing...`, `Indexed (N chunks, V vectors)`) and Scan, Index, and Re-index buttons.

---

### ⏳ PLANNED (Future Phases)
- **Phase 3 (RAG Pipeline)**: Local retrieval-augmented generation pipeline, context window assembler, prompt grounding, citation engine.
- **Phase 4 (Security Analysis)**: Static secret detection (API keys, tokens, private keys), leak prevention, local redaction before AI ingestion.
- **Phase 5 (Project Health)**: Duplicate file detection, orphaned/stale file detection, codebase size distribution, health hygiene scoring.
- **Phase 6 (Gemini Integration)**: Optional cloud AI integration using Google Gemini API for grounded code explanations, architectural Q&A, and documentation generation.
- **Phase 7 (Packaging & Polish)**: Desktop executable packaging (e.g. PyWebView / Tauri), onboarding tour, advanced indexing configuration.

---

## 3. Architecture

```
SVANT System Architecture (Phase 2)
┌────────────────────────────────────────────────────────┐
│             Desktop Web Interface (UI)                 │
│   Dashboard · Projects (Scan/Index) · Multi-Mode Search│
└───────────────────────────┬────────────────────────────┘
                            │ REST / JSON (HTTP loopback)
┌───────────────────────────▼────────────────────────────┐
│                  FastAPI Backend Server                │
│   Routes (/api/projects, /api/files, /api/search)      │
│   Indexing Routes (/api/projects/{id}/index)           │
└─────────────┬───────────────────────────┬──────────────┘
              │                           │
┌─────────────▼─────────────┐   ┌─────────▼──────────────┐
│       Core Service Layer  │   │     Storage Layer      │
│  - FileScanner            │   │  - SQLite (WAL Mode)   │
│  - DocumentExtractor      │   │    - projects          │
│  - TextChunker            │   │    - files             │
│  - EmbeddingProvider      │   │    - file_extractions  │
│  - FAISSVectorStore       │   │    - chunks (metadata) │
│  - IndexingPipeline       │   │    - project_indexes   │
│  - SearchService          │   │    - fts_files (FTS5)  │
│    (Keyword/Semantic/     │   │  - FAISS Vector Store  │
│     Hybrid)               │   │    (D:\SVANTData\      │
└───────────────────────────┘   │     indexes\<id>\)     │
                                └────────────────────────┘
```

---

## 4. Embedding Model Details

- **Model**: `BAAI/bge-small-en-v1.5` (via `fastembed`)
- **Engine**: ONNX Runtime on CPU (quantized INT8/FP32 weights)
- **Dimensions**: 384 dimensions
- **Model Size on Disk**: ~64 MB
- **Memory (RAM) Footprint**: ~100–150 MB during inference
- **Why this model?**
  1. Outstanding retrieval accuracy on the Massive Text Embedding Benchmark (MTEB).
  2. Runs natively on CPU via ONNX Runtime without requiring PyTorch, CUDA, or GPU hardware.
  3. 100% compatible with Python 3.14 on Windows.
  4. Instant startup (~1.5s) and low latency (~20ms per batch).
- **Storage Location**: Stored outside the Git repository at `D:\SVANTData\models`.
- **Offline Behavior**: Once downloaded on initial run, inference is strictly offline. Zero telemetry, zero external network requests.

---

## 5. Storage & Database Layout

All persistent application data is isolated on `D:\SVANTData` to protect limited C: drive capacity:

```
D:\SVANTData\
├── svant.db                    # SQLite metadata, extractions, chunks & FTS5
├── models\                     # ONNX embedding model weights (~64 MB)
│   └── models--Qdrant--bge-small-en-v1.5-onnx-Q\
├── indexes\                    # FAISS vector index files per project
│   └── <project-id>\
│       └── chunks.index        # Binary FAISS IndexIDMap2 index
└── logs\
    └── svant.log               # Rotating structured log file (with secret redaction)
```

---

## 6. How Search Works

### 1. Keyword Search (SQLite FTS5)
- Tokenizes query using the `porter unicode61` tokenizer.
- Executes BM25 ranking across file contents, filenames, and relative paths.
- Returns highlighted snippet and BM25 rank score (negative values; more negative = stronger match).

### 2. Semantic Search (FAISS Cosine Similarity)
- Computes dense vector embedding for query text via `LocalEmbeddingProvider`.
- Queries the project's FAISS index using inner product on unit-normalized vectors ($u \cdot v = \cos(u, v)$).
- Maps returned 64-bit vector IDs to SQLite `chunks` and joined `files` records.
- Capable of retrieving relevant code and passages even when query wording shares zero exact keywords (e.g. *"keep packages separate"* matches *"virtual environments isolate dependencies"*).

### 3. Hybrid Search (Score-Normalized Linear Fusion)
- Executes both FTS5 keyword retrieval and FAISS vector similarity search.
- Normalizes BM25 ranks to $[0.3, 1.0]$ and clamps cosine similarities to $[0.0, 1.0]$.
- Combines scores using configurable weights:
  $$\text{Score}_{\text{hybrid}} = w_{\text{sem}} \times \text{Score}_{\text{sem}} + w_{\text{kw}} \times \text{Score}_{\text{kw}}$$
  *(Defaults: $w_{\text{sem}} = 0.6, w_{\text{kw}} = 0.4$)*
- Documents appearing in both subsystems receive compounding score boosts.
- Deduplicates results at the file/chunk level and ranks descending by composite score.

---

## 7. Setup & Installation

### Prerequisites
- Windows 10/11
- Python 3.11+ (Validated on Python 3.14.4)
- Existing virtual environment: `D:\Projects\Svant\.venv`

### Installation
Activate virtual environment and install dependencies:
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

*Installed Phase 2 Dependencies:*
- `faiss-cpu>=1.15.0`
- `fastembed>=0.8.0`

---

## 8. Running SVANT

### Start the Application
```powershell
.\.venv\Scripts\python.exe -m svant.main
```
This boots the server on `http://127.0.0.1:8000` and opens the desktop UI in your default browser.

### Headless Mode / Custom Port
```powershell
.\.venv\Scripts\python.exe -m svant.main --port 8080 --no-browser
```

### Run Automated Tests
```powershell
.\.venv\Scripts\pytest.exe -v
```

---

## 9. Current Limitations (Phase 2)
- **Retrieval Only (No LLM Generative Chat)**: Generative response synthesis, grounded RAG Q&A, and citation generation are scheduled for Phase 3.
- **Single-Machine Desktop**: Optimized for local desktop workstation use on `127.0.0.1`.
- **CPU Inference**: Embedding throughput is tuned for CPU efficiency (~50–200 chunks/sec); very large multi-gigabyte codebases may take a few minutes on initial cold index.

# SVANT
just trying my things out. Will update it soon with proper description, setup guide, how it works and how to efficiently use it.


 Overview & Purpose

Modern software projects and documentation are scattered across disks, nested directories, and distinct formats (code, documentation, configuration, notes). Developers spend substantial time finding where specific logic, configuration keys, or architectural guidelines reside.

SVANT delivers local intelligence directly on your machine:
- Indexes local projects directly on your machine without modifying original files.
- Extracts text across code, documentation, and configuration files.
- Provides sub-millisecond keyword search via SQLite FTS5 with BM25 relevance ranking.
- Generates CPU-friendly dense vector embeddings locally and indexes them with FAISS.
- Enables natural language **Semantic Search** and score-normalized **Hybrid Search** (FTS5 + FAISS).
- Powers **Grounded AI Chat (RAG)** strictly backed by retrieved local project evidence with honest citations.
- Enforces **Local Secret Redaction** so API keys, passwords, private keys, and tokens are NEVER sent to cloud LLMs.
- Runs in **Local-Only Mode** 100% offline without Ollama, PyTorch, CUDA, or required cloud services.
<!--
> **Local-First Project & File Intelligence Desktop Application**  
> *Phase 3 — Grounded AI Chat & Privacy-Aware RAG Engine*
-->
<!--

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
- Powers **Grounded AI Chat (RAG)** strictly backed by retrieved local project evidence with honest citations.
- Enforces **Local Secret Redaction** so API keys, passwords, private keys, and tokens are NEVER sent to cloud LLMs.
- Runs in **Local-Only Mode** 100% offline without Ollama, PyTorch, CUDA, or required cloud services.

---

## 2. Status: What is Implemented vs. Planned

### ✅ IMPLEMENTED (Phase 1, Phase 2, & Phase 3)

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
- **Intelligent Text Chunking (`svant.core.chunker`)**: Structural boundary chunking across Markdown headings, code functions/classes, paragraph blocks, and config sections with source attribution.
- **CPU-Friendly Local Embeddings (`svant.core.embeddings`)**: ONNX Runtime engine (`fastembed` with `BAAI/bge-small-en-v1.5`, 384 dimensions, unit $L_2$ normalized, ~64 MB footprint).
- **FAISS Vector Store (`svant.core.vector_store`)**: CPU-only `IndexIDMap2(IndexFlatIP)` storing 64-bit IDs mapped back to SQLite chunk records.
- **Incremental Indexing Pipeline (`svant.core.indexing`)**: SHA-256 hash checking skipping unchanged files, auto-pruning stale vectors.
- **Unified Multi-Mode Search Service (`svant.core.search`)**: Keyword (FTS5 BM25), Semantic (FAISS), and Hybrid (Score-normalized linear fusion).

#### Phase 3: RAG & Grounded AI Chat
- **Local Secret & Privacy Redaction (`svant.core.privacy`)**:
  - Scans prompt and retrieved context for credentials *locally* before any generation pass.
  - High-confidence pattern masking for private keys (PEM), API keys, bearer tokens, database connection passwords, AWS keys, GitHub tokens, Slack tokens, OpenAI keys, and JWTs.
  - Replaces detected sensitive material with safe markers (e.g. `[REDACTED:PASSWORD]`, `[REDACTED:PRIVATE_KEY]`).
  - Zero raw secrets leave the local machine.
- **RAG Context Assembler (`svant.core.rag.context`)**:
  - Deduplicates retrieved chunks by chunk ID and file content.
  - Enforces character/token budget limits (default 30,000 characters).
  - Formats traceable structured evidence blocks for model ingestion.
- **Anti-Hallucination Grounded Prompt Builder (`svant.core.rag.prompt`)**:
  - Enforces strict grounding rules: answer *only* from supplied project evidence.
  - Clear instruction to state: *"I couldn't find enough relevant information in this project to answer that confidently"* when evidence is lacking.
- **Traceable Citation Generator (`svant.core.rag.citations`)**:
  - Honest source attribution with exact relative paths, line numbers or chunk identifiers, relevance scores, and preview snippets.
  - Clicking any citation in the UI opens the file detail modal directly.
- **AI Provider Abstraction (`svant.core.ai`)**:
  - Unified `AIProvider` base class.
  - `MockAIProvider`: Deterministic offline testing without network calls or API keys.
  - `GeminiProvider`: Direct, robust REST calls via `httpx` to Google Gemini API (`gemini-2.5-flash`). Zero heavy external dependencies.
  - `Local-Only Mode`: When enabled or when no cloud provider is configured, returns verified local context excerpts and citations with zero network transmission.
- **End-to-End RAG Chat UI**:
  - Interactive chat interface with real-time stream, typing indicators, project selector, retrieval mode selector, and top-K selector.
  - Source grounding citation cards with file inspection modal integration.
  - Privacy badges displaying local redactor status and count of masked secrets.

---

### ⏳ PLANNED (Future Phases)
- **Phase 4 (Security Analysis)**: Static secret scanning dashboard, leak exposure history, credential risk scoring.
- **Phase 5 (Project Health)**: Duplicate file detection, orphaned/stale file detection, codebase size distribution, health hygiene scoring.
- **Phase 6 (Advanced Code Insights)**: Architectural dependency graphs, dead code detection, automated refactoring suggestions.
- **Phase 7 (Packaging & Polish)**: Desktop executable packaging, system tray integration, advanced local storage configuration.

---

## 3. Architecture

```
SVANT System Architecture (Phase 3)
┌────────────────────────────────────────────────────────────────────────┐
│                      Desktop Web Interface (UI)                        │
│   Dashboard · Projects · Multi-Mode Search · Grounded AI Chat (RAG)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ REST / JSON (HTTP loopback)
┌───────────────────────────────────▼────────────────────────────────────┐
│                         FastAPI Backend Server                         │
│   Routes (/api/projects, /api/files, /api/search, /api/chat)           │
└─────────────┬───────────────────────────┬──────────────────────────────┘
              │                           │
┌─────────────▼─────────────┐   ┌─────────▼──────────────┐
│       Core Service Layer  │   │     Storage Layer      │
│  - FileScanner            │   │  - SQLite (WAL Mode)   │
│  - DocumentExtractor      │   │    - projects          │
│  - TextChunker            │   │    - files             │
│  - EmbeddingProvider      │   │    - file_extractions  │
│  - FAISSVectorStore       │   │    - chunks (metadata) │
│  - IndexingPipeline       │   │    - project_indexes   │
│  - SearchService (Hybrid) │   │    - fts_files (FTS5)  │
│                           │   │  - FAISS Vector Store  │
│  Phase 3 RAG Layer:       │   │    (D:\SVANTData\      │
│  - SecretRedactor (Local) │   │     indexes\<id>\)     │
│  - ContextAssembler       │   └────────────────────────┘
│  - GroundedPromptBuilder  │
│  - CitationGenerator      │   ┌────────────────────────┐
│  - RAGPipeline            │   │   AI Provider Layer    │
│                           ├───►  - GeminiProvider      │
│                           │   │  - MockAIProvider      │
│                           │   │  - Local-Only Mode     │
└───────────────────────────┘   └────────────────────────┘
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

## 6. How Search and RAG Work

### 1. Keyword Search (SQLite FTS5)
- Tokenizes query using the `porter unicode61` tokenizer.
- Executes BM25 ranking across file contents, filenames, and relative paths.
- Returns highlighted snippet and BM25 rank score.

### 2. Semantic Search (FAISS Cosine Similarity)
- Computes dense vector embedding for query text via `LocalEmbeddingProvider`.
- Queries the project's FAISS index using inner product on unit-normalized vectors ($u \cdot v = \cos(u, v)$).
- Maps returned 64-bit vector IDs to SQLite `chunks` and joined `files` records.

### 3. Hybrid Search (Score-Normalized Linear Fusion)
- Executes both FTS5 keyword retrieval and FAISS vector similarity search.
- Normalizes BM25 ranks to $[0.3, 1.0]$ and clamps cosine similarities to $[0.0, 1.0]$.
- Combines scores using configurable weights:
  $$\text{Score}_{\text{hybrid}} = w_{\text{sem}} \times \text{Score}_{\text{sem}} + w_{\text{kw}} \times \text{Score}_{\text{kw}}$$
  *(Defaults: $w_{\text{sem}} = 0.6, w_{\text{kw}} = 0.4$)*

### 4. Grounded RAG Chat Pipeline
- **Step 1 — Query Sanitization**: Inspects the developer question locally; redacts any typed credentials.
- **Step 2 — Multi-Mode Retrieval**: Queries SQLite FTS5, FAISS, or Hybrid fusion for candidate chunks.
- **Step 3 — Context Assembly**: Deduplicates chunks, sorts by relevance, and enforces max context limits.
- **Step 4 — Privacy Masking**: Scans all retrieved chunks with high-confidence regex patterns. Masks passwords, keys, and tokens locally.
- **Step 5 — Citation Generation**: Maps evidence to exact files, line numbers, and relevance scores.
- **Step 6 — Grounded Generation**: If Gemini is enabled, sends sanitized prompts to Google Gemini REST API. If Local-Only, presents structured evidence excerpts directly without external network traffic.

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

## 9. Current Limitations & Future Roadmap
- **Phase 3 Complete**: RAG and Grounded AI Chat with local secret redaction are fully functional and tested.
- **Single-Machine Desktop**: Optimized for local workstation use on `127.0.0.1`.
- **CPU Inference**: Embedding throughput is tuned for CPU efficiency (~50–200 chunks/sec); very large multi-gigabyte codebases may take a few minutes on initial cold index.

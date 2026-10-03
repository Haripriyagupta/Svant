# Svant
SVANT is an open-source, privacy-first digital assistant that helps you understand, organize, search, and protect the information on your computer. It can find files, detect sensitive data, extract important information, and answer questions about your documents—all locally, keeping your data under your control.
---------------------------------------------------------------------------------------------------------------------------------------------------------
SVANT 🖥️🤖

SVANT — Make your digital life make sense.

SVANT is an open-source, privacy-first desktop assistant that helps you understand, search, organize, and protect the information stored on your computer.

It works mainly locally on your device, giving you more control over your personal files and data.

✨ What Can SVANT Do?

- 🔎 Smart File Search — Find files using names, content, or meaning.
- 💬 Ask SVANT — Ask questions about your documents and get answers with file sources.
- 🔐 Privacy Scanner — Detect sensitive information such as API keys, passwords, emails, and tokens.
- 📄 File Intelligence — Extract useful information, dates, deadlines, and metadata from documents.
- 🗂️ Organization Suggestions — Suggest better ways to organize files without changing anything automatically.
- 🧹 File Cleanup — Find duplicate, large, or old files.
- 🤖 Local AI — Use AI on your own computer through local models.

⚙️ How Does It Work?

Your Files
    ↓
SVANT scans & extracts information
    ↓
SQLite stores file information
    ↓
FAISS helps find relevant content
    ↓
Ollama processes AI questions
    ↓
SVANT gives you an answer + sources

SVANT treats documents as data, not instructions, helping protect against malicious instructions hidden inside files.

🛠️ Tech Stack

Part| Technology
Desktop App| Tauri
Frontend| HTML, CSS, JavaScript
Core & AI| Python
Database| SQLite
Semantic Search| FAISS
Local AI| Ollama
Version Control| Git + GitHub

🚀 Development Status

SVANT is currently under development.

Planned development

- [ ] File indexing
- [ ] Smart search
- [ ] Document Q&A
- [ ] Privacy scanner
- [ ] Duplicate detection
- [ ] Important information extraction
- [ ] Organization suggestions
- [ ] Desktop UI
- [ ] Plugin system

🤝 Contributing

Contributions are welcome!

You can contribute by:

1. Forking the repository.
2. Creating a new branch.
3. Working on a feature or bug.
4. Adding tests where needed.
5. Creating a Pull Request.

Beginner-friendly contributions such as documentation, UI improvements, testing, and bug fixes are also welcome.

🔒 Privacy

SVANT follows a local-first approach.

- Your files should remain under your control.
- No unnecessary cloud uploads.
- No automatic destructive actions.
- AI features can use local models.
- Cloud AI integrations, if added later, will be optional.

🎯 Vision

SVANT aims to become an open-source personal intelligence layer for your computer — helping you search, understand, organize, and protect your digital workspace while keeping privacy at the center.

Private. Local. Intelligent.

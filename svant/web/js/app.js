/**
 * SVANT Desktop Web Application Logic
 * Coordinates UI state, views, actions, and real-time backend updates.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Application State
  const state = {
    currentPage: 'dashboard',
    projects: [],
    stats: null,
    files: [],
    selectedProjectForFiles: '',
    selectedCategoryForFiles: '',
    searchMode: 'keyword',
    projectStatuses: {},
  };

  // DOM Elements
  const navItems = document.querySelectorAll('.nav-item');
  const pageViews = document.querySelectorAll('.page-view');
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');
  const toastContainer = document.getElementById('toast-container');

  // Modals
  const modalAddProject = document.getElementById('modal-add-project');
  const modalFileDetail = document.getElementById('modal-file-detail');

  // Formatters
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function formatDate(isoStr) {
    if (!isoStr) return 'Never';
    try {
      const d = new Date(isoStr);
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (_) {
      return isoStr;
    }
  }

  // Toast Notification
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      setTimeout(() => toast.remove(), 200);
    }, 3500);
  }

  // Navigation Logic
  const pageTitles = {
    dashboard: { title: 'System Dashboard', subtitle: 'Real-time local file intelligence & tracked repositories' },
    projects: { title: 'Tracked Projects', subtitle: 'Manage local folders, trigger scans, and inspect disk status' },
    files: { title: 'Indexed Files', subtitle: 'Explore scanned project files, metadata, and extracted text' },
    search: { title: 'Knowledge Search', subtitle: 'High-speed local keyword search via SQLite FTS5 engine' },
    security: { title: 'Security & Secret Shield', subtitle: 'Static credential scanning, dangerous config detection, and zero-exposure masking' },
    duplicates: { title: 'Duplicate File Analysis', subtitle: 'SHA-256 hash-based identical file discovery and storage reclamation' },
    health: { title: 'Project Health & Architecture', subtitle: 'Explainable SVANT Health Score (0-100), component weights, and prioritized fixes' },
    aichat: { title: 'Grounded AI Assistant', subtitle: 'Privacy-aware project Q&A with strict context grounding & citations' },
    settings: { title: 'Preferences', subtitle: 'Configuration and storage path settings (Roadmap Phase 7)' },
  };

  function switchPage(pageId) {
    state.currentPage = pageId;

    navItems.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.page === pageId);
    });

    pageViews.forEach((view) => {
      view.classList.toggle('active', view.id === `page-${pageId}`);
    });

    const info = pageTitles[pageId] || { title: 'SVANT', subtitle: '' };
    pageTitle.textContent = info.title;
    pageSubtitle.textContent = info.subtitle;

    // Trigger page-specific data refresh
    if (pageId === 'dashboard') loadDashboardData();
    if (pageId === 'projects') loadProjectsView();
    if (pageId === 'files') loadFilesView();
    if (pageId === 'security') loadSecurityView();
    if (pageId === 'duplicates') loadDuplicatesView();
    if (pageId === 'health') loadHealthView();
    if (pageId === 'aichat') {
      updateAIStatusBadge();
      if (!state.projects.length) loadDashboardData();
    }
  }

  navItems.forEach((btn) => {
    btn.addEventListener('click', () => {
      const pageId = btn.dataset.page;
      switchPage(pageId);
    });
  });

  // Backend Health Polling
  async function checkHealth() {
    try {
      const data = await API.getHealth();
      const dot = document.getElementById('status-dot');
      const label = document.getElementById('status-label');
      const dataDirTag = document.getElementById('data-dir-preview');

      if (data.status === 'ok') {
        dot.className = 'status-indicator live';
        label.textContent = `Backend Live (v${data.version})`;
        dataDirTag.textContent = data.data_dir;
      }
    } catch (_) {
      const dot = document.getElementById('status-dot');
      const label = document.getElementById('status-label');
      dot.className = 'status-indicator error';
      label.textContent = 'Backend Offline';
    }
  }

  // Load Dashboard Data
  async function loadDashboardData() {
    try {
      const [stats, projects] = await Promise.all([API.getStats(), API.getProjects()]);
      state.stats = stats;
      state.projects = projects;

      // Update counters
      document.getElementById('stat-projects').textContent = stats.total_projects;
      document.getElementById('stat-files').textContent = stats.total_files.toLocaleString();
      document.getElementById('stat-files-size').textContent = `${formatBytes(stats.total_size_bytes)} Total Storage`;
      document.getElementById('stat-indexed').textContent = `${stats.total_indexed_files.toLocaleString()} (${stats.total_chunks || 0} chunks)`;
      document.getElementById('stat-last-scan').textContent = stats.last_scanned_at
        ? `Last scan: ${formatDate(stats.last_scanned_at)}`
        : 'No scans completed';

      // Update badges
      document.getElementById('nav-project-count').textContent = stats.total_projects;
      document.getElementById('nav-file-count').textContent = stats.total_files;

      // Render mini project list
      const miniList = document.getElementById('dashboard-projects-list');
      if (projects.length === 0) {
        miniList.innerHTML = `<div class="empty-state">No projects tracked yet. Click "Track New Project" above.</div>`;
      } else {
        miniList.innerHTML = projects
          .slice(0, 5)
          .map(
            (p) => `
          <div class="mini-project-item">
            <div class="mini-proj-info">
              <h4>${escapeHtml(p.name)}</h4>
              <p>${escapeHtml(p.root_path)}</p>
            </div>
            <div class="mini-proj-meta">
              <span class="badge">${p.file_count} files</span>
              <button class="btn btn-secondary btn-sm" onclick="window.triggerScan('${p.id}')">Scan</button>
            </div>
          </div>
        `
          )
          .join('');
      }

      // Render Category distribution
      const catBox = document.getElementById('category-distribution');
      const categories = stats.categories || {};
      const entries = Object.entries(categories);

      if (entries.length === 0) {
        catBox.innerHTML = `<div class="empty-state">Scan a project to analyze file distribution.</div>`;
      } else {
        const total = stats.total_files || 1;
        catBox.innerHTML = entries
          .map(([cat, data]) => {
            const pct = Math.round((data.count / total) * 100);
            return `
            <div class="category-row">
              <div class="category-meta">
                <span class="category-name">${cat} (${data.count})</span>
                <span class="category-stats">${formatBytes(data.size)} · ${pct}%</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: ${pct}%"></div>
              </div>
            </div>
          `;
          })
          .join('');
      }
    } catch (err) {
      showToast(`Failed to load dashboard: ${err.message}`, 'error');
    }
  }

  // Projects View
  async function loadProjectsView() {
    try {
      const projects = await API.getProjects();
      state.projects = projects;

      // Fetch index status for all projects
      const statuses = await Promise.all(
        projects.map((p) =>
          API.getIndexStatus(p.id).catch(() => ({ status: 'not_indexed', total_chunks: 0, total_vectors: 0 }))
        )
      );
      state.projectStatuses = {};
      projects.forEach((p, idx) => {
        state.projectStatuses[p.id] = statuses[idx];
      });

      renderProjectsGrid(projects);
      updateProjectFilterDropdowns(projects);
    } catch (err) {
      showToast(`Error fetching projects: ${err.message}`, 'error');
    }
  }

  function renderProjectsGrid(projects) {
    const grid = document.getElementById('projects-grid');
    if (projects.length === 0) {
      grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;">No projects tracked yet. Click "Track New Project" to get started.</div>`;
      return;
    }

    grid.innerHTML = projects
      .map((p) => {
        const idxInfo = state.projectStatuses[p.id] || { status: 'not_indexed', total_chunks: 0, total_vectors: 0 };
        const idxLabel = idxInfo.status === 'indexed'
          ? `Indexed (${idxInfo.total_chunks} chunks)`
          : idxInfo.status === 'indexing'
          ? 'Indexing...'
          : 'Not Indexed';
        const idxClass = idxInfo.status === 'indexed' ? 'document' : idxInfo.status === 'indexing' ? 'source' : 'binary';

        const isIndexing = idxInfo.status === 'indexing';

        return `
      <div class="project-card">
        <div class="project-card-header">
          <div>
            <div class="project-title">${escapeHtml(p.name)}</div>
            <div class="project-path" title="${escapeHtml(p.root_path)}">${escapeHtml(p.root_path)}</div>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <span class="tag-cat ${p.status === 'ready' ? 'document' : 'binary'}">${p.status}</span>
            <span class="tag-cat ${idxClass}" title="Semantic Vector Index Status">${idxLabel}</span>
          </div>
        </div>

        <div class="project-stats-row">
          <div class="proj-stat-item">
            <span class="proj-stat-label">Files</span>
            <span class="proj-stat-val">${p.file_count.toLocaleString()}</span>
          </div>
          <div class="proj-stat-item">
            <span class="proj-stat-label">Size</span>
            <span class="proj-stat-val">${formatBytes(p.total_size_bytes)}</span>
          </div>
          <div class="proj-stat-item">
            <span class="proj-stat-label">Vectors</span>
            <span class="proj-stat-val">${(idxInfo.total_vectors || 0).toLocaleString()}</span>
          </div>
          <div class="proj-stat-item">
            <span class="proj-stat-label">Last Scan</span>
            <span class="proj-stat-val" style="font-size: 11.5px;">${formatDate(p.last_scanned_at)}</span>
          </div>
        </div>

        <div class="project-actions">
          <button class="btn btn-secondary btn-sm" onclick="window.viewProjectFiles('${p.id}')">Files</button>
          <button class="btn btn-secondary btn-sm" onclick="window.triggerScan('${p.id}')" title="Scan disk and extract text">Scan</button>
          <button class="btn btn-primary btn-sm" onclick="window.triggerIndex('${p.id}')" ${isIndexing ? 'disabled' : ''} title="Chunk and embed text for semantic search">${isIndexing ? 'Indexing...' : 'Index'}</button>
          <button class="btn btn-ghost btn-sm" onclick="window.triggerReindex('${p.id}')" ${isIndexing ? 'disabled' : ''} title="Force rebuild FAISS vector index">Re-index</button>
          <button class="btn btn-danger btn-sm" onclick="window.confirmUntrack('${p.id}', '${escapeJs(p.name)}')">Untrack</button>
        </div>
      </div>
    `;
      })
      .join('');
  }

  function updateProjectFilterDropdowns(projects) {
    const fileSelect = document.getElementById('file-filter-project');
    const searchSelect = document.getElementById('search-project-select');
    const chatSelect = document.getElementById('chat-project-select');

    const options = [
      '<option value="">All Projects</option>',
      ...projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`),
    ].join('');

    if (fileSelect) fileSelect.innerHTML = options;
    if (searchSelect) searchSelect.innerHTML = ['<option value="">Across All Tracked Projects</option>', ...projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)].join('');
    if (chatSelect) chatSelect.innerHTML = ['<option value="">All Indexed Projects</option>', ...projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)].join('');
  }

  // Scan Action
  window.triggerScan = async function (projectId) {
    showToast('Starting file scan & text extraction...', 'info');
    try {
      const res = await API.scanProject(projectId);
      showToast(`Scan complete: ${res.total_scanned} files (${res.indexed_count} indexed) in ${res.duration_seconds}s`, 'success');
      loadDashboardData();
      if (state.currentPage === 'projects') loadProjectsView();
      if (state.currentPage === 'files') loadFilesView();
    } catch (err) {
      showToast(`Scan failed: ${err.message}`, 'error');
    }
  };

  // Index Action (Phase 2 Local Intelligence)
  window.triggerIndex = async function (projectId) {
    if (state.projectStatuses[projectId]?.status === 'indexing') {
      showToast('Indexing is already in progress for this project.', 'warning');
      return;
    }
    state.projectStatuses[projectId] = {
      ...(state.projectStatuses[projectId] || {}),
      status: 'indexing',
    };
    if (state.currentPage === 'projects') renderProjectsGrid(state.projects);

    showToast('Starting semantic indexing (chunking & embeddings)...', 'info');
    try {
      const res = await API.indexProject(projectId);
      showToast(
        `Indexing complete: ${res.indexed_files} indexed (${res.total_chunks} chunks, ${res.total_vectors} vectors) in ${res.duration_seconds}s`,
        'success'
      );
    } catch (err) {
      showToast(`Indexing failed: ${err.message}`, 'error');
    } finally {
      loadDashboardData();
      if (state.currentPage === 'projects') loadProjectsView();
    }
  };

  // Re-index Action (Force rebuild)
  window.triggerReindex = async function (projectId) {
    if (state.projectStatuses[projectId]?.status === 'indexing') {
      showToast('Indexing is already in progress for this project.', 'warning');
      return;
    }
    if (!confirm('Rebuilding the index will wipe current vectors and re-chunk/re-embed all files from scratch. Proceed?')) return;
    state.projectStatuses[projectId] = {
      ...(state.projectStatuses[projectId] || {}),
      status: 'indexing',
    };
    if (state.currentPage === 'projects') renderProjectsGrid(state.projects);

    showToast('Force rebuilding vector index...', 'info');
    try {
      const res = await API.rebuildIndex(projectId);
      showToast(
        `Index rebuilt: ${res.total_chunks} chunks and ${res.total_vectors} vectors in ${res.duration_seconds}s`,
        'success'
      );
    } catch (err) {
      showToast(`Rebuild failed: ${err.message}`, 'error');
    } finally {
      loadDashboardData();
      if (state.currentPage === 'projects') loadProjectsView();
    }
  };

  // Untrack Project
  window.confirmUntrack = async function (projectId, name) {
    const ok = confirm(`Remove "${name}" from SVANT tracking?\n\nNote: Original files on your disk will NOT be touched or deleted.`);
    if (!ok) return;

    try {
      await API.deleteProject(projectId);
      showToast(`Untracked project "${name}". Files on disk are untouched.`, 'info');
      loadProjectsView();
      loadDashboardData();
    } catch (err) {
      showToast(`Failed to untrack: ${err.message}`, 'error');
    }
  };

  // Explore Files for Project
  window.viewProjectFiles = function (projectId) {
    state.selectedProjectForFiles = projectId;
    switchPage('files');
    const select = document.getElementById('file-filter-project');
    if (select) select.value = projectId;
    loadFilesView();
  };

  // Files View
  async function loadFilesView() {
    const projectFilter = document.getElementById('file-filter-project')?.value || '';
    const categoryFilter = document.getElementById('file-filter-category')?.value || '';
    const searchFilter = document.getElementById('file-search-input')?.value || '';

    try {
      const files = await API.getFiles({
        projectId: projectFilter || undefined,
        category: categoryFilter || undefined,
        search: searchFilter || undefined,
      });
      state.files = files;
      renderFilesTable(files);
    } catch (err) {
      showToast(`Failed to fetch files: ${err.message}`, 'error');
    }
  }

  function renderFilesTable(files) {
    const tbody = document.getElementById('files-table-body');
    if (files.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center empty-cell" style="padding: 24px; text-align: center; color: var(--text-dim);">No files matched the current filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = files
      .map(
        (f) => `
      <tr>
        <td style="font-weight: 600;">${escapeHtml(f.filename)}</td>
        <td style="color: var(--text-muted);">${escapeHtml(f.project_name || 'Project')}</td>
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-dim);">${escapeHtml(f.relative_path)}</td>
        <td><span class="tag-cat ${f.category}">${f.category}</span></td>
        <td style="font-family: var(--font-mono); font-size: 11px;">${formatBytes(f.size_bytes)}</td>
        <td style="font-size: 11.5px; color: var(--text-dim);">${formatDate(f.modified_time)}</td>
        <td><span class="tag-cat ${f.indexed_status === 'indexed' ? 'document' : 'other'}">${f.indexed_status}</span></td>
        <td><button class="btn btn-ghost btn-sm" onclick="window.viewFileDetail('${f.id}')">Inspect</button></td>
      </tr>
    `
      )
      .join('');
  }

  // File Detail Modal
  window.viewFileDetail = async function (fileId) {
    try {
      const detail = await API.getFileDetail(fileId);
      document.getElementById('modal-file-title').textContent = detail.filename;
      document.getElementById('meta-file-path').textContent = detail.path;
      document.getElementById('meta-file-size').textContent = `${formatBytes(detail.size_bytes)} (${detail.size_bytes} bytes)`;
      document.getElementById('meta-file-cat').textContent = `${detail.category} (${detail.extension})`;
      document.getElementById('meta-file-mtime').textContent = formatDate(detail.modified_time);
      document.getElementById('meta-file-extstatus').textContent = detail.extraction_status || 'not extracted';
      document.getElementById('meta-file-sha').textContent = detail.sha256 ? detail.sha256.substring(0, 16) + '...' : 'N/A';
      document.getElementById('preview-char-count').textContent = `${(detail.char_count || 0).toLocaleString()} characters`;
      document.getElementById('modal-file-content').textContent = detail.content_preview || '(No text extracted or file is binary)';
      modalFileDetail.classList.add('active');
    } catch (err) {
      showToast(`Could not load file details: ${err.message}`, 'error');
    }
  };

  // Search View & Mode Switching
  state.searchMode = 'keyword';
  const modeTabs = document.querySelectorAll('.mode-tab');
  modeTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      modeTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      state.searchMode = tab.dataset.mode || 'keyword';

      const qInput = document.getElementById('search-query-input');
      if (state.searchMode === 'semantic') {
        qInput.placeholder = 'Natural language semantic search (FAISS dense vector embeddings)...';
      } else if (state.searchMode === 'hybrid') {
        qInput.placeholder = 'Hybrid search combining full-text keywords and semantic vector relevance...';
      } else {
        qInput.placeholder = 'Search exact keywords (SQLite FTS5 full-text engine)...';
      }

      if (qInput.value.trim()) {
        runSearch();
      }
    });
  });

  async function runSearch() {
    const queryInput = document.getElementById('search-query-input');
    const projectSelect = document.getElementById('search-project-select');
    const container = document.getElementById('search-results-container');

    const query = queryInput.value.trim();
    if (!query) {
      showToast('Please enter search terms', 'info');
      return;
    }

    const currentMode = state.searchMode || 'keyword';
    const modeLabels = {
      keyword: 'SQLite FTS5 BM25',
      semantic: 'FAISS Dense Vectors',
      hybrid: 'FTS5 + FAISS Hybrid Fusion',
    };

    container.innerHTML = `<div class="search-initial-state"><div class="hint-icon">⚡</div><h3>Searching ${modeLabels[currentMode]}...</h3></div>`;

    try {
      const res = await API.search({
        query: query,
        projectId: projectSelect.value || undefined,
        mode: currentMode,
      });

      if (res.results.length === 0) {
        container.innerHTML = `
          <div class="search-initial-state">
            <div class="hint-icon">∅</div>
            <h3>No matches found</h3>
            <p>No indexed files matched query: "<strong>${escapeHtml(query)}</strong>" in ${currentMode.toUpperCase()} mode.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div style="font-family: var(--font-mono); font-size: 12px; color: var(--text-dim); margin-bottom: 8px;">
          Found ${res.total} matches across indexed files (${res.mode.toUpperCase()} · ${modeLabels[currentMode] || currentMode})
        </div>
        ${res.results
          .map((hit) => {
            const modeBadgeClass = hit.match_mode && hit.match_mode.includes('semantic')
              ? 'source'
              : (hit.match_mode && hit.match_mode.includes('hybrid') ? 'data' : 'document');
            const scoreLabel = hit.score !== undefined ? ` · Score ${hit.score}` : '';

            return `
          <div class="search-hit-card" onclick="window.viewFileDetail('${hit.file_id}')">
            <div class="search-hit-header">
              <span class="search-hit-title">${escapeHtml(hit.filename)}</span>
              <div style="display: flex; gap: 8px; align-items: center;">
                <span class="tag-cat ${modeBadgeClass}">${escapeHtml((hit.match_mode || currentMode).toUpperCase())}${scoreLabel}</span>
                <span class="search-hit-proj">${escapeHtml(hit.project_name)}</span>
              </div>
            </div>
            <div class="search-hit-path">${escapeHtml(hit.relative_path)}</div>
            <div class="search-snippet">${hit.snippet}</div>
          </div>
        `;
          })
          .join('')}
      `;
    } catch (err) {
      showToast(`Search error: ${err.message}`, 'error');
      container.innerHTML = `<div class="search-initial-state"><div class="hint-icon">⚠️</div><h3>Search Error</h3><p>${escapeHtml(err.message)}</p></div>`;
    }
  }

  // Event Listeners
  document.getElementById('btn-open-add-project').addEventListener('click', () => {
    modalAddProject.classList.add('active');
    document.getElementById('input-project-path').focus();
  });

  document.getElementById('btn-close-add-modal').addEventListener('click', () => {
    modalAddProject.classList.remove('active');
  });

  document.getElementById('btn-cancel-add-project').addEventListener('click', () => {
    modalAddProject.classList.remove('active');
  });

  document.getElementById('btn-close-detail-modal').addEventListener('click', () => {
    modalFileDetail.classList.remove('active');
  });

  document.getElementById('btn-close-detail').addEventListener('click', () => {
    modalFileDetail.classList.remove('active');
  });

  document.getElementById('btn-submit-add-project').addEventListener('click', async () => {
    const pathInput = document.getElementById('input-project-path');
    const nameInput = document.getElementById('input-project-name');
    const pathVal = pathInput.value.trim();
    const nameVal = nameInput.value.trim();

    if (!pathVal) {
      showToast('Project directory path is required.', 'error');
      return;
    }

    try {
      const newProj = await API.createProject(pathVal, nameVal);
      showToast(`Tracked project "${newProj.name}" successfully!`, 'success');
      modalAddProject.classList.remove('active');
      pathInput.value = '';
      nameInput.value = '';
      loadProjectsView();
      loadDashboardData();

      // Trigger prompt to scan immediately
      if (confirm(`Project "${newProj.name}" is now tracked. Would you like to scan it now?`)) {
        window.triggerScan(newProj.id);
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  });

  document.getElementById('btn-refresh-projects').addEventListener('click', () => {
    loadDashboardData();
  });

  document.getElementById('btn-filter-files').addEventListener('click', () => {
    loadFilesView();
  });

  document.getElementById('btn-run-search').addEventListener('click', runSearch);

  document.getElementById('search-query-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runSearch();
  });

  // Filter input on projects page
  document.getElementById('project-filter-input').addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    const filtered = state.projects.filter(
      (p) => p.name.toLowerCase().includes(term) || p.root_path.toLowerCase().includes(term)
    );
    renderProjectsGrid(filtered);
  });

  // Helpers
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function escapeJs(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
  }

  // ==========================================================================
  // Grounded AI Chat Logic (Phase 3)
  // ==========================================================================

  async function updateAIStatusBadge() {
    const badge = document.getElementById('chat-provider-badge');
    if (!badge) return;
    try {
      const status = await API.getAIStatus();
      if (status.active_provider === 'gemini') {
        badge.textContent = `Gemini (${status.model})`;
        badge.className = 'badge-provider live';
      } else if (status.active_provider === 'mock') {
        badge.textContent = 'Mock AI (Local Test)';
        badge.className = 'badge-provider test';
      } else if (status.local_only_mode) {
        badge.textContent = 'Local-Only Mode';
        badge.className = 'badge-provider local';
      } else {
        badge.textContent = `${(status.active_provider || 'AI').toUpperCase()} (${status.is_available ? 'Ready' : 'Offline'})`;
        badge.className = 'badge-provider';
      }
    } catch (_) {
      badge.textContent = 'AI Status Unknown';
      badge.className = 'badge-provider';
    }
  }

  function formatAIAnswer(rawText) {
    if (!rawText) return '';
    let formatted = escapeHtml(rawText);
    // Code blocks: ```code```
    formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    // Inline code: `code`
    formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold: **text**
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    return formatted;
  }

  async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('btn-chat-send');
    const stream = document.getElementById('chat-stream');
    const projSelect = document.getElementById('chat-project-select');
    const modeSelect = document.getElementById('chat-mode-select');
    const topkSelect = document.getElementById('chat-topk-select');

    const text = input.value.trim();
    if (!text) return;

    // Remove welcome card if still visible
    const welcomeCard = document.getElementById('chat-welcome');
    if (welcomeCard) welcomeCard.remove();

    // Disable controls while awaiting RAG generation
    input.disabled = true;
    sendBtn.disabled = true;

    // Append User Bubble
    const userRow = document.createElement('div');
    userRow.className = 'chat-message-row user';
    userRow.innerHTML = `
      <div class="chat-bubble">
        <div>${escapeHtml(text)}</div>
      </div>
    `;
    stream.appendChild(userRow);
    stream.scrollTop = stream.scrollHeight;

    // Append Typing Indicator
    const typingRow = document.createElement('div');
    typingRow.className = 'chat-message-row assistant';
    typingRow.id = 'chat-typing-row';
    typingRow.innerHTML = `
      <div class="chat-bubble">
        <div class="typing-dots">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    `;
    stream.appendChild(typingRow);
    stream.scrollTop = stream.scrollHeight;

    try {
      const res = await API.chat({
        message: text,
        projectId: projSelect.value || undefined,
        searchMode: modeSelect.value || 'hybrid',
        topK: parseInt(topkSelect.value, 10) || 5,
      });

      typingRow.remove();

      const sources = res.sources || res.citations || [];
      const redactionCount = res.redactions !== undefined ? res.redactions : (res.redactions_count || 0);
      const provName = res.provider || res.provider_name || 'AI';

      const redactionHtml = redactionCount > 0
        ? `<span class="redaction-indicator" title="${redactionCount} sensitive secrets (keys, passwords, tokens) were masked locally before generation">🛡️ ${redactionCount} Redacted</span>`
        : '';

      const citationsHtml = sources.length > 0
        ? `
        <div class="citations-box">
          <div class="citations-header">
            <span>Source Grounding Citations</span>
            <span class="citations-count-badge">${sources.length} cited source${sources.length > 1 ? 's' : ''}</span>
          </div>
          <div class="citations-list">
            ${sources.map((c) => {
              const loc = c.location || (c.start_line && c.end_line ? `Lines ${c.start_line}-${c.end_line}` : `Chunk #${(c.chunk_index !== undefined ? c.chunk_index : 0)}`);
              const scoreVal = c.relevance_score !== undefined ? c.relevance_score : c.score;
              const scoreBadge = scoreVal !== undefined ? `<span class="citation-score">Relevance: ${scoreVal}</span>` : '';
              const snippetText = c.snippet_preview || c.snippet || '';
              return `
                <div class="citation-card" onclick="window.viewFileDetail('${c.file_id}')" title="Inspect file: ${escapeHtml(c.relative_path || c.path || c.filename)}">
                  <div class="citation-top">
                    <div class="citation-file-info">
                      <span class="citation-filename">📄 ${escapeHtml(c.filename)}</span>
                      <span class="citation-location">${loc}</span>
                    </div>
                    ${scoreBadge}
                  </div>
                  <div class="citation-snippet">${escapeHtml(snippetText)}</div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
        `
        : '';

      const assistantRow = document.createElement('div');
      assistantRow.className = 'chat-message-row assistant';
      assistantRow.innerHTML = `
        <div class="chat-bubble">
          <div class="bubble-header">
            <span class="assistant-tag">⚡ SVANT RAG</span>
            ${redactionHtml}
          </div>
          <div class="assistant-text">${formatAIAnswer(res.answer)}</div>
          ${citationsHtml}
          <div class="bubble-meta-footer">
            <span>Mode: ${(res.mode || 'hybrid').toUpperCase()}</span>
            <span>·</span>
            <span>Context Chunks: ${res.context_count !== undefined ? res.context_count : sources.length}</span>
            <span>·</span>
            <span>Provider: ${escapeHtml(provName)}</span>
            <span>·</span>
            <span style="color: var(--emerald-primary);">✓ Grounded Context</span>
          </div>
        </div>
      `;
      stream.appendChild(assistantRow);
      input.value = '';
    } catch (err) {
      typingRow.remove();
      const errorRow = document.createElement('div');
      errorRow.className = 'chat-message-row assistant';
      errorRow.innerHTML = `
        <div class="chat-bubble" style="border-color: var(--rose-primary);">
          <div class="bubble-header">
            <span class="assistant-tag" style="color: var(--rose-primary);">⚠️ Error</span>
          </div>
          <div class="assistant-text" style="color: var(--rose-primary);">${escapeHtml(err.message)}</div>
        </div>
      `;
      stream.appendChild(errorRow);
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
      stream.scrollTop = stream.scrollHeight;
    }
  }

  // Chat Event Listeners
  const chatSendBtn = document.getElementById('btn-chat-send');
  if (chatSendBtn) {
    chatSendBtn.addEventListener('click', sendChatMessage);
  }

  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }

  const chatClearBtn = document.getElementById('btn-clear-chat');
  if (chatClearBtn) {
    chatClearBtn.addEventListener('click', () => {
      const stream = document.getElementById('chat-stream');
      stream.innerHTML = `
        <div class="chat-welcome-card" id="chat-welcome">
          <div class="welcome-glyph">✨</div>
          <h2>Grounded Local RAG Assistant</h2>
          <p>Ask questions about your codebase, documentation, and tracked repositories. Every answer is strictly grounded in retrieved local chunks with full source citations.</p>
          <div class="chat-feature-pills">
            <span class="chat-pill">🔒 Zero Secret Leakage (Local Redaction)</span>
            <span class="chat-pill">📑 Precise Source & Line Range Citations</span>
            <span class="chat-pill">⚡ Hybrid FTS5 + FAISS Vector Retrieval</span>
            <span class="chat-pill">🛡️ Honest "I don't know" when context lacks facts</span>
          </div>
        </div>
      `;
      showToast('Chat history cleared', 'info');
    });
  }

  // =====================================================================
  // PHASE 4 & 5: HEALTH, SECURITY, DUPLICATES & AI INSIGHTS
  // =====================================================================

  let currentRecommendationsData = null;
  let activeTierFilter = 'all';

  function populateSelect(selectElem, currentVal) {
    if (!selectElem) return;
    const existingVal = currentVal || selectElem.value;
    selectElem.innerHTML = '';
    state.projects.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.root_path})`;
      selectElem.appendChild(opt);
    });
    if (existingVal && state.projects.some((p) => p.id === existingVal)) {
      selectElem.value = existingVal;
    } else if (state.projects.length) {
      selectElem.value = state.projects[0].id;
    }
  }

  // --- HEALTH VIEW ---
  async function loadHealthView() {
    const projSelect = document.getElementById('health-project-select');
    populateSelect(projSelect);
    const projectId = projSelect ? projSelect.value : null;
    if (!projectId) {
      document.getElementById('health-empty-state').style.display = 'block';
      document.getElementById('health-content').style.display = 'none';
      return;
    }

    try {
      const health = await API.getProjectHealth(projectId);
      document.getElementById('health-empty-state').style.display = 'none';
      const content = document.getElementById('health-content');
      content.style.display = 'block';

      // Overall Grade & Summary
      const gradeBadge = document.getElementById('health-grade-badge');
      gradeBadge.textContent = health.grade;
      gradeBadge.className = `grade-badge-large grade-${health.grade}`;

      document.getElementById('health-score-number').textContent = health.overall_score;
      document.getElementById('health-summary-text').textContent = health.summary;
      document.getElementById('health-timestamp').textContent = `Last analyzed: ${formatDate(health.analyzed_at)}`;

      document.getElementById('health-count-crit').textContent = `${health.critical_count} Critical`;
      document.getElementById('health-count-high').textContent = `${health.high_count} High`;
      document.getElementById('health-count-med').textContent = `${health.medium_count} Medium`;
      document.getElementById('health-count-low').textContent = `${health.low_count} Low`;

      // Components Grid
      const compGrid = document.getElementById('health-components-grid');
      compGrid.innerHTML = '';
      if (health.component_scores) {
        Object.entries(health.component_scores).forEach(([catKey, comp]) => {
          const compCard = document.createElement('div');
          compCard.className = 'component-card';
          let colorClass = 'score-green';
          if (comp.score < 60) colorClass = 'score-red';
          else if (comp.score < 80) colorClass = 'score-yellow';
          else if (comp.score < 90) colorClass = 'score-blue';

          const pctWeight = Math.round(comp.weight * 100);
          compCard.innerHTML = `
            <div class="comp-header">
              <span class="comp-name">${escapeHtml(comp.category || catKey)}</span>
              <span class="comp-weight">${pctWeight}% Weight · <strong>${comp.score}/100</strong></span>
            </div>
            <div class="comp-score-bar">
              <div class="comp-score-fill ${colorClass}" style="width: ${comp.score}%;"></div>
            </div>
            <div class="comp-rationale">${escapeHtml(comp.rationale)}</div>
          `;
          compGrid.appendChild(compCard);
        });
      }

      // Recommendations
      loadRecommendations(projectId);
    } catch (err) {
      // Not analyzed yet
      document.getElementById('health-empty-state').style.display = 'block';
      document.getElementById('health-content').style.display = 'none';
    }
  }

  async function loadRecommendations(projectId) {
    try {
      const recs = await API.getProjectRecommendations(projectId);
      currentRecommendationsData = recs;
      renderRecommendationsList();
    } catch (err) {
      console.error('Error fetching recommendations:', err);
    }
  }

  function renderRecommendationsList() {
    const recsContainer = document.getElementById('health-recommendations-list');
    if (!recsContainer || !currentRecommendationsData) return;
    recsContainer.innerHTML = '';

    const tiers = currentRecommendationsData.recommendations_by_tier || {};
    let allItems = [];
    if (activeTierFilter === 'all') {
      allItems = [
        ...(tiers.fix_first || []),
        ...(tiers.should_fix || []),
        ...(tiers.nice_to_improve || []),
        ...(tiers.informational || []),
      ];
    } else {
      allItems = tiers[activeTierFilter] || [];
    }

    if (!allItems.length) {
      recsContainer.innerHTML = `
        <div class="empty-state-card">
          <div class="empty-icon">✅</div>
          <h3>No Open Issues in this Tier</h3>
          <p>Great job! No unresolved findings match the selected filter.</p>
        </div>
      `;
      return;
    }

    allItems.forEach((f) => {
      const card = createFindingCard(f, document.getElementById('health-project-select').value, () => {
        loadHealthView();
      });
      recsContainer.appendChild(card);
    });
  }

  function createFindingCard(finding, projectId, onStatusUpdate) {
    const card = document.createElement('div');
    card.className = `finding-card severity-${finding.severity}`;

    const sevBadgeClass = `badge-${finding.severity === 'critical' ? 'crit' : finding.severity === 'high' ? 'high' : finding.severity === 'medium' ? 'med' : 'low'}`;
    const evidenceHtml = finding.evidence ? `<div class="finding-evidence"><code>${escapeHtml(finding.evidence)}</code></div>` : '';

    card.innerHTML = `
      <div class="finding-top-row">
        <div class="finding-title-group">
          <span class="health-meta-badge ${sevBadgeClass}">${finding.severity.toUpperCase()}</span>
          <span class="finding-title">${escapeHtml(finding.title)}</span>
          <span class="finding-path">${escapeHtml(finding.relative_path || 'Project Root')}</span>
        </div>
        <div class="finding-actions">
          <select class="form-control select-status-toggle" style="font-size: 11px; padding: 4px 8px;">
            <option value="open" ${finding.status === 'open' ? 'selected' : ''}>Open</option>
            <option value="acknowledged" ${finding.status === 'acknowledged' ? 'selected' : ''}>Acknowledged</option>
            <option value="resolved" ${finding.status === 'resolved' ? 'selected' : ''}>Resolved</option>
            <option value="ignored" ${finding.status === 'ignored' ? 'selected' : ''}>Ignored</option>
          </select>
          <button class="btn btn-ghost btn-sm btn-explain-finding" title="Ask AI to analyze and provide code fix">
            <span>💡 Explain</span>
          </button>
        </div>
      </div>
      <div class="finding-desc">${escapeHtml(finding.description)}</div>
      ${evidenceHtml}
      <div class="finding-rec">
        <strong>Recommendation:</strong> ${escapeHtml(finding.recommendation)}
      </div>
    `;

    // Status change listener
    const statusSelect = card.querySelector('.select-status-toggle');
    statusSelect.addEventListener('change', async () => {
      try {
        await API.updateFindingStatus(projectId, finding.id, statusSelect.value);
        showToast(`Finding marked as ${statusSelect.value}`, 'success');
        if (onStatusUpdate) onStatusUpdate();
      } catch (err) {
        showToast(`Failed to update status: ${err.message}`, 'error');
      }
    });

    // Explain listener
    const explainBtn = card.querySelector('.btn-explain-finding');
    explainBtn.addEventListener('click', async () => {
      showAIModal(`Explaining Finding: ${finding.title}`, 'Analyzing finding impact and drafting code remediation...');
      try {
        const res = await API.aiExplainFinding(projectId, finding.id);
        renderAIModalContent(res.content);
      } catch (err) {
        renderAIModalContent(`Failed to explain finding: ${err.message}`);
      }
    });

    return card;
  }

  // --- SECURITY VIEW ---
  async function loadSecurityView() {
    const projSelect = document.getElementById('security-project-select');
    populateSelect(projSelect);
    const projectId = projSelect ? projSelect.value : null;
    if (!projectId) return;

    const sevFilter = document.getElementById('security-severity-filter').value;
    const statusFilter = document.getElementById('security-status-filter').value;

    try {
      const findings = await API.getProjectFindings(projectId, {
        category: 'security',
        severity: sevFilter || undefined,
        status: statusFilter || undefined,
      });

      // Update counters
      const critCount = findings.filter((f) => f.severity === 'critical' && f.status === 'open').length;
      const highCount = findings.filter((f) => f.severity === 'high' && f.status === 'open').length;
      document.getElementById('sec-count-crit').textContent = `${critCount} Critical`;
      document.getElementById('sec-count-high').textContent = `${highCount} High`;
      document.getElementById('sec-count-total').textContent = `${findings.length} Total`;

      const listContainer = document.getElementById('security-findings-list');
      listContainer.innerHTML = '';

      if (!findings.length) {
        listContainer.innerHTML = `
          <div class="empty-state-card">
            <div class="empty-icon">🛡️</div>
            <h3>No Security Findings Detected</h3>
            <p>Codebase is clean. Zero exposed secrets or dangerous configurations match this filter.</p>
          </div>
        `;
        return;
      }

      findings.forEach((f) => {
        const card = createFindingCard(f, projectId, () => {
          loadSecurityView();
        });
        listContainer.appendChild(card);
      });
    } catch (err) {
      console.error('Error loading security findings:', err);
    }
  }

  // --- DUPLICATES VIEW ---
  async function loadDuplicatesView() {
    const projSelect = document.getElementById('duplicates-project-select');
    populateSelect(projSelect);
    const projectId = projSelect ? projSelect.value : null;
    if (!projectId) return;

    try {
      const clusters = await API.getProjectDuplicates(projectId);
      const totalClusters = clusters.length;
      let totalWasted = 0;
      let totalCopies = 0;

      clusters.forEach((c) => {
        totalWasted += c.wasted_bytes || 0;
        totalCopies += c.count || 0;
      });

      document.getElementById('dup-total-clusters').textContent = totalClusters;
      document.getElementById('dup-wasted-storage').textContent = formatBytes(totalWasted);
      document.getElementById('dup-total-copies').textContent = totalCopies;

      const listContainer = document.getElementById('duplicates-clusters-list');
      listContainer.innerHTML = '';

      if (!clusters.length) {
        listContainer.innerHTML = `
          <div class="empty-state-card">
            <div class="empty-icon">✨</div>
            <h3>No Duplicate Files Found</h3>
            <p>Every file in this project has unique content. No redundant storage detected.</p>
          </div>
        `;
        return;
      }

      clusters.forEach((cl) => {
        const card = document.createElement('div');
        card.className = 'dup-cluster-card';
        const fileItems = (cl.files || [])
          .map((f) => `<div class="dup-file-item"><span>${escapeHtml(f.relative_path || f.filename)}</span><span>${formatBytes(f.size_bytes)}</span></div>`)
          .join('');

        card.innerHTML = `
          <div class="dup-cluster-header">
            <div>
              <span class="dup-hash">SHA-256: ${cl.sha256.substring(0, 16)}...</span>
              <span class="health-meta-badge badge-med" style="margin-left: 8px;">${cl.count} copies</span>
            </div>
            <div class="dup-stats">
              Each: ${formatBytes(cl.size_bytes)} · <strong>Wasted: ${formatBytes(cl.wasted_bytes)}</strong>
            </div>
          </div>
          <div class="dup-file-list">${fileItems}</div>
        `;
        listContainer.appendChild(card);
      });
    } catch (err) {
      console.error('Error loading duplicates:', err);
    }
  }

  // --- AI MODAL HELPER ---
  const modalAIInsight = document.getElementById('modal-ai-insight');
  const modalAITitle = document.getElementById('modal-ai-title');
  const modalAIBody = document.getElementById('modal-ai-body');
  let currentAIMarkdown = '';

  function showAIModal(title, initialText) {
    if (!modalAIInsight) return;
    modalAITitle.textContent = title;
    currentAIMarkdown = initialText;
    modalAIBody.innerHTML = `<p>${escapeHtml(initialText)}</p>`;
    modalAIInsight.classList.add('active');
  }

  function renderAIModalContent(markdown) {
    currentAIMarkdown = markdown;
    modalAIBody.innerHTML = formatMarkdown(markdown);
  }

  const closeAIModalBtn = document.getElementById('btn-close-ai-modal');
  if (closeAIModalBtn) {
    closeAIModalBtn.addEventListener('click', () => {
      modalAIInsight.classList.remove('active');
    });
  }

  const copyAIInsightBtn = document.getElementById('btn-copy-ai-insight');
  if (copyAIInsightBtn) {
    copyAIInsightBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(currentAIMarkdown);
      showToast('Copied to clipboard!', 'success');
    });
  }

  const discussChatBtn = document.getElementById('btn-discuss-in-chat');
  if (discussChatBtn) {
    discussChatBtn.addEventListener('click', () => {
      modalAIInsight.classList.remove('active');
      switchPage('aichat');
      const chatInput = document.getElementById('chat-input');
      if (chatInput) {
        chatInput.value = `Explain the key recommendations from the recent project health analysis and help me plan fixes.`;
        chatInput.focus();
      }
    });
  }

  // --- EVENT LISTENERS FOR HEALTH / SECURITY / DUPLICATES ---
  const healthSelect = document.getElementById('health-project-select');
  if (healthSelect) healthSelect.addEventListener('change', loadHealthView);

  const securitySelect = document.getElementById('security-project-select');
  if (securitySelect) securitySelect.addEventListener('change', loadSecurityView);
  const secSevFilter = document.getElementById('security-severity-filter');
  if (secSevFilter) secSevFilter.addEventListener('change', loadSecurityView);
  const secStatusFilter = document.getElementById('security-status-filter');
  if (secStatusFilter) secStatusFilter.addEventListener('change', loadSecurityView);

  const dupSelect = document.getElementById('duplicates-project-select');
  if (dupSelect) dupSelect.addEventListener('change', loadDuplicatesView);

  // Filter pills for recommendations
  const recFilterGroup = document.getElementById('recommendation-tier-filter');
  if (recFilterGroup) {
    recFilterGroup.addEventListener('click', (e) => {
      if (e.target.classList.contains('pill')) {
        recFilterGroup.querySelectorAll('.pill').forEach((p) => p.classList.remove('active'));
        e.target.classList.add('active');
        activeTierFilter = e.target.dataset.tier;
        renderRecommendationsList();
      }
    });
  }

  // Run Health Analysis button
  const runAnalysisBtn = document.getElementById('btn-run-analysis');
  if (runAnalysisBtn) {
    runAnalysisBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('health-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      runAnalysisBtn.disabled = true;
      runAnalysisBtn.innerHTML = '<span>⏳ Analyzing Codebase...</span>';
      showToast('Running project intelligence, health & security analysis...', 'info');

      try {
        const res = await API.analyzeProject(projectId);
        showToast(`Analysis completed! Grade ${res.grade} (${res.overall_score}/100)`, 'success');
        await loadHealthView();
      } catch (err) {
        showToast(`Analysis failed: ${err.message}`, 'error');
      } finally {
        runAnalysisBtn.disabled = false;
        runAnalysisBtn.innerHTML = '<span>⚡ Run Health Analysis</span>';
      }
    });
  }

  // Run Security Scan button
  const secScanBtn = document.getElementById('btn-security-scan');
  if (secScanBtn) {
    secScanBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('security-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      secScanBtn.disabled = true;
      secScanBtn.innerHTML = '<span>⏳ Scanning Secrets...</span>';
      try {
        await API.analyzeProject(projectId);
        showToast('Security scan completed successfully!', 'success');
        await loadSecurityView();
      } catch (err) {
        showToast(`Security scan failed: ${err.message}`, 'error');
      } finally {
        secScanBtn.disabled = false;
        secScanBtn.innerHTML = '<span>🛡️ Run Security Scan</span>';
      }
    });
  }

  // Refresh Duplicates button
  const refreshDupBtn = document.getElementById('btn-refresh-duplicates');
  if (refreshDupBtn) {
    refreshDupBtn.addEventListener('click', () => {
      loadDuplicatesView();
      showToast('Duplicates view refreshed', 'info');
    });
  }

  // AI Summarize button
  const aiSummarizeBtn = document.getElementById('btn-ai-summarize');
  if (aiSummarizeBtn) {
    aiSummarizeBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('health-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      showAIModal('Project Executive Summary', 'Analyzing codebase structure, languages, health metrics, and active risks...');
      try {
        const res = await API.aiSummarizeProject(projectId);
        renderAIModalContent(res.content);
      } catch (err) {
        renderAIModalContent(`Failed to generate summary: ${err.message}`);
      }
    });
  }

  // AI Plan button
  const aiPlanBtn = document.getElementById('btn-ai-plan');
  if (aiPlanBtn) {
    aiPlanBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('health-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      showAIModal('Phased Remediation Plan', 'Formulating phased remediation steps based on prioritized findings...');
      try {
        const res = await API.aiImprovementPlan(projectId);
        renderAIModalContent(res.content);
      } catch (err) {
        renderAIModalContent(`Failed to generate remediation plan: ${err.message}`);
      }
    });
  }

  // Initial load
  checkHealth();
  loadDashboardData();
  updateAIStatusBadge();
  setInterval(checkHealth, 15000); // 15s health heartbeat
});

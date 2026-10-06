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
    security: { title: 'Secret Detection', subtitle: 'Static secret scanning and leak prevention (Roadmap Phase 4)' },
    duplicates: { title: 'Duplicate Analysis', subtitle: 'Identify redundant and identical files (Roadmap Phase 5)' },
    health: { title: 'Project Health', subtitle: 'Codebase architecture metrics and hygiene scoring (Roadmap Phase 5)' },
    aichat: { title: 'AI Assistant', subtitle: 'Grounded project Q&A with Gemini and local models (Roadmap Phase 6)' },
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
      document.getElementById('stat-indexed').textContent = stats.total_indexed_files.toLocaleString();
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
      .map(
        (p) => `
      <div class="project-card">
        <div class="project-card-header">
          <div>
            <div class="project-title">${escapeHtml(p.name)}</div>
            <div class="project-path" title="${escapeHtml(p.root_path)}">${escapeHtml(p.root_path)}</div>
          </div>
          <span class="tag-cat ${p.status === 'ready' ? 'document' : 'binary'}">${p.status}</span>
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
            <span class="proj-stat-label">Last Scan</span>
            <span class="proj-stat-val" style="font-size: 11.5px;">${formatDate(p.last_scanned_at)}</span>
          </div>
        </div>

        <div class="project-actions">
          <button class="btn btn-secondary btn-sm" onclick="window.viewProjectFiles('${p.id}')">Explore Files</button>
          <button class="btn btn-primary btn-sm" onclick="window.triggerScan('${p.id}')">Scan & Index</button>
          <button class="btn btn-danger btn-sm" onclick="window.confirmUntrack('${p.id}', '${escapeJs(p.name)}')">Untrack</button>
        </div>
      </div>
    `
      )
      .join('');
  }

  function updateProjectFilterDropdowns(projects) {
    const fileSelect = document.getElementById('file-filter-project');
    const searchSelect = document.getElementById('search-project-select');

    const options = [
      '<option value="">All Projects</option>',
      ...projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`),
    ].join('');

    if (fileSelect) fileSelect.innerHTML = options;
    if (searchSelect) searchSelect.innerHTML = ['<option value="">Across All Tracked Projects</option>', ...projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)].join('');
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

  // Search View
  async function runSearch() {
    const queryInput = document.getElementById('search-query-input');
    const projectSelect = document.getElementById('search-project-select');
    const container = document.getElementById('search-results-container');

    const query = queryInput.value.trim();
    if (!query) {
      showToast('Please enter search terms', 'info');
      return;
    }

    container.innerHTML = `<div class="search-initial-state"><div class="hint-icon">⚡</div><h3>Searching FTS5 Index...</h3></div>`;

    try {
      const res = await API.search({
        query: query,
        projectId: projectSelect.value || undefined,
      });

      if (res.results.length === 0) {
        container.innerHTML = `
          <div class="search-initial-state">
            <div class="hint-icon">∅</div>
            <h3>No matches found</h3>
            <p>No indexed files matched query: "<strong>${escapeHtml(query)}</strong>"</p>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div style="font-family: var(--font-mono); font-size: 12px; color: var(--text-dim); margin-bottom: 8px;">
          Found ${res.total} matches across indexed files (SQLite FTS5 BM25)
        </div>
        ${res.results
          .map(
            (hit) => `
          <div class="search-hit-card" onclick="window.viewFileDetail('${hit.file_id}')">
            <div class="search-hit-header">
              <span class="search-hit-title">${escapeHtml(hit.filename)}</span>
              <span class="search-hit-proj">${escapeHtml(hit.project_name)} · Rank ${hit.score}</span>
            </div>
            <div class="search-hit-path">${escapeHtml(hit.relative_path)}</div>
            <div class="search-snippet">${hit.snippet}</div>
          </div>
        `
          )
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

  // Initial load
  checkHealth();
  loadDashboardData();
  setInterval(checkHealth, 15000); // 15s health heartbeat
});

/**
 * SVANT Frontend API Client
 * Interfaces directly with the Python backend REST API.
 */

const API = {
  baseUrl: window.location.origin,

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        let errMessage = `HTTP error ${response.status}`;
        try {
          const errorJson = await response.json();
          errMessage = errorJson.detail || errorJson.error || errMessage;
        } catch (_) {}
        throw new Error(errMessage);
      }

      return await response.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  getHealth() {
    return this.request('/health');
  },

  getStats() {
    return this.request('/api/stats');
  },

  getProjects() {
    return this.request('/api/projects');
  },

  createProject(path, name) {
    return this.request('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ path, name: name || undefined }),
    });
  },

  scanProject(projectId) {
    return this.request(`/api/projects/${projectId}/scan`, {
      method: 'POST',
    });
  },

  indexProject(projectId, forceRebuild = false) {
    return this.request(`/api/projects/${projectId}/index`, {
      method: 'POST',
      body: JSON.stringify({ force_rebuild: forceRebuild }),
    });
  },

  getIndexStatus(projectId) {
    return this.request(`/api/projects/${projectId}/index/status`);
  },

  rebuildIndex(projectId) {
    return this.request(`/api/projects/${projectId}/index/rebuild`, {
      method: 'POST',
    });
  },

  deleteProject(projectId) {
    return this.request(`/api/projects/${projectId}`, {
      method: 'DELETE',
    });
  },

  getFiles({ projectId, category, extension, search, limit = 100, offset = 0 } = {}) {
    const params = new URLSearchParams();
    if (projectId) params.append('project_id', projectId);
    if (category) params.append('category', category);
    if (extension) params.append('extension', extension);
    if (search) params.append('search', search);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());
    return this.request(`/api/files?${params.toString()}`);
  },

  getFileDetail(fileId) {
    return this.request(`/api/files/${fileId}`);
  },

  search({ query, projectId, mode = 'keyword' } = {}) {
    const params = new URLSearchParams();
    params.append('q', query);
    if (projectId) params.append('project_id', projectId);
    params.append('mode', mode);
    return this.request(`/api/search?${params.toString()}`);
  },

  getAIStatus() {
    return this.request('/api/chat/status');
  },

  chat({ message, projectId, searchMode = 'hybrid', topK = 5, provider } = {}) {
    return this.request('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        project_id: projectId || undefined,
        search_mode: searchMode,
        top_k: topK,
        provider: provider || undefined,
      }),
    });
  },
};


"""Modern Control Center & Interactive Chat Dashboard for SAGO Webserver."""

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SAGO Orchestration Platform</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 50: '#f0fdf4', 500: '#10b981', 600: '#059669' },
            dark: { 900: '#090b10', 800: '#12161f', 700: '#1a202c', 600: '#2d3748' }
          },
          fontFamily: {
            sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
            mono: ['JetBrains Mono', 'Fira Code', 'monospace']
          }
        }
      }
    }
  </script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
  <style>
    @keyframes pulseGlow {
      0%, 100% { opacity: 0.8; filter: drop-shadow(0 0 10px rgba(16, 185, 129, 0.4)); }
      50% { opacity: 0.3; filter: drop-shadow(0 0 3px rgba(16, 185, 129, 0.1)); }
    }
    .glow-dot { animation: pulseGlow 2s infinite ease-in-out; }
    .glass {
      background: rgba(18, 22, 31, 0.8);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .glass-card {
      background: rgba(26, 32, 44, 0.45);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.06);
      transition: all 0.2s ease;
    }
    .session-item.active {
      background: rgba(16, 185, 129, 0.12);
      border-color: rgba(16, 185, 129, 0.4);
    }
    .prose pre {
      background: #0d1117 !important;
      border: 1px solid #30363d;
      border-radius: 0.5rem;
      padding: 0.75rem;
      margin: 0.5rem 0;
      overflow-x: auto;
    }
    .prose code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
    }
    .prose p { margin-bottom: 0.5rem; }
    .prose p:last-child { margin-bottom: 0; }
    .prose ul { list-style-type: disc; margin-left: 1.25rem; margin-bottom: 0.5rem; }
    .prose ol { list-style-type: decimal; margin-left: 1.25rem; margin-bottom: 0.5rem; }
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 9999px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.3); }
  </style>
</head>
<body class="bg-[#090b10] text-[#e2e8f0] min-h-screen font-sans antialiased selection:bg-emerald-500 selection:text-black">
  <div class="flex flex-col h-screen overflow-hidden">
    <!-- Header -->
    <header class="glass border-b border-white/5 px-6 py-3 shrink-0 z-10">
      <div class="max-w-7xl mx-auto flex items-center justify-between">
        <div class="flex items-center space-x-3">
          <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <span class="text-white font-bold text-sm tracking-wider">S</span>
          </div>
          <div>
            <h1 class="text-base font-semibold tracking-tight text-white flex items-center gap-2">
              SAGO Platform <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-mono border border-emerald-500/20">v0.1.13</span>
            </h1>
            <p class="text-[11px] text-gray-400">Multi-Agent Control Center & Interactive Chat</p>
          </div>
        </div>

        <div class="flex items-center space-x-3">
          <button onclick="openTracesModal()" class="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-white/5 hover:bg-white/10 text-purple-300 border border-white/10 transition flex items-center gap-1.5" title="Execution Traces (F2)">
            <span>📊 Traces (F2)</span>
          </button>
          <button onclick="openDiffModal()" class="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-white/5 hover:bg-white/10 text-yellow-300 border border-white/10 transition flex items-center gap-1.5" title="Git Diff (F3)">
            <span>⚡ Diff (F3)</span>
          </button>
          <button onclick="openFilesModal()" class="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-white/5 hover:bg-white/10 text-blue-300 border border-white/10 transition flex items-center gap-1.5" title="File Explorer (F4)">
            <span>📁 Files (F4)</span>
          </button>
          <button onclick="newSessionModal()" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black shadow transition flex items-center gap-1.5">
            <span>+</span> <span>New Session</span>
          </button>
          <div id="conn-pill" class="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/10 text-xs text-gray-300">
            <span id="conn-dot" class="w-2 h-2 rounded-full bg-emerald-400 glow-dot"></span>
            <span id="conn-text" class="font-medium">Connected</span>
          </div>
        </div>
      </div>
    </header>

    <!-- Main Workspace Split -->
    <div class="flex-1 flex max-w-7xl w-full mx-auto overflow-hidden p-4 gap-4">

      <!-- Left Sidebar: Sessions & Context -->
      <aside class="w-80 flex flex-col glass-card rounded-2xl p-4 shrink-0 overflow-hidden">
        <div class="flex items-center justify-between pb-3 border-b border-white/5 mb-3">
          <span class="text-xs font-semibold text-gray-200 tracking-tight">Recent Sessions</span>
          <button onclick="fetchSessions()" class="text-xs text-gray-400 hover:text-emerald-400 transition">↻ Refresh</button>
        </div>

        <div id="sessions-container" class="flex-1 overflow-y-auto space-y-2 pr-1 text-xs">
          <div class="text-gray-500 py-6 text-center">Loading sessions...</div>
        </div>

        <div class="pt-3 border-t border-white/5 mt-3 space-y-2">
          <div class="text-[11px] text-gray-400 flex justify-between items-center">
            <span>Engine Backend</span>
            <span class="font-mono text-emerald-400">Native</span>
          </div>
          <div class="text-[11px] text-gray-400 flex justify-between items-center">
            <span>Session ID</span>
            <span id="cur-session-label" class="font-mono text-gray-200 truncate max-w-[140px]">-</span>
          </div>
          <div class="text-[11px] text-gray-400 flex justify-between items-center">
            <span>Workspace</span>
            <span id="cur-workspace-label" class="font-mono text-emerald-400 truncate max-w-[140px]" title="Workspace folder">-</span>
          </div>
        </div>
      </aside>

      <!-- Right Main Chat & Execution Area -->
      <main class="flex-1 flex flex-col glass-card rounded-2xl overflow-hidden shadow-2xl">
        <!-- Chat Header -->
        <div class="px-5 py-3 border-b border-white/5 flex items-center justify-between bg-black/20 shrink-0">
          <div class="flex items-center space-x-2">
            <span id="session-title-display" class="text-sm font-semibold text-white">Interactive Session</span>
            <span id="thinking-badge" class="hidden text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono animate-pulse">Thinking & Executing</span>
          </div>
          <div class="flex items-center space-x-3">
            <span class="text-[11px] font-mono px-2.5 py-1 rounded-md bg-white/5 border border-white/10 text-emerald-400">
              Agent: <span class="font-bold text-white">sago</span>
            </span>
            <button onclick="clearChat()" class="text-xs text-gray-400 hover:text-gray-200 px-2 py-1 transition">Clear View</button>
          </div>
        </div>

        <!-- Messages Feed -->
        <div id="chat-feed" class="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
          <div id="empty-state" class="h-full flex flex-col items-center justify-center text-gray-500 space-y-2 py-12">
            <span class="text-2xl">💬</span>
            <p class="font-medium text-gray-400">Start a new conversation or dispatch a specialist agent</p>
            <p class="text-[11px] text-gray-600">Type below to run code, debug errors, edit files, or execute deep tasks</p>
          </div>
        </div>

        <!-- Tool / Thinking Live Strip -->
        <div id="live-tool-strip" class="hidden px-5 py-2 bg-black/40 border-t border-white/5 text-[11px] font-mono text-emerald-400 flex items-center justify-between shrink-0">
          <div id="live-tool-content" class="truncate max-w-[80%] flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
            <span>Running tool...</span>
          </div>
        </div>

        <!-- Quick Slash Command Chips -->
        <div class="px-4 py-2 border-t border-white/5 bg-black/40 flex items-center gap-2 overflow-x-auto text-[11px] shrink-0">
          <span class="text-gray-500 font-mono text-[10px]">Commands:</span>
          <button onclick="insertCommand('/plan ')" class="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-emerald-400 border border-white/5">/plan</button>
          <button onclick="insertCommand('/think ')" class="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-blue-400 border border-white/5">/think</button>
          <button onclick="openDiffModal()" class="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-yellow-400 border border-white/5">/diff</button>
          <button onclick="openFilesModal()" class="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-blue-400 border border-white/5">/files</button>
          <button onclick="openTracesModal()" class="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-purple-400 border border-white/5">/traces</button>
          <button onclick="clearChat()" class="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-gray-400 border border-white/5">/clear</button>
        </div>

        <!-- Input Box & Autocomplete Popup Container -->
        <div class="p-4 border-t border-white/5 bg-black/30 shrink-0 relative">
          <!-- Autocomplete Dropdown Popup -->
          <div id="autocomplete-popup" class="hidden absolute bottom-full left-4 right-4 mb-2 max-h-56 overflow-y-auto rounded-xl bg-[#161b22] border border-white/10 shadow-2xl p-1.5 font-mono text-xs z-20 space-y-1">
          </div>

          <div class="relative flex items-end gap-2">
            <textarea id="task-input" rows="2" placeholder="Send a message or task (Type / for commands, @ for agents, # for files)..." class="flex-1 bg-black/50 border border-white/10 rounded-xl p-3 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 transition resize-none"></textarea>
            <button id="send-btn" onclick="sendMessage()" class="px-4 py-3 text-xs font-semibold rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black shadow transition flex items-center gap-1 shrink-0">
              <span>Send</span> <span>→</span>
            </button>
          </div>
        </div>
      </main>

    </div>
  </div>

  <!-- Diff Viewer Modal (F3) -->
  <div id="diff-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6 modal-backdrop">
    <div class="glass border border-white/10 rounded-2xl w-full max-w-5xl max-h-[85vh] flex flex-col overflow-hidden shadow-2xl">
      <div class="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/40">
        <h3 class="text-sm font-semibold text-white flex items-center gap-2">
          <span>⚡ Live Workspace Diff</span>
          <span id="diff-file-count" class="text-xs px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-300 font-mono">0 files</span>
        </h3>
        <button onclick="closeDiffModal()" class="text-gray-400 hover:text-white text-lg">✕</button>
      </div>
      <div id="diff-content-container" class="flex-1 overflow-y-auto p-4 font-mono text-xs text-gray-300 bg-[#0d1117] space-y-2">
        <pre id="diff-content" class="leading-relaxed whitespace-pre-wrap">Loading git diff...</pre>
      </div>
      <div class="px-6 py-3 border-t border-white/10 bg-black/40 flex justify-end">
        <button onclick="closeDiffModal()" class="px-4 py-1.5 text-xs font-medium rounded-lg bg-white/10 hover:bg-white/20 text-white transition">Close (Esc)</button>
      </div>
    </div>
  </div>

  <!-- File Explorer Modal (F4) -->
  <div id="files-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6 modal-backdrop">
    <div class="glass border border-white/10 rounded-2xl w-full max-w-3xl max-h-[80vh] flex flex-col overflow-hidden shadow-2xl">
      <div class="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/40">
        <h3 class="text-sm font-semibold text-white flex items-center gap-2">
          <span>📁 Workspace File Explorer</span>
          <span id="files-current-dir" class="text-xs font-mono text-gray-400 truncate max-w-md"></span>
        </h3>
        <button onclick="closeFilesModal()" class="text-gray-400 hover:text-white text-lg">✕</button>
      </div>
      <div id="files-list" class="flex-1 overflow-y-auto p-4 space-y-1.5 font-mono text-xs text-gray-200">
        Loading directory files...
      </div>
      <div class="px-6 py-3 border-t border-white/10 bg-black/40 flex justify-end">
        <button onclick="closeFilesModal()" class="px-4 py-1.5 text-xs font-medium rounded-lg bg-white/10 hover:bg-white/20 text-white transition">Close (Esc)</button>
      </div>
    </div>
  </div>

  <!-- File Content Viewer Modal -->
  <div id="file-viewer-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6 modal-backdrop">
    <div class="glass border border-white/10 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden shadow-2xl">
      <div class="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/40">
        <h3 class="text-sm font-semibold text-white flex items-center gap-2">
          <span>📄 File Viewer:</span>
          <span id="file-viewer-path" class="text-xs font-mono text-emerald-400 truncate max-w-md"></span>
        </h3>
        <button onclick="closeFileViewerModal()" class="text-gray-400 hover:text-white text-lg">✕</button>
      </div>
      <div class="flex-1 overflow-y-auto p-4 font-mono text-xs text-gray-200 bg-[#0d1117]">
        <pre><code id="file-viewer-code" class="leading-relaxed"></code></pre>
      </div>
      <div class="px-6 py-3 border-t border-white/10 bg-black/40 flex justify-end">
        <button onclick="closeFileViewerModal()" class="px-4 py-1.5 text-xs font-medium rounded-lg bg-white/10 hover:bg-white/20 text-white transition">Close (Esc)</button>
      </div>
    </div>
  </div>

  <!-- Execution Traces Modal (F2) -->
  <div id="traces-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6 modal-backdrop">
    <div class="glass border border-white/10 rounded-2xl w-full max-w-3xl max-h-[80vh] flex flex-col overflow-hidden shadow-2xl">
      <div class="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-black/40">
        <h3 class="text-sm font-semibold text-white flex items-center gap-2">
          <span>📊 Execution Traces & Graph Spans</span>
        </h3>
        <button onclick="closeTracesModal()" class="text-gray-400 hover:text-white text-lg">✕</button>
      </div>
      <div id="traces-list" class="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-xs text-gray-300">
        Loading traces...
      </div>
      <div class="px-6 py-3 border-t border-white/10 bg-black/40 flex justify-end">
        <button onclick="closeTracesModal()" class="px-4 py-1.5 text-xs font-medium rounded-lg bg-white/10 hover:bg-white/20 text-white transition">Close (Esc)</button>
      </div>
    </div>
  </div>

  <!-- New Session & Workspace Modal -->
  <div id="new-session-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6 modal-backdrop">
    <div class="glass border border-white/10 rounded-2xl w-full max-w-md flex flex-col overflow-hidden shadow-2xl p-6 space-y-4">
      <h3 class="text-sm font-semibold text-white">Create New Session</h3>
      <div>
        <label class="block text-xs text-gray-400 mb-1">Session Title</label>
        <input id="new-session-title" type="text" placeholder="e.g. Refactor API routes" class="w-full bg-black/50 border border-white/10 rounded-xl p-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500">
      </div>
      <div class="relative">
        <label class="block text-xs text-gray-400 mb-1">Workspace Folder Path</label>
        <input id="new-session-path" list="workspace-path-suggestions" type="text" placeholder="/path/to/project" class="w-full bg-black/50 border border-white/10 rounded-xl p-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500" autocomplete="off">
        <datalist id="workspace-path-suggestions"></datalist>
        <span class="text-[10px] text-gray-500 mt-1 block">Type path (e.g. /mnt or /home) for real-time filesystem suggestions.</span>
      </div>
      <div class="flex justify-end gap-2 pt-2">
        <button onclick="closeNewSessionModal()" class="px-3.5 py-1.5 text-xs font-medium rounded-lg bg-white/5 text-gray-300 hover:bg-white/10 transition">Cancel</button>
        <button onclick="confirmNewSession()" class="px-4 py-1.5 text-xs font-semibold rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black shadow transition">Create</button>
      </div>
    </div>
  </div>

  <script>
    let currentSessionId = localStorage.getItem('sago_active_session') || ('session_' + Math.random().toString(36).substring(2, 9));
    let ws = null;
    const runningSessions = new Set();

    function initWebSocket() {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${proto}//${window.location.host}/ws/sago_global_client`;

      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        document.getElementById('conn-dot').className = 'w-2 h-2 rounded-full bg-emerald-400 glow-dot';
        document.getElementById('conn-text').textContent = 'Connected';
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleWsEvent(data);
        } catch (e) {
          console.error("WS Parse error", e);
        }
      };

      ws.onclose = () => {
        document.getElementById('conn-dot').className = 'w-2 h-2 rounded-full bg-yellow-500';
        document.getElementById('conn-text').textContent = 'Reconnecting...';
        setTimeout(initWebSocket, 2500);
      };
    }

    function handleWsEvent(data) {
      const strip = document.getElementById('live-tool-strip');
      const stripContent = document.getElementById('live-tool-content');
      const targetSessionId = data.session_id || currentSessionId;

      if (data.type === 'tool_call') {
        runningSessions.add(targetSessionId);
        updateSidebarBadges();
        if (targetSessionId === currentSessionId) {
          strip.classList.remove('hidden');
          stripContent.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span> <span>Tool: <strong>${data.name}</strong></span>`;
          appendToolEvent(data.name, data.args, null);
        }
      } else if (data.type === 'tool_result') {
        if (targetSessionId === currentSessionId) {
          appendToolEvent(data.name, data.args, data.result);
        }
      } else if (data.type === 'thinking') {
        runningSessions.add(targetSessionId);
        updateSidebarBadges();
        if (targetSessionId === currentSessionId) {
          strip.classList.remove('hidden');
          stripContent.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-blue-400 animate-ping"></span> <span class="text-blue-300">Thinking: ${data.text.substring(0, 80)}...</span>`;
          appendThinkingEvent(data.text);
        }
      } else if (data.type === 'complete') {
        runningSessions.delete(targetSessionId);
        updateSidebarBadges();
        if (targetSessionId === currentSessionId) {
          strip.classList.add('hidden');
          document.getElementById('thinking-badge').classList.add('hidden');
          document.getElementById('send-btn').disabled = false;
          document.getElementById('task-input').disabled = false;

          appendMessage('assistant', data.output || 'Done', data.agent || 'sago');
        }
        fetchSessions();
      } else if (data.type === 'error') {
        runningSessions.delete(targetSessionId);
        updateSidebarBadges();
        if (targetSessionId === currentSessionId) {
          strip.classList.add('hidden');
          document.getElementById('thinking-badge').classList.add('hidden');
          document.getElementById('send-btn').disabled = false;
          document.getElementById('task-input').disabled = false;

          appendMessage('assistant', 'Error: ' + data.error, 'error');
        }
      }
    }

    function updateSidebarBadges() {
      document.querySelectorAll('.session-item').forEach(el => {
        const sid = el.id.replace('sess-', '');
        const badge = el.querySelector('.status-running-badge');
        if (runningSessions.has(sid)) {
          if (!badge) {
            const b = document.createElement('span');
            b.className = 'status-running-badge px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[9px] font-mono animate-pulse mr-1';
            b.textContent = 'running';
            el.querySelector('.truncate').prepend(b);
          }
        } else if (badge) {
          badge.remove();
        }
      });
    }

    function sendMessage() {
      const input = document.getElementById('task-input');
      const text = input.value.trim();
      if (!text) return;

      const agent = 'sago';
      const curWs = document.getElementById('cur-workspace-label').textContent;

      appendMessage('user', text);
      input.value = '';
      input.disabled = true;
      document.getElementById('send-btn').disabled = true;
      document.getElementById('thinking-badge').classList.remove('hidden');

      runningSessions.add(currentSessionId);
      updateSidebarBadges();

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'chat',
          message: text,
          agent: agent,
          session_id: currentSessionId,
          workspace_cwd: curWs
        }));
      } else {
        // Fallback to REST execute if WS disconnected
        fetch('/api/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task: text, agent: agent, session_id: currentSessionId, workspace_cwd: curWs })
        })
        .then(r => r.json())
        .then(res => {
          runningSessions.delete(currentSessionId);
          updateSidebarBadges();
          document.getElementById('thinking-badge').classList.add('hidden');
          document.getElementById('send-btn').disabled = false;
          input.disabled = false;
          appendMessage('assistant', res.output || res.message || 'Done', agent);
          fetchSessions();
        })
        .catch(err => {
          runningSessions.delete(currentSessionId);
          updateSidebarBadges();
          document.getElementById('thinking-badge').classList.add('hidden');
          document.getElementById('send-btn').disabled = false;
          input.disabled = false;
          appendMessage('assistant', 'Error: ' + err, 'error');
        });
      }
    }

    function appendMessage(role, content, agentName, metadata) {
      const feed = document.getElementById('chat-feed');
      const empty = document.getElementById('empty-state');
      if (empty) empty.style.display = 'none';

      if (role === 'user') {
        const row = document.createElement('div');
        row.className = 'flex justify-end my-2';
        const bubble = document.createElement('div');
        bubble.className = 'max-w-[80%] bg-emerald-600/20 text-emerald-100 border border-emerald-500/30 rounded-2xl rounded-tr-sm px-4 py-2.5 text-xs font-mono whitespace-pre-wrap leading-relaxed shadow-sm';
        bubble.textContent = content;
        row.appendChild(bubble);
        feed.appendChild(row);
        feed.scrollTop = feed.scrollHeight;
        return;
      }

      // Check if message content contains sequential thinking tags
      const regex = /<(?:thinking|thought)>([\\s\\S]*?)<\\/(?:thinking|thought)>/gi;
      const raw = content || '';
      let lastIdx = 0;
      let match;

      while ((match = regex.exec(raw)) !== null) {
        // Render text segment before this thinking block
        const preText = raw.substring(lastIdx, match.index).trim();
        if (preText) {
          renderAssistantBubble(preText, agentName);
        }
        // Render thinking block
        const thinkingText = match[1].trim();
        if (thinkingText) {
          appendThinkingEvent(thinkingText);
        }
        lastIdx = regex.lastIndex;
      }

      // Render remaining text segment after all thinking blocks
      const postText = raw.substring(lastIdx).trim();
      if (postText || lastIdx === 0) {
        renderAssistantBubble(postText || (lastIdx === 0 ? raw : ''), agentName);
      }
    }

    function renderAssistantBubble(text, agentName) {
      const feed = document.getElementById('chat-feed');
      if (!text) return;

      const row = document.createElement('div');
      row.className = 'flex justify-start my-2';
      const bubble = document.createElement('div');
      bubble.className = 'max-w-[85%] bg-black/40 border border-white/10 text-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 leading-relaxed';
      const tag = agentName ? `<div class="text-[10px] font-mono font-semibold text-emerald-400 mb-2 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>@${escapeHtml(agentName)}</div>` : '';

      let htmlBody = '';
      if (window.marked) {
        try {
          htmlBody = marked.parse(text);
        } catch(e) {
          htmlBody = `<div class="whitespace-pre-wrap">${escapeHtml(text)}</div>`;
        }
      } else {
        htmlBody = `<div class="whitespace-pre-wrap">${escapeHtml(text)}</div>`;
      }

      bubble.innerHTML = `${tag}<div class="prose prose-invert max-w-none text-xs leading-relaxed">${htmlBody}</div>`;
      bubble.querySelectorAll('pre code').forEach((el) => {
        if (window.hljs) hljs.highlightElement(el);
      });

      row.appendChild(bubble);
      feed.appendChild(row);
      feed.scrollTop = feed.scrollHeight;
    }

    function appendToolEvent(name, args, result) {
      const feed = document.getElementById('chat-feed');
      const card = document.createElement('div');
      card.className = 'my-2 p-3 rounded-xl bg-black/30 border border-white/5 font-mono text-[11px] max-w-[85%]';
      const argsStr = typeof args === 'object' ? JSON.stringify(args, null, 2) : String(args || '');
      const resultStr = result != null ? (typeof result === 'object' ? JSON.stringify(result, null, 2) : String(result)) : '';

      card.innerHTML = `
        <details class="cursor-pointer" open>
          <summary class="text-emerald-400 font-semibold flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span>⚙ Tool:</span> <span class="text-white font-bold">${escapeHtml(name)}</span>
            </div>
            ${resultStr ? '<span class="text-[10px] text-emerald-400 font-normal">✓ executed</span>' : '<span class="text-[10px] text-yellow-400/80 font-normal">calling...</span>'}
          </summary>
          <div class="mt-2 text-[10px] text-gray-400 font-semibold">Parameters:</div>
          <pre class="mt-1 p-2 rounded bg-black/50 text-gray-300 overflow-x-auto text-[10px] border border-white/5">${escapeHtml(argsStr)}</pre>
          ${resultStr ? `
            <div class="mt-2 text-[10px] text-emerald-400 font-semibold">Output Response:</div>
            <pre class="mt-1 p-2 rounded bg-black/70 text-emerald-300/90 overflow-x-auto text-[10px] border border-emerald-500/20 max-h-60 overflow-y-auto">${escapeHtml(resultStr)}</pre>
          ` : ''}
        </details>
      `;
      feed.appendChild(card);
      feed.scrollTop = feed.scrollHeight;
    }

    function appendThinkingEvent(text) {
      const feed = document.getElementById('chat-feed');
      const card = document.createElement('div');
      card.className = 'my-2 p-3 rounded-xl bg-blue-500/5 border border-blue-500/10 font-mono text-[11px] max-w-[85%] text-blue-300/80';
      card.innerHTML = `
        <details class="cursor-pointer" open>
          <summary class="font-semibold text-blue-400 flex items-center gap-1.5">
            <span>💭 Thinking Trace</span>
          </summary>
          <div class="mt-2 p-2 rounded bg-black/30 text-gray-300 whitespace-pre-wrap leading-relaxed border border-blue-500/10">${escapeHtml(text)}</div>
        </details>
      `;
      feed.appendChild(card);
      feed.scrollTop = feed.scrollHeight;
    }

    function escapeHtml(text) {
      return (text || '').toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function newSession() {
      currentSessionId = 'session_' + Math.random().toString(36).substring(2, 9);
      localStorage.setItem('sago_active_session', currentSessionId);
      document.getElementById('cur-session-label').textContent = currentSessionId;
      document.getElementById('session-title-display').textContent = 'New Session';
      clearChat();
      fetchSessions();
    }

    function loadSession(sid, title, wdir) {
      currentSessionId = sid;
      localStorage.setItem('sago_active_session', sid);
      document.getElementById('cur-session-label').textContent = sid;
      document.getElementById('session-title-display').textContent = title || 'Active Session';
      if (wdir) {
        document.getElementById('cur-workspace-label').textContent = wdir;
        document.getElementById('cur-workspace-label').title = wdir;
      }

      // Update UI active state
      document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
      const target = document.getElementById('sess-' + sid);
      if (target) target.classList.add('active');

      if (runningSessions.has(sid)) {
        document.getElementById('thinking-badge').classList.remove('hidden');
        document.getElementById('task-input').disabled = true;
        document.getElementById('send-btn').disabled = true;
      } else {
        document.getElementById('thinking-badge').classList.add('hidden');
        document.getElementById('task-input').disabled = false;
        document.getElementById('send-btn').disabled = false;
      }

      clearChat();

      fetch(`/api/sessions/${sid}/messages`)
        .then(r => r.json())
        .then(messages => {
          if (messages && messages.length > 0) {
            messages.forEach(m => {
              let meta = {};
              if (typeof m.metadata === 'string') {
                try { meta = JSON.parse(m.metadata); } catch(e) {}
              } else if (typeof m.metadata === 'object' && m.metadata !== null) {
                meta = m.metadata;
              }

              if (m.role === 'tool') {
                appendToolEvent(m.agent_name || 'tool', meta.args || m.content, meta.result || m.content);
              } else if (m.role === 'thinking') {
                appendThinkingEvent(m.content);
              } else {
                // If metadata explicitly has thinking text, render it before the message
                if (meta.thinking && typeof meta.thinking === 'string' && meta.thinking.trim()) {
                  appendThinkingEvent(meta.thinking.trim());
                }
                appendMessage(m.role, m.content, m.agent_name);
              }
            });
          }
        })
        .catch(err => console.debug("Failed to load messages", err));
    }

    function clearChat() {
      const feed = document.getElementById('chat-feed');
      document.getElementById('live-tool-strip').classList.add('hidden');
      feed.innerHTML = `
        <div id="empty-state" class="h-full flex flex-col items-center justify-center text-gray-500 space-y-2 py-12">
          <span class="text-2xl">💬</span>
          <p class="font-medium text-gray-400">Ready for questions or tasks</p>
          <p class="text-[11px] text-gray-600">Type below to run code, debug errors, or dispatch agents with @agent</p>
        </div>
      `;
    }

    function fetchSessions() {
      fetch('/api/sessions')
        .then(r => r.json())
        .then(data => {
          const sessions = Array.isArray(data) ? data : (data.sessions || []);
          const container = document.getElementById('sessions-container');
          if (!sessions || sessions.length === 0) {
            container.innerHTML = '<div class="text-gray-500 py-6 text-center">No active sessions found</div>';
            return;
          }
          container.innerHTML = sessions.map(s => {
            const wdir = s.working_dir || s.cwd || '';
            const wdirShort = wdir ? wdir.split('/').slice(-2).join('/') : '';
            const isRunning = runningSessions.has(s.id);
            return `
            <div id="sess-${s.id}" onclick="loadSession('${s.id}', '${(s.title || '').replace(/'/g, "\\'")}', '${wdir.replace(/'/g, "\\'")}')" class="session-item ${s.id === currentSessionId ? 'active' : ''} p-2.5 rounded-xl bg-black/20 border border-white/5 hover:border-emerald-500/30 transition cursor-pointer flex justify-between items-center group">
              <div class="truncate max-w-[190px]">
                <div class="font-medium text-gray-200 truncate flex items-center">
                  ${isRunning ? '<span class="status-running-badge px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[9px] font-mono animate-pulse mr-1">running</span>' : ''}
                  <span class="truncate">${s.title || 'Untitled Session'}</span>
                </div>
                <div class="text-[10px] text-gray-500 font-mono truncate">${s.id}</div>
                ${wdirShort ? `<div class="text-[9px] text-emerald-500/80 font-mono truncate" title="${wdir}">📁 ${wdirShort}</div>` : ''}
              </div>
              <button onclick="event.stopPropagation(); deleteSession('${s.id}')" class="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition px-1.5 py-0.5 text-xs">✕</button>
            </div>
          `;}).join('');
        })
        .catch(err => console.debug("Sync failed", err));
    }

    function insertCommand(cmd) {
      const input = document.getElementById('task-input');
      input.value = cmd;
      input.focus();
    }

    function openDiffModal() {
      const modal = document.getElementById('diff-modal');
      const container = document.getElementById('diff-content-container');
      const fileCount = document.getElementById('diff-file-count');
      modal.classList.remove('hidden');
      container.innerHTML = '<div class="text-gray-400 py-6 text-center">Loading git diff...</div>';

      fetch('/api/diff')
        .then(r => r.json())
        .then(data => {
          if (data.status === 'ok') {
            const files = data.changed_files || [];
            fileCount.textContent = files.length + ' files changed';
            if (!data.diff) {
              container.innerHTML = '<div class="text-emerald-400 font-bold py-6 text-center">✓ Clean workspace — No uncommitted changes</div>';
              return;
            }

            // GitHub-style colored diff lines
            const lines = data.diff.split('\\n');
            let diffHtml = '';
            lines.forEach(line => {
              if (line.startsWith('+++') || line.startsWith('---')) {
                diffHtml += `<div class="font-bold text-gray-400 bg-white/5 px-2 py-0.5">${escapeHtml(line)}</div>`;
              } else if (line.startsWith('+')) {
                diffHtml += `<div class="bg-emerald-500/15 text-emerald-300 border-l-2 border-emerald-500 px-2 py-0.5">${escapeHtml(line)}</div>`;
              } else if (line.startsWith('-')) {
                diffHtml += `<div class="bg-red-500/15 text-red-300 border-l-2 border-red-500 px-2 py-0.5">${escapeHtml(line)}</div>`;
              } else if (line.startsWith('@@')) {
                diffHtml += `<div class="text-blue-400 bg-blue-500/10 font-bold px-2 py-1 my-1">${escapeHtml(line)}</div>`;
              } else if (line.startsWith('diff --git')) {
                diffHtml += `<div class="text-yellow-400 font-bold bg-white/10 px-2 py-1.5 mt-3 rounded">${escapeHtml(line)}</div>`;
              } else {
                diffHtml += `<div class="text-gray-400 px-2 py-0.5">${escapeHtml(line)}</div>`;
              }
            });
            container.innerHTML = diffHtml;
          } else {
            container.innerHTML = '<div class="text-red-400 py-4">Error loading diff: ' + escapeHtml(data.message || 'Unknown') + '</div>';
          }
        })
        .catch(err => {
          container.innerHTML = '<div class="text-red-400 py-4">Failed to load diff: ' + err + '</div>';
        });
    }

    function closeDiffModal() {
      document.getElementById('diff-modal').classList.add('hidden');
    }

    function openFileViewerModal(filePath) {
      const modal = document.getElementById('file-viewer-modal');
      const codeEl = document.getElementById('file-viewer-code');
      const pathEl = document.getElementById('file-viewer-path');
      modal.classList.remove('hidden');
      pathEl.textContent = filePath;
      codeEl.textContent = 'Loading file contents...';

      fetch(`/api/files/content?path=${encodeURIComponent(filePath)}`)
        .then(r => r.json())
        .then(data => {
          if (data.status === 'ok') {
            codeEl.textContent = data.content;
            if (window.hljs) hljs.highlightElement(codeEl);
          } else {
            codeEl.textContent = 'Error loading file: ' + (data.message || 'Unknown');
          }
        })
        .catch(err => {
          codeEl.textContent = 'Failed to load file: ' + err;
        });
    }

    function closeFileViewerModal() {
      document.getElementById('file-viewer-modal').classList.add('hidden');
    }

    function newSessionModal() {
      document.getElementById('new-session-modal').classList.remove('hidden');
      fetch('/api/workspaces')
        .then(r => r.json())
        .then(data => {
          if (data.current) {
            document.getElementById('new-session-path').placeholder = data.current;
          }
        })
        .catch(() => {});
    }

    function closeNewSessionModal() {
      document.getElementById('new-session-modal').classList.add('hidden');
    }

    function confirmNewSession() {
      const title = document.getElementById('new-session-title').value.trim() || 'New Session';
      const path = document.getElementById('new-session-path').value.trim();

      currentSessionId = 'session_' + Math.random().toString(36).substring(2, 9);
      localStorage.setItem('sago_active_session', currentSessionId);
      document.getElementById('cur-session-label').textContent = currentSessionId;
      document.getElementById('session-title-display').textContent = title;
      if (path) {
        document.getElementById('cur-workspace-label').textContent = path;
        document.getElementById('cur-workspace-label').title = path;
      }

      fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: currentSessionId,
          title: title,
          workspace_cwd: path || document.getElementById('cur-workspace-label').textContent
        })
      })
      .then(() => fetchSessions())
      .catch(() => fetchSessions());

      closeNewSessionModal();
      clearChat();
    }

    function openFilesModal(path) {
      const modal = document.getElementById('files-modal');
      const list = document.getElementById('files-list');
      const curDir = document.getElementById('files-current-dir');
      modal.classList.remove('hidden');
      list.innerHTML = '<div class="text-gray-500 py-4">Loading directory files...</div>';

      const url = path ? `/api/files?path=${encodeURIComponent(path)}` : '/api/files';
      fetch(url)
        .then(r => r.json())
        .then(data => {
          if (data.status === 'ok') {
            curDir.textContent = data.current;
            let html = '';
            if (data.parent) {
              html += `<div onclick="openFilesModal('${data.parent.replace(/'/g, "\\'")}')" class="p-2 rounded hover:bg-white/5 cursor-pointer text-emerald-400 font-bold">📁 .. (Parent Directory)</div>`;
            }
            html += data.entries.map(e => `
              <div onclick="${e.is_dir ? `openFilesModal('${e.path.replace(/'/g, "\\'")}')` : `openFileViewerModal('${e.path.replace(/'/g, "\\'")}')`}" class="p-2 rounded hover:bg-white/5 cursor-pointer flex justify-between items-center ${e.is_dir ? 'text-blue-300 font-semibold' : 'text-gray-300'}">
                <span>${e.is_dir ? '📁' : '📄'} ${e.name}</span>
                <span class="text-[10px] text-gray-500 font-mono">${e.is_dir ? 'dir' : (e.size + ' B')}</span>
              </div>
            `).join('');
            list.innerHTML = html || '<div class="text-gray-500 py-4">Empty folder</div>';
          } else {
            list.innerHTML = `<div class="text-red-400 py-4">Error: ${data.message}</div>`;
          }
        })
        .catch(err => {
          list.innerHTML = `<div class="text-red-400 py-4">Failed to load files: ${err}</div>`;
        });
    }

    function closeFilesModal() {
      document.getElementById('files-modal').classList.add('hidden');
    }

    function openTracesModal() {
      const modal = document.getElementById('traces-modal');
      const list = document.getElementById('traces-list');
      modal.classList.remove('hidden');
      list.innerHTML = '<div class="text-gray-500 py-4">Loading execution traces...</div>';

      fetch(`/api/traces?session_id=${encodeURIComponent(currentSessionId)}`)
        .then(r => r.json())
        .then(traces => {
          if (traces && traces.length > 0) {
            list.innerHTML = traces.map(t => `
              <div class="p-3 rounded-xl bg-black/30 border border-white/5">
                <div class="flex justify-between items-center text-xs">
                  <span class="text-emerald-400 font-bold">⚡ ${t.tool_name || 'Tool Span'}</span>
                  <span class="text-[10px] text-gray-500 font-mono">${t.created_at || ''}</span>
                </div>
                <pre class="mt-1 p-2 rounded bg-black/50 text-[10px] text-gray-300 overflow-x-auto">${escapeHtml(typeof t.args === 'object' ? JSON.stringify(t.args, null, 2) : String(t.args || ''))}</pre>
              </div>
            `).join('');
          } else {
            list.innerHTML = '<div class="text-gray-500 py-6 text-center">No active tool traces recorded in this session yet.</div>';
          }
        })
        .catch(err => {
          list.innerHTML = `<div class="text-red-400 py-4">Failed to load traces: ${err}</div>`;
        });
    }

    function closeTracesModal() {
      document.getElementById('traces-modal').classList.add('hidden');
    }

    function closeAllModals() {
      closeDiffModal();
      closeFilesModal();
      closeFileViewerModal();
      closeTracesModal();
      closeNewSessionModal();
      hideAutocomplete();
    }

    function hideAutocomplete() {
      document.getElementById('autocomplete-popup').classList.add('hidden');
    }

    function handleAutocomplete(text) {
      const popup = document.getElementById('autocomplete-popup');
      if (!text) {
        hideAutocomplete();
        return;
      }

      // Check if text starts with / or contains @ or # anywhere in the current word
      const cursorText = text;
      const lastToken = cursorText.split(/\\s+/).pop() || '';

      if (!lastToken.startsWith('/') && !lastToken.startsWith('@') && !lastToken.startsWith('#')) {
        hideAutocomplete();
        return;
      }

      fetch(`/api/suggest?q=${encodeURIComponent(lastToken)}`)
        .then(r => r.json())
        .then(items => {
          if (!items || items.length === 0) {
            hideAutocomplete();
            return;
          }
          popup.classList.remove('hidden');
          popup.innerHTML = items.map(item => `
            <div onclick="applySuggestion('${item.val.replace(/'/g, "\\'")}', '${lastToken.replace(/'/g, "\\'")}')" class="p-1.5 rounded hover:bg-emerald-500/20 cursor-pointer flex justify-between items-center text-xs">
              <span class="text-emerald-400 font-bold">${escapeHtml(item.val)}</span>
              <span class="text-gray-400 text-[10px]">${escapeHtml(item.desc || '')}</span>
            </div>
          `).join('');
        })
        .catch(() => hideAutocomplete());
    }

    function handlePathSuggestions(val) {
      const datalist = document.getElementById('workspace-path-suggestions');
      if (!datalist) return;

      fetch(`/api/fs/suggest?path=${encodeURIComponent(val)}`)
        .then(r => r.json())
        .then(dirs => {
          if (dirs && dirs.length > 0) {
            datalist.innerHTML = dirs.map(d => `<option value="${escapeHtml(d.val)}"></option>`).join('');
          }
        })
        .catch(() => {});
    }

    function applySuggestion(val, lastToken) {
      const input = document.getElementById('task-input');
      const cur = input.value;
      const idx = cur.lastIndexOf(lastToken);
      if (idx !== -1) {
        input.value = cur.substring(0, idx) + val;
      } else {
        input.value += val;
      }
      input.focus();
      hideAutocomplete();
    }

    function deleteSession(sid) {
      fetch(`/api/sessions/${sid}`, { method: 'DELETE' })
        .then(() => {
          if (sid === currentSessionId) {
            newSession();
          } else {
            fetchSessions();
          }
        });
    }

    // Keyboard support: Enter, Shift+Enter, F2 Traces, F3 Diff, F4 Files, Esc to close
    document.addEventListener('DOMContentLoaded', () => {
      const input = document.getElementById('task-input');
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          hideAutocomplete();
          sendMessage();
        } else if (e.key === 'Escape') {
          hideAutocomplete();
        }
      });

      input.addEventListener('input', (e) => {
        handleAutocomplete(e.target.value);
      });

      const pathInput = document.getElementById('new-session-path');
      if (pathInput) {
        pathInput.addEventListener('input', (e) => {
          handlePathSuggestions(e.target.value);
        });
      }

      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          closeAllModals();
        } else if (e.key === 'F2') {
          e.preventDefault();
          openTracesModal();
        } else if (e.key === 'F3') {
          e.preventDefault();
          openDiffModal();
        } else if (e.key === 'F4') {
          e.preventDefault();
          openFilesModal();
        }
      });

      document.getElementById('cur-session-label').textContent = currentSessionId;
      initWebSocket();
      fetchSessions();
      setInterval(fetchSessions, 10000);
    });
  </script>
</body>
</html>
"""

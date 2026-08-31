"""TUI CSS Styles and Themes definition."""

TUI_CSS = """
/* ── Screen ────────────────────────────────────────────────────────────── */
Screen { background: #0a0d12; }

#main-layout { height: 1fr; }

#messages-parent {
    width: 1fr;
    height: 1fr;
    min-width: 30;
}

/* ── Agent Dashboard ───────────────────────────────────────────────────── */
#agent-dashboard {
    width: 30;
    min-width: 24;
    max-width: 40;
    height: 1fr;
    background: #111418;
    border-left: solid #21262d;
    padding: 0 1;
    overflow-y: auto;
    scrollbar-size: 1 1;
    scrollbar-color: #388bfd #161b22;
}
#agent-dashboard.hidden { display: none; }

.dashboard-title { color: #58a6ff; text-style: bold; padding: 0; content-align: center middle; }
.agent-entry { background: #161b22; border: solid #21262d; padding: 0 1; margin: 0 0 1 0; }
.agent-name { text-style: bold; }
.agent-status { color: #8b949e; padding: 0 0 0 1; }
.agent-task { color: #8b949e; text-style: italic; padding: 0; }
.agent-tools { color: #58a6ff; padding: 0; }
.agent-progress { padding: 0; color: #3fb950; }
.dashboard-separator { color: #21262d; padding: 0; }
.dashboard-stats { color: #8b949e; }
.active-color { color: #3fb950; }
.idle-color { color: #8b949e; }
.error-color { color: #f85149; }
.completed-color { color: #58a6ff; }

/* ── Messages ──────────────────────────────────────────────────────────── */
#messages {
    height: 1fr;
    padding: 1 1;
    overflow-y: scroll;
    overflow-x: hidden;
    scrollbar-size: 1 1;
    scrollbar-color: #388bfd #161b22;
    scrollbar-color-hover: #79c0ff #161b22;
    scrollbar-gutter: stable;
}

#new-messages-badge {
    display: none; dock: bottom; width: 100%; height: 1;
    background: #1f6feb; color: #ffffff; text-align: center; text-style: bold;
    padding: 0 1; margin: 0; align: center middle; content-align: center middle;
}
#new-messages-badge.visible { display: block; }
#new-messages-badge.hidden { display: none; }

.msg-user { background: transparent; border: none; border-left: solid #388bfd; color: #58a6ff; padding: 0 1; margin: 0; }
.msg-assistant { background: transparent; border: none; color: #e6edf3; padding: 0; margin: 0; }
.msg-system { background: transparent; color: #e3b341; padding: 0 1; margin: 0; border: none; }
.msg-error-inline { background: transparent; color: #f85149; padding: 0 1; margin: 1 0 0 0; border: none; border-left: solid #f85149; }
.msg-notice-inline { background: transparent; color: #e3b341; padding: 0 1; margin: 1 0 0 0; border: none; border-left: solid #e3b341; }
.msg-meta { color: #6e7681; padding: 0; }
.msg-parallel { background: transparent; color: #d2a8ff; border: none; border-left: solid #d2a8ff; padding: 0 1; margin: 1 0; }

/* ── Exchange Cards ────────────────────────────────────────────────────── */
.exchange-box { background: transparent; border: solid #30363d; padding: 0; margin: 1 0; height: auto; }
.exchange-box--user { border-left: solid #388bfd; }
.exchange-box--delegate { border-left: solid #8957e5; }
.exchange-box--chain { border-left: solid #1f6feb; }
.exchange-box--orchestrate { border-left: solid #2ea043; }
.exchange-box--plan { border-left: solid #d29922; }
.exchange-box--command { border-left: solid #58a6ff; }

.exchange-prompt-header { background: transparent; color: #c9d1d9; padding: 0 1; border-bottom: solid #30363d; }
.exchange-user-prompt-header { background: transparent; padding: 0; height: auto; min-height: 0; }
.exchange-user-prompt { background: transparent; padding: 0; height: auto; min-height: 0; }
.exchange-body { background: transparent; padding: 0 1; height: auto; min-height: 0; color: #e6edf3; }
.exchange-divider { color: #30363d; padding: 0; margin: 0; height: auto; min-height: 0; }
.exchange-response { background: transparent; padding: 0; height: auto; min-height: 0; }
.exchange-prompt { color: #58a6ff; text-style: bold; padding: 0; border-bottom: solid #30363d; }
.exchange-assistant { color: #e6edf3; background: transparent; padding: 0; }
.markdown-body { background: transparent; padding: 0; margin: 0; }
.agent-tag { color: #58a6ff; text-style: bold; padding: 0; margin: 0; }
.thinking-text { color: #8b949e; text-style: italic; padding: 0 1; background: transparent; border: none; border-left: solid #6e40c9; margin: 1 0; }
.trace-badge { color: #484f58; padding: 0 1; margin: 0; width: 1fr; content-align: left middle; height: 1; }
.trace-action-bar { height: 1; margin: 0; padding: 0; background: #0d1117; border-top: solid #21262d; }
.btn-view-trace { height: 1; min-width: 12; border: none; background: #161b22; color: #388bfd; padding: 0 1; }
.btn-view-trace:hover { background: #1c2a3d; color: #58a6ff; }
.btn-view-trace:focus { background: #1c2a3d; color: #58a6ff; border: none; }

.plan-text { color: #7ee787; padding: 0 1; background: transparent; border: none; border-left: solid #2ea043; margin: 1 0; }

/* ── Collapsible Cards ─────────────────────────────────────────────────── */
.collapsible-card-box { background: transparent; border: solid #30363d; padding: 0; margin: 1 0; height: auto; max-height: 30; overflow-y: auto; color: #e6edf3; }
.card-header { background: transparent; color: #c9d1d9; padding: 0 1; border-bottom: solid #30363d; }
.card-body { padding: 1 1; height: auto; max-height: 28; overflow-y: auto; color: #e6edf3; }

Collapsible { background: #0d1117; border: solid #21262d; margin: 1 0; padding: 0; height: auto; }
Collapsible .collapsible-title { background: #0d1117; color: #58a6ff; padding: 0 1; text-style: bold; }
Collapsible .collapsible-body { background: #0d1117; color: #e6edf3; padding: 1 1; overflow-y: auto; scrollbar-size: 1 1; scrollbar-color: #388bfd #161b22; }

.exchange-body Collapsible { margin: 1 0 0 0; padding: 0; }
.exchange-body Collapsible > Contents { padding: 0 1; }

/* ── Code Actions ──────────────────────────────────────────────────────── */
.code-action-bar { height: 1; margin: 1 0 0 0; padding: 0; }
.spacer { width: 1fr; }
.btn-copy-code { min-width: 12; height: 1; background: #161b22; color: #8b949e; border: none; padding: 0 1; }
.btn-copy-code:focus, .btn-copy-code:hover { background: #1c2a3d; color: #58a6ff; }

/* ── Input Area ────────────────────────────────────────────────────────── */
#input-area { height: auto; padding: 0 1 1 1; background: #0a0d12; border-top: solid #21262d; margin: 0; }
#msg-input { background: #0a0d12; border: none; border-top: solid #21262d; color: #c9d1d9; margin: 0; padding: 0 1; width: 1fr; }
#msg-input:focus { border: none; border-top: solid #388bfd; color: #ffffff; background: #0a0d12; }

#input-action-bar { height: auto; max-height: 2; margin: 1 0 0 0; overflow-x: auto; overflow-y: hidden; }
.hide-action-bar #input-action-bar { display: none; }
.btn-input-action { height: 1; min-width: 6; border: none; background: #161b22; color: #8b949e; margin-right: 0; padding: 0 0 0 1; }
.btn-input-action:hover { background: #1c2333; color: #e6edf3; }
.btn-input-action:focus { background: #1c2333; color: #e6edf3; border: none; }
.btn-action-traces { color: #58a6ff; text-style: bold; }
.btn-action-traces:hover { background: #1c2a3d; color: #79c0ff; }
.btn-action-traces:focus { background: #1c2a3d; color: #79c0ff; border: none; }
.dev-only-btn { display: none; }
.dev-mode-enabled .dev-only-btn { display: block; }

.btn-action-cancel { display: none; color: #f85149; }
.is-thinking .btn-action-cancel { display: block; }
.btn-action-cancel:hover { background: #2d1520; color: #f85149; }
.btn-action-cancel:focus { background: #2d1520; color: #f85149; border: none; }

.btn-action-exit { color: #8b949e; }
.btn-action-exit:hover { background: #2d1520; color: #f85149; }
.btn-action-exit:focus { background: #2d1520; color: #f85149; border: none; }

/* ── Suggestions ───────────────────────────────────────────────────────── */
#suggestions { display: none; height: auto; max-height: 12; overflow-y: scroll; background: #0a0d12; border: none; border-top: solid #21262d; margin: 0; padding: 0 1; scrollbar-size-vertical: 1; scrollbar-color: #388bfd #161b22; }
#suggestions.visible { display: block; }
.suggestion-item { color: #8b949e; padding: 0 1; }
.suggestion-item.highlighted { color: #ffffff; background: #1f6feb; text-style: bold; }

/* ── Code Blocks / Shell ───────────────────────────────────────────────── */
.code-block { background: #161b22; color: #c9d1d9; padding: 1; margin: 0 0 1 0; border: tall #30363d; }
Markdown > .code-block, Markdown Horizontal > .code-block, .exchange-body .code-block { background: #161b22; color: #c9d1d9; }

.shell-escape-card { background: #0d1117; border: solid #21262d; padding: 0; margin: 0 0 1 0; height: auto; max-height: 20; overflow-y: auto; }
.shell-card-header { background: #161b22; color: #c9d1d9; padding: 0 1; text-style: bold; border-bottom: solid #21262d; }
.shell-card-body { padding: 1 1; height: auto; max-height: 18; overflow-y: auto; }
.shell-output-text { color: #c9d1d9; text-style: none; }

/* ── Misc ──────────────────────────────────────────────────────────────── */
.spinner { color: #58a6ff; text-style: italic; padding: 0 0 1 0; }
.summary-box { background: #161b22; border: solid #1f6feb; color: #c9d1d9; padding: 1; margin: 0 0 1 0; }
.dev-trace-text { color: #79c0ff; padding: 1 1; background: #06090e; border: solid #21262d; border-left: solid #f85149; margin: 1 0; }

/* ── Welcome Screen ────────────────────────────────────────────────────── */
#welcome-screen { height: 1fr; align: center middle; content-align: center middle; text-align: center; background: #0d1117; }
#welcome-screen.hidden { display: none; }
#messages-parent.has-welcome #messages { display: none; }
.welcome-logo { color: #58a6ff; text-style: bold; text-align: center; width: 100%; height: auto; }
.welcome-version { color: #ffffff; text-style: bold; text-align: center; width: 100%; height: 1; margin: 1 0 0 0; }
.welcome-dev-badge { text-align: center; width: 100%; height: 1; margin: 1 0 0 0; }
.welcome-workspace-badge { text-align: center; width: 100%; height: 1; margin: 1 0 0 0; }
.welcome-subtitle { color: #8b949e; text-align: center; width: 100%; height: 1; margin: 0; }
.welcome-hint { color: #484f58; text-align: center; width: 100%; height: 1; margin: 2 0 0 0; }
.welcome-separator { color: #30363d; text-align: center; width: 100%; height: 1; margin: 1 0 0 0; }
.prompt-enhancement-inline { width: 100%; height: auto; padding: 0 1; margin: 0 0 1 0; }

/* ── Approval / Parallel Bars ──────────────────────────────────────────── */
#approval-bar { display: none; height: auto; max-height: 4; overflow-y: auto; background: transparent; border: none; border-left: solid #f0883e; margin: 0 1 0 1; padding: 0 1; }
#approval-bar.visible { display: block; }
#approval-bar .approval-label { color: #f0883e; text-style: bold; padding: 0; max-height: 2; overflow-y: auto; }
#approval-bar .approval-buttons { layout: horizontal; height: 1; }
#approval-bar Button { margin: 0 1 0 0; min-width: 8; max-height: 1; }
.approve-btn { background: transparent; color: #3fb950; border: none; text-style: bold; }
.approve-btn:hover { background: #1a3a2a; }
.approve-btn:focus { border: none; background: #1a3a2a; }
.deny-btn { background: transparent; color: #f85149; border: none; text-style: bold; }
.deny-btn:hover { background: #2d1520; }
.deny-btn:focus { border: none; background: #2d1520; }

#parallel-bar { display: none; height: auto; max-height: 10; overflow-y: auto; background: #161b22; border: solid #d2a8ff; margin: 0 1 0 1; padding: 1; }
#parallel-bar.visible { display: block; }
#parallel-bar .parallel-title { color: #d2a8ff; text-style: bold; padding: 0 0 1 0; }
#parallel-bar .parallel-agent { padding: 0 0 0 1; }

/* ── Modal Screens (obsidian defaults) ─────────────────────────────────── */
#diff-dialog, #file-dialog, #session-dialog, #shortcuts-dialog, .tv-box { background: #0d1117; border: solid #21262d; }
#diff-dialog, #file-dialog { border-top: solid #58a6ff; }
#session-dialog { border-top: solid #8957e5; }
#shortcuts-dialog, .tv-box { border-top: solid #58a6ff; }
#diff-header, #file-header, #session-header, .tv-header { border-bottom: solid #21262d; }
#diff-title, #file-title { color: #58a6ff; }
#session-title { color: #8957e5; }
.tv-title { color: #58a6ff; }
#diff-options, #session-options, DirectoryTree { background: #0d1117; }
#tree-container { border-right: solid #1c2128; }
#preview-container { scrollbar-color: #388bfd #161b22; }
#file-preview { color: #c9d1d9; }
#diff-file-list, #session-list-col { border-right: solid #21262d; }
.shortcuts-header { color: #58a6ff; border-bottom: solid #21262d; }

/* ═══════════════════════════════════════════════════════════════════════════
   THEMES — full overrides for every color-using selector
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Nord ──────────────────────────────────────────────────────────────── */
.theme-nord { background: #242933; }
.theme-nord #agent-dashboard { background: #2e3440; border-left: solid #434c5e; }
.theme-nord .dashboard-title { color: #88c0d0; }
.theme-nord .agent-entry { background: #2e3440; border: solid #434c5e; }
.theme-nord .agent-status { color: #a0a8b8; }
.theme-nord .agent-task { color: #a0a8b8; }
.theme-nord .agent-tools { color: #88c0d0; }
.theme-nord .agent-progress { color: #a3be8c; }
.theme-nord .dashboard-separator { color: #434c5e; }
.theme-nord .dashboard-stats { color: #a0a8b8; }
.theme-nord .active-color { color: #a3be8c; }
.theme-nord .idle-color { color: #a0a8b8; }
.theme-nord .error-color { color: #bf616a; }
.theme-nord .completed-color { color: #88c0d0; }

.theme-nord #messages { scrollbar-color: #88c0d0 #2e3440; scrollbar-color-hover: #8fbcbb #2e3440; }
.theme-nord #new-messages-badge { background: #5e81ac; }
.theme-nord .msg-user { border-left: solid #88c0d0; color: #88c0d0; }
.theme-nord .msg-assistant { color: #eceff4; }
.theme-nord .msg-system { color: #ebcb8b; border-left: solid #ebcb8b; }
.theme-nord .msg-error-inline { color: #bf616a; border-left: solid #bf616a; }
.theme-nord .msg-notice-inline { color: #ebcb8b; border-left: solid #ebcb8b; }
.theme-nord .msg-meta { color: #7b88a1; }
.theme-nord .msg-parallel { color: #b48ead; border-left: solid #b48ead; }

.theme-nord .exchange-box { border: solid #434c5e; }
.theme-nord .exchange-box--user { border-left: solid #88c0d0; }
.theme-nord .exchange-box--delegate { border-left: solid #b48ead; }
.theme-nord .exchange-box--chain { border-left: solid #5e81ac; }
.theme-nord .exchange-box--orchestrate { border-left: solid #a3be8c; }
.theme-nord .exchange-box--plan { border-left: #ebcb8b; }
.theme-nord .exchange-box--command { border-left: solid #88c0d0; }
.theme-nord .exchange-prompt-header { color: #d8dee9; border-bottom: solid #434c5e; }
.theme-nord .exchange-body { color: #eceff4; }
.theme-nord .exchange-divider { color: #434c5e; }
.theme-nord .exchange-prompt { color: #88c0d0; border-bottom: solid #434c5e; }
.theme-nord .exchange-assistant { color: #eceff4; }
.theme-nord .agent-tag { color: #88c0d0; }
.theme-nord .thinking-text { color: #a0a8b8; border-left: solid #b48ead; }
.theme-nord .trace-badge { color: #5e6b7e; }
.theme-nord .trace-action-bar { background: #2e3440; border-top: solid #434c5e; }
.theme-nord .btn-view-trace { background: #2e3440; color: #88c0d0; }
.theme-nord .btn-view-trace:hover { background: #3b4252; color: #8fbcbb; }
.theme-nord .btn-view-trace:focus { background: #3b4252; color: #8fbcbb; }
.theme-nord .plan-text { color: #a3be8c; border-left: solid #a3be8c; }

.theme-nord .collapsible-card-box { border: solid #434c5e; color: #eceff4; }
.theme-nord .card-header { color: #d8dee9; border-bottom: solid #434c5e; }
.theme-nord .card-body { color: #eceff4; }
.theme-nord Collapsible { background: #2e3440; border: solid #434c5e; }
.theme-nord Collapsible .collapsible-title { background: #2e3440; color: #88c0d0; }
.theme-nord Collapsible .collapsible-body { background: #2e3440; color: #eceff4; scrollbar-color: #88c0d0 #2e3440; }

.theme-nord .btn-copy-code { background: #2e3440; color: #a0a8b8; }
.theme-nord .btn-copy-code:hover { background: #3b4252; color: #88c0d0; }
.theme-nord .btn-copy-code:focus { background: #3b4252; color: #88c0d0; }

.theme-nord #input-area { background: #242933; border-top: solid #434c5e; }
.theme-nord #msg-input { background: #242933; border-top: solid #434c5e; color: #d8dee9; }
.theme-nord #msg-input:focus { border-top: solid #88c0d0; color: #eceff4; background: #242933; }
.theme-nord .btn-input-action { background: #2e3440; color: #a0a8b8; }
.theme-nord .btn-input-action:hover { background: #3b4252; color: #eceff4; }
.theme-nord .btn-input-action:focus { background: #3b4252; color: #eceff4; }
.theme-nord .btn-action-traces { color: #88c0d0; }
.theme-nord .btn-action-traces:hover { background: #3b4252; color: #8fbcbb; }
.theme-nord .btn-action-traces:focus { background: #3b4252; color: #8fbcbb; }
.theme-nord .btn-action-cancel:hover { background: #3b2430; color: #bf616a; }
.theme-nord .btn-action-cancel:focus { background: #3b2430; }
.theme-nord .btn-action-exit { color: #a0a8b8; }
.theme-nord .btn-action-exit:hover { background: #3b2430; color: #bf616a; }

.theme-nord #suggestions { background: #242933; border-top: solid #434c5e; scrollbar-color: #88c0d0 #2e3440; }
.theme-nord .suggestion-item { color: #a0a8b8; }
.theme-nord .suggestion-item.highlighted { color: #eceff4; background: #5e81ac; }

.theme-nord .code-block { background: #2e3440; color: #d8dee9; border: tall #434c5e; }
.theme-nord .shell-escape-card { background: #2e3440; border: solid #434c5e; }
.theme-nord .shell-card-header { background: #3b4252; color: #d8dee9; border-bottom: solid #434c5e; }
.theme-nord .shell-output-text { color: #d8dee9; }
.theme-nord .spinner { color: #88c0d0; }
.theme-nord .summary-box { background: #2e3440; border: solid #5e81ac; color: #d8dee9; }
.theme-nord .dev-trace-text { color: #8fbcbb; background: #242933; border: solid #434c5e; border-left: solid #bf616a; }
.theme-nord #welcome-screen { background: #2e3440; }
.theme-nord .welcome-logo { color: #88c0d0; }
.theme-nord .welcome-version { color: #eceff4; }
.theme-nord .welcome-subtitle { color: #a0a8b8; }
.theme-nord .welcome-hint { color: #5e6b7e; }
.theme-nord .welcome-separator { color: #434c5e; }
.theme-nord #approval-bar { border-left: solid #ebcb8b; }
.theme-nord #approval-bar .approval-label { color: #ebcb8b; }
.theme-nord .approve-btn { color: #a3be8c; }
.theme-nord .approve-btn:hover { background: #2a3a2a; }
.theme-nord .approve-btn:focus { background: #2a3a2a; }
.theme-nord .deny-btn { color: #bf616a; }
.theme-nord .deny-btn:hover { background: #3b2430; }
.theme-nord .deny-btn:focus { background: #3b2430; }
.theme-nord #parallel-bar { background: #2e3440; border: solid #b48ead; }
.theme-nord #parallel-bar .parallel-title { color: #b48ead; }

.theme-nord #diff-dialog, .theme-nord #file-dialog, .theme-nord #session-dialog, .theme-nord #shortcuts-dialog, .theme-nord .tv-box { background: #2e3440; border: solid #434c5e; }
.theme-nord #diff-dialog, .theme-nord #file-dialog { border-top: solid #88c0d0; }
.theme-nord #session-dialog { border-top: solid #b48ead; }
.theme-nord #shortcuts-dialog, .theme-nord .tv-box { border-top: solid #88c0d0; }
.theme-nord #diff-header, .theme-nord #file-header, .theme-nord #session-header, .theme-nord .tv-header { border-bottom: solid #434c5e; }
.theme-nord #diff-title, .theme-nord #file-title { color: #88c0d0; }
.theme-nord #session-title { color: #b48ead; }
.theme-nord .tv-title { color: #88c0d0; }
.theme-nord #diff-options, .theme-nord #session-options, .theme-nord DirectoryTree { background: #2e3440; }
.theme-nord #tree-container { border-right: solid #434c5e; }
.theme-nord #preview-container { scrollbar-color: #88c0d0 #2e3440; }
.theme-nord #file-preview { color: #d8dee9; }
.theme-nord #diff-file-list, .theme-nord #session-list-col { border-right: solid #434c5e; }
.theme-nord .shortcuts-header { color: #88c0d0; border-bottom: solid #434c5e; }

/* ── Dracula ───────────────────────────────────────────────────────────── */
.theme-dracula { background: #1e1f29; }
.theme-dracula #agent-dashboard { background: #282a36; border-left: solid #44475a; }
.theme-dracula .dashboard-title { color: #bd93f9; }
.theme-dracula .agent-entry { background: #282a36; border: solid #44475a; }
.theme-dracula .agent-status { color: #6272a4; }
.theme-dracula .agent-task { color: #6272a4; }
.theme-dracula .agent-tools { color: #bd93f9; }
.theme-dracula .agent-progress { color: #50fa7b; }
.theme-dracula .dashboard-separator { color: #44475a; }
.theme-dracula .dashboard-stats { color: #6272a4; }
.theme-dracula .active-color { color: #50fa7b; }
.theme-dracula .idle-color { color: #6272a4; }
.theme-dracula .error-color { color: #ff5555; }
.theme-dracula .completed-color { color: #bd93f9; }

.theme-dracula #messages { scrollbar-color: #bd93f9 #282a36; scrollbar-color-hover: #ff79c6 #282a36; }
.theme-dracula #new-messages-badge { background: #6272a4; }
.theme-dracula .msg-user { border-left: solid #bd93f9; color: #bd93f9; }
.theme-dracula .msg-assistant { color: #f8f8f2; }
.theme-dracula .msg-system { color: #f1fa8c; border-left: solid #f1fa8c; }
.theme-dracula .msg-error-inline { color: #ff5555; border-left: solid #ff5555; }
.theme-dracula .msg-notice-inline { color: #f1fa8c; border-left: solid #f1fa8c; }
.theme-dracula .msg-meta { color: #5a5e7a; }
.theme-dracula .msg-parallel { color: #bd93f9; border-left: solid #bd93f9; }

.theme-dracula .exchange-box { border: solid #44475a; }
.theme-dracula .exchange-box--user { border-left: solid #bd93f9; }
.theme-dracula .exchange-box--delegate { border-left: solid #bd93f9; }
.theme-dracula .exchange-box--chain { border-left: solid #6272a4; }
.theme-dracula .exchange-box--orchestrate { border-left: solid #50fa7b; }
.theme-dracula .exchange-box--plan { border-left: #f1fa8c; }
.theme-dracula .exchange-box--command { border-left: solid #bd93f9; }
.theme-dracula .exchange-prompt-header { color: #f8f8f2; border-bottom: solid #44475a; }
.theme-dracula .exchange-body { color: #f8f8f2; }
.theme-dracula .exchange-divider { color: #44475a; }
.theme-dracula .exchange-prompt { color: #bd93f9; border-bottom: solid #44475a; }
.theme-dracula .exchange-assistant { color: #f8f8f2; }
.theme-dracula .agent-tag { color: #bd93f9; }
.theme-dracula .thinking-text { color: #6272a4; border-left: solid #6272a4; }
.theme-dracula .trace-badge { color: #44475a; }
.theme-dracula .trace-action-bar { background: #282a36; border-top: solid #44475a; }
.theme-dracula .btn-view-trace { background: #282a36; color: #bd93f9; }
.theme-dracula .btn-view-trace:hover { background: #343746; color: #ff79c6; }
.theme-dracula .btn-view-trace:focus { background: #343746; color: #ff79c6; }
.theme-dracula .plan-text { color: #50fa7b; border-left: solid #50fa7b; }

.theme-dracula .collapsible-card-box { border: solid #44475a; color: #f8f8f2; }
.theme-dracula .card-header { color: #f8f8f2; border-bottom: solid #44475a; }
.theme-dracula .card-body { color: #f8f8f2; }
.theme-dracula Collapsible { background: #282a36; border: solid #44475a; }
.theme-dracula Collapsible .collapsible-title { background: #282a36; color: #bd93f9; }
.theme-dracula Collapsible .collapsible-body { background: #282a36; color: #f8f8f2; scrollbar-color: #bd93f9 #282a36; }

.theme-dracula .btn-copy-code { background: #282a36; color: #6272a4; }
.theme-dracula .btn-copy-code:hover { background: #343746; color: #bd93f9; }
.theme-dracula .btn-copy-code:focus { background: #343746; color: #bd93f9; }

.theme-dracula #input-area { background: #1e1f29; border-top: solid #44475a; }
.theme-dracula #msg-input { background: #1e1f29; border-top: solid #44475a; color: #f8f8f2; }
.theme-dracula #msg-input:focus { border-top: solid #bd93f9; color: #ffffff; background: #1e1f29; }
.theme-dracula .btn-input-action { background: #282a36; color: #6272a4; }
.theme-dracula .btn-input-action:hover { background: #343746; color: #f8f8f2; }
.theme-dracula .btn-input-action:focus { background: #343746; color: #f8f8f2; }
.theme-dracula .btn-action-traces { color: #bd93f9; }
.theme-dracula .btn-action-traces:hover { background: #343746; color: #ff79c6; }
.theme-dracula .btn-action-traces:focus { background: #343746; color: #ff79c6; }
.theme-dracula .btn-action-cancel:hover { background: #3d2030; color: #ff5555; }
.theme-dracula .btn-action-cancel:focus { background: #3d2030; }
.theme-dracula .btn-action-exit { color: #6272a4; }
.theme-dracula .btn-action-exit:hover { background: #3d2030; color: #ff5555; }

.theme-dracula #suggestions { background: #1e1f29; border-top: solid #44475a; scrollbar-color: #bd93f9 #282a36; }
.theme-dracula .suggestion-item { color: #6272a4; }
.theme-dracula .suggestion-item.highlighted { color: #ffffff; background: #6272a4; }

.theme-dracula .code-block { background: #282a36; color: #f8f8f2; border: tall #44475a; }
.theme-dracula .shell-escape-card { background: #282a36; border: solid #44475a; }
.theme-dracula .shell-card-header { background: #343746; color: #f8f8f2; border-bottom: solid #44475a; }
.theme-dracula .shell-output-text { color: #f8f8f2; }
.theme-dracula .spinner { color: #bd93f9; }
.theme-dracula .summary-box { background: #282a36; border: solid #6272a4; color: #f8f8f2; }
.theme-dracula .dev-trace-text { color: #8be9fd; background: #1e1f29; border: solid #44475a; border-left: solid #ff5555; }
.theme-dracula #welcome-screen { background: #282a36; }
.theme-dracula .welcome-logo { color: #bd93f9; }
.theme-dracula .welcome-version { color: #f8f8f2; }
.theme-dracula .welcome-subtitle { color: #6272a4; }
.theme-dracula .welcome-hint { color: #44475a; }
.theme-dracula .welcome-separator { color: #44475a; }
.theme-dracula #approval-bar { border-left: solid #ffb86c; }
.theme-dracula #approval-bar .approval-label { color: #ffb86c; }
.theme-dracula .approve-btn { color: #50fa7b; }
.theme-dracula .approve-btn:hover { background: #1a3a2a; }
.theme-dracula .approve-btn:focus { background: #1a3a2a; }
.theme-dracula .deny-btn { color: #ff5555; }
.theme-dracula .deny-btn:hover { background: #3d2030; }
.theme-dracula .deny-btn:focus { background: #3d2030; }
.theme-dracula #parallel-bar { background: #282a36; border: solid #bd93f9; }
.theme-dracula #parallel-bar .parallel-title { color: #bd93f9; }

.theme-dracula #diff-dialog, .theme-dracula #file-dialog, .theme-dracula #session-dialog, .theme-dracula #shortcuts-dialog, .theme-dracula .tv-box { background: #282a36; border: solid #44475a; }
.theme-dracula #diff-dialog, .theme-dracula #file-dialog { border-top: solid #bd93f9; }
.theme-dracula #session-dialog { border-top: solid #ff79c6; }
.theme-dracula #shortcuts-dialog, .theme-dracula .tv-box { border-top: solid #bd93f9; }
.theme-dracula #diff-header, .theme-dracula #file-header, .theme-dracula #session-header, .theme-dracula .tv-header { border-bottom: solid #44475a; }
.theme-dracula #diff-title, .theme-dracula #file-title { color: #bd93f9; }
.theme-dracula #session-title { color: #ff79c6; }
.theme-dracula .tv-title { color: #bd93f9; }
.theme-dracula #diff-options, .theme-dracula #session-options, .theme-dracula DirectoryTree { background: #282a36; }
.theme-dracula #tree-container { border-right: solid #44475a; }
.theme-dracula #preview-container { scrollbar-color: #bd93f9 #282a36; }
.theme-dracula #file-preview { color: #f8f8f2; }
.theme-dracula #diff-file-list, .theme-dracula #session-list-col { border-right: solid #44475a; }
.theme-dracula .shortcuts-header { color: #bd93f9; border-bottom: solid #44475a; }

/* ── Monokai ───────────────────────────────────────────────────────────── */
.theme-monokai { background: #1e1f1c; }
.theme-monokai #agent-dashboard { background: #272822; border-left: solid #3e3d32; }
.theme-monokai .dashboard-title { color: #66d9ef; }
.theme-monokai .agent-entry { background: #272822; border: solid #3e3d32; }
.theme-monokai .agent-status { color: #75715e; }
.theme-monokai .agent-task { color: #75715e; }
.theme-monokai .agent-tools { color: #66d9ef; }
.theme-monokai .agent-progress { color: #a6e22e; }
.theme-monokai .dashboard-separator { color: #3e3d32; }
.theme-monokai .dashboard-stats { color: #75715e; }
.theme-monokai .active-color { color: #a6e22e; }
.theme-monokai .idle-color { color: #75715e; }
.theme-monokai .error-color { color: #f92672; }
.theme-monokai .completed-color { color: #66d9ef; }

.theme-monokai #messages { scrollbar-color: #a6e22e #272822; scrollbar-color-hover: #66d9ef #272822; }
.theme-monokai #new-messages-badge { background: #49483e; }
.theme-monokai .msg-user { border-left: solid #a6e22e; color: #66d9ef; }
.theme-monokai .msg-assistant { color: #f8f8f2; }
.theme-monokai .msg-system { color: #e6db74; border-left: solid #e6db74; }
.theme-monokai .msg-error-inline { color: #f92672; border-left: solid #f92672; }
.theme-monokai .msg-notice-inline { color: #e6db74; border-left: solid #e6db74; }
.theme-monokai .msg-meta { color: #5e5c50; }
.theme-monokai .msg-parallel { color: #ae81ff; border-left: solid #ae81ff; }

.theme-monokai .exchange-box { border: solid #3e3d32; }
.theme-monokai .exchange-box--user { border-left: solid #a6e22e; }
.theme-monokai .exchange-box--delegate { border-left: solid #ae81ff; }
.theme-monokai .exchange-box--chain { border-left: solid #49483e; }
.theme-monokai .exchange-box--orchestrate { border-left: solid #a6e22e; }
.theme-monokai .exchange-box--plan { border-left: #e6db74; }
.theme-monokai .exchange-box--command { border-left: solid #66d9ef; }
.theme-monokai .exchange-prompt-header { color: #f8f8f2; border-bottom: solid #3e3d32; }
.theme-monokai .exchange-body { color: #f8f8f2; }
.theme-monokai .exchange-divider { color: #3e3d32; }
.theme-monokai .exchange-prompt { color: #a6e22e; border-bottom: solid #3e3d32; }
.theme-monokai .exchange-assistant { color: #f8f8f2; }
.theme-monokai .agent-tag { color: #66d9ef; }
.theme-monokai .thinking-text { color: #75715e; border-left: solid #ae81ff; }
.theme-monokai .trace-badge { color: #49483e; }
.theme-monokai .trace-action-bar { background: #272822; border-top: solid #3e3d32; }
.theme-monokai .btn-view-trace { background: #272822; color: #a6e22e; }
.theme-monokai .btn-view-trace:hover { background: #3e3d32; color: #66d9ef; }
.theme-monokai .btn-view-trace:focus { background: #3e3d32; color: #66d9ef; }
.theme-monokai .plan-text { color: #a6e22e; border-left: solid #a6e22e; }

.theme-monokai .collapsible-card-box { border: solid #3e3d32; color: #f8f8f2; }
.theme-monokai .card-header { color: #f8f8f2; border-bottom: solid #3e3d32; }
.theme-monokai .card-body { color: #f8f8f2; }
.theme-monokai Collapsible { background: #272822; border: solid #3e3d32; }
.theme-monokai Collapsible .collapsible-title { background: #272822; color: #a6e22e; }
.theme-monokai Collapsible .collapsible-body { background: #272822; color: #f8f8f2; scrollbar-color: #a6e22e #272822; }

.theme-monokai .btn-copy-code { background: #272822; color: #75715e; }
.theme-monokai .btn-copy-code:hover { background: #3e3d32; color: #a6e22e; }
.theme-monokai .btn-copy-code:focus { background: #3e3d32; color: #a6e22e; }

.theme-monokai #input-area { background: #1e1f1c; border-top: solid #3e3d32; }
.theme-monokai #msg-input { background: #1e1f1c; border-top: solid #3e3d32; color: #f8f8f2; }
.theme-monokai #msg-input:focus { border-top: solid #a6e22e; color: #ffffff; background: #1e1f1c; }
.theme-monokai .btn-input-action { background: #272822; color: #75715e; }
.theme-monokai .btn-input-action:hover { background: #3e3d32; color: #f8f8f2; }
.theme-monokai .btn-input-action:focus { background: #3e3d32; color: #f8f8f2; }
.theme-monokai .btn-action-traces { color: #66d9ef; }
.theme-monokai .btn-action-traces:hover { background: #3e3d32; color: #a6e22e; }
.theme-monokai .btn-action-traces:focus { background: #3e3d32; color: #a6e22e; }
.theme-monokai .btn-action-cancel:hover { background: #3d1f2e; color: #f92672; }
.theme-monokai .btn-action-cancel:focus { background: #3d1f2e; }
.theme-monokai .btn-action-exit { color: #75715e; }
.theme-monokai .btn-action-exit:hover { background: #3d1f2e; color: #f92672; }

.theme-monokai #suggestions { background: #1e1f1c; border-top: solid #3e3d32; scrollbar-color: #a6e22e #272822; }
.theme-monokai .suggestion-item { color: #75715e; }
.theme-monokai .suggestion-item.highlighted { color: #ffffff; background: #49483e; }

.theme-monokai .code-block { background: #272822; color: #f8f8f2; border: tall #3e3d32; }
.theme-monokai .shell-escape-card { background: #272822; border: solid #3e3d32; }
.theme-monokai .shell-card-header { background: #3e3d32; color: #f8f8f2; border-bottom: solid #3e3d32; }
.theme-monokai .shell-output-text { color: #f8f8f2; }
.theme-monokai .spinner { color: #a6e22e; }
.theme-monokai .summary-box { background: #272822; border: solid #49483e; color: #f8f8f2; }
.theme-monokai .dev-trace-text { color: #66d9ef; background: #1e1f1c; border: solid #3e3d32; border-left: solid #f92672; }
.theme-monokai #welcome-screen { background: #272822; }
.theme-monokai .welcome-logo { color: #a6e22e; }
.theme-monokai .welcome-version { color: #f8f8f2; }
.theme-monokai .welcome-subtitle { color: #75715e; }
.theme-monokai .welcome-hint { color: #49483e; }
.theme-monokai .welcome-separator { color: #3e3d32; }
.theme-monokai #approval-bar { border-left: solid #e6db74; }
.theme-monokai #approval-bar .approval-label { color: #e6db74; }
.theme-monokai .approve-btn { color: #a6e22e; }
.theme-monokai .approve-btn:hover { background: #1a3a1a; }
.theme-monokai .approve-btn:focus { background: #1a3a1a; }
.theme-monokai .deny-btn { color: #f92672; }
.theme-monokai .deny-btn:hover { background: #3d1f2e; }
.theme-monokai .deny-btn:focus { background: #3d1f2e; }
.theme-monokai #parallel-bar { background: #272822; border: solid #ae81ff; }
.theme-monokai #parallel-bar .parallel-title { color: #ae81ff; }

.theme-monokai #diff-dialog, .theme-monokai #file-dialog, .theme-monokai #session-dialog, .theme-monokai #shortcuts-dialog, .theme-monokai .tv-box { background: #272822; border: solid #3e3d32; }
.theme-monokai #diff-dialog, .theme-monokai #file-dialog { border-top: solid #a6e22e; }
.theme-monokai #session-dialog { border-top: solid #ae81ff; }
.theme-monokai #shortcuts-dialog, .theme-monokai .tv-box { border-top: solid #a6e22e; }
.theme-monokai #diff-header, .theme-monokai #file-header, .theme-monokai #session-header, .theme-monokai .tv-header { border-bottom: solid #3e3d32; }
.theme-monokai #diff-title, .theme-monokai #file-title { color: #a6e22e; }
.theme-monokai #session-title { color: #ae81ff; }
.theme-monokai .tv-title { color: #a6e22e; }
.theme-monokai #diff-options, .theme-monokai #session-options, .theme-monokai DirectoryTree { background: #272822; }
.theme-monokai #tree-container { border-right: solid #3e3d32; }
.theme-monokai #preview-container { scrollbar-color: #a6e22e #272822; }
.theme-monokai #file-preview { color: #f8f8f2; }
.theme-monokai #diff-file-list, .theme-monokai #session-list-col { border-right: solid #3e3d32; }
.theme-monokai .shortcuts-header { color: #a6e22e; border-bottom: solid #3e3d32; }

/* ── Tokyo Night ───────────────────────────────────────────────────────── */
.theme-tokyo-night { background: #16161e; }
.theme-tokyo-night #agent-dashboard { background: #1a1b26; border-left: solid #292e42; }
.theme-tokyo-night .dashboard-title { color: #7aa2f7; }
.theme-tokyo-night .agent-entry { background: #1a1b26; border: solid #292e42; }
.theme-tokyo-night .agent-status { color: #565f89; }
.theme-tokyo-night .agent-task { color: #565f89; }
.theme-tokyo-night .agent-tools { color: #7aa2f7; }
.theme-tokyo-night .agent-progress { color: #9ece6a; }
.theme-tokyo-night .dashboard-separator { color: #292e42; }
.theme-tokyo-night .dashboard-stats { color: #565f89; }
.theme-tokyo-night .active-color { color: #9ece6a; }
.theme-tokyo-night .idle-color { color: #565f89; }
.theme-tokyo-night .error-color { color: #f7768e; }
.theme-tokyo-night .completed-color { color: #7aa2f7; }

.theme-tokyo-night #messages { scrollbar-color: #7aa2f7 #1a1b26; scrollbar-color-hover: #bb9af7 #1a1b26; }
.theme-tokyo-night #new-messages-badge { background: #3d59a1; }
.theme-tokyo-night .msg-user { border-left: solid #7aa2f7; color: #7aa2f7; }
.theme-tokyo-night .msg-assistant { color: #c0caf5; }
.theme-tokyo-night .msg-system { color: #e0af68; border-left: solid #e0af68; }
.theme-tokyo-night .msg-error-inline { color: #f7768e; border-left: solid #f7768e; }
.theme-tokyo-night .msg-notice-inline { color: #e0af68; border-left: solid #e0af68; }
.theme-tokyo-night .msg-meta { color: #414868; }
.theme-tokyo-night .msg-parallel { color: #bb9af7; border-left: solid #bb9af7; }

.theme-tokyo-night .exchange-box { border: solid #292e42; }
.theme-tokyo-night .exchange-box--user { border-left: solid #7aa2f7; }
.theme-tokyo-night .exchange-box--delegate { border-left: solid #bb9af7; }
.theme-tokyo-night .exchange-box--chain { border-left: solid #3d59a1; }
.theme-tokyo-night .exchange-box--orchestrate { border-left: solid #9ece6a; }
.theme-tokyo-night .exchange-box--plan { border-left: #e0af68; }
.theme-tokyo-night .exchange-box--command { border-left: solid #7aa2f7; }
.theme-tokyo-night .exchange-prompt-header { color: #a9b1d6; border-bottom: solid #292e42; }
.theme-tokyo-night .exchange-body { color: #c0caf5; }
.theme-tokyo-night .exchange-divider { color: #292e42; }
.theme-tokyo-night .exchange-prompt { color: #7aa2f7; border-bottom: solid #292e42; }
.theme-tokyo-night .exchange-assistant { color: #c0caf5; }
.theme-tokyo-night .agent-tag { color: #7aa2f7; }
.theme-tokyo-night .thinking-text { color: #565f89; border-left: solid #9d7cd8; }
.theme-tokyo-night .trace-badge { color: #3b4261; }
.theme-tokyo-night .trace-action-bar { background: #1a1b26; border-top: solid #292e42; }
.theme-tokyo-night .btn-view-trace { background: #1a1b26; color: #7aa2f7; }
.theme-tokyo-night .btn-view-trace:hover { background: #24283b; color: #bb9af7; }
.theme-tokyo-night .btn-view-trace:focus { background: #24283b; color: #bb9af7; }
.theme-tokyo-night .plan-text { color: #9ece6a; border-left: solid #9ece6a; }

.theme-tokyo-night .collapsible-card-box { border: solid #292e42; color: #c0caf5; }
.theme-tokyo-night .card-header { color: #a9b1d6; border-bottom: solid #292e42; }
.theme-tokyo-night .card-body { color: #c0caf5; }
.theme-tokyo-night Collapsible { background: #1a1b26; border: solid #292e42; }
.theme-tokyo-night Collapsible .collapsible-title { background: #1a1b26; color: #7aa2f7; }
.theme-tokyo-night Collapsible .collapsible-body { background: #1a1b26; color: #c0caf5; scrollbar-color: #7aa2f7 #1a1b26; }

.theme-tokyo-night .btn-copy-code { background: #1a1b26; color: #565f89; }
.theme-tokyo-night .btn-copy-code:hover { background: #24283b; color: #7aa2f7; }
.theme-tokyo-night .btn-copy-code:focus { background: #24283b; color: #7aa2f7; }

.theme-tokyo-night #input-area { background: #16161e; border-top: solid #292e42; }
.theme-tokyo-night #msg-input { background: #16161e; border-top: solid #292e42; color: #a9b1d6; }
.theme-tokyo-night #msg-input:focus { border-top: solid #7aa2f7; color: #c0caf5; background: #16161e; }
.theme-tokyo-night .btn-input-action { background: #1a1b26; color: #565f89; }
.theme-tokyo-night .btn-input-action:hover { background: #24283b; color: #c0caf5; }
.theme-tokyo-night .btn-input-action:focus { background: #24283b; color: #c0caf5; }
.theme-tokyo-night .btn-action-traces { color: #7aa2f7; }
.theme-tokyo-night .btn-action-traces:hover { background: #24283b; color: #bb9af7; }
.theme-tokyo-night .btn-action-traces:focus { background: #24283b; color: #bb9af7; }
.theme-tokyo-night .btn-action-cancel:hover { background: #3d2534; color: #f7768e; }
.theme-tokyo-night .btn-action-cancel:focus { background: #3d2534; }
.theme-tokyo-night .btn-action-exit { color: #565f89; }
.theme-tokyo-night .btn-action-exit:hover { background: #3d2534; color: #f7768e; }

.theme-tokyo-night #suggestions { background: #16161e; border-top: solid #292e42; scrollbar-color: #7aa2f7 #1a1b26; }
.theme-tokyo-night .suggestion-item { color: #565f89; }
.theme-tokyo-night .suggestion-item.highlighted { color: #ffffff; background: #3d59a1; }

.theme-tokyo-night .code-block { background: #1a1b26; color: #a9b1d6; border: tall #292e42; }
.theme-tokyo-night .shell-escape-card { background: #1a1b26; border: solid #292e42; }
.theme-tokyo-night .shell-card-header { background: #24283b; color: #a9b1d6; border-bottom: solid #292e42; }
.theme-tokyo-night .shell-output-text { color: #a9b1d6; }
.theme-tokyo-night .spinner { color: #7aa2f7; }
.theme-tokyo-night .summary-box { background: #1a1b26; border: solid #3d59a1; color: #a9b1d6; }
.theme-tokyo-night .dev-trace-text { color: #89b4fa; background: #16161e; border: solid #292e42; border-left: solid #f7768e; }
.theme-tokyo-night #welcome-screen { background: #1a1b26; }
.theme-tokyo-night .welcome-logo { color: #7aa2f7; }
.theme-tokyo-night .welcome-version { color: #c0caf5; }
.theme-tokyo-night .welcome-subtitle { color: #565f89; }
.theme-tokyo-night .welcome-hint { color: #3b4261; }
.theme-tokyo-night .welcome-separator { color: #292e42; }
.theme-tokyo-night #approval-bar { border-left: solid #e0af68; }
.theme-tokyo-night #approval-bar .approval-label { color: #e0af68; }
.theme-tokyo-night .approve-btn { color: #9ece6a; }
.theme-tokyo-night .approve-btn:hover { background: #1a3a1a; }
.theme-tokyo-night .approve-btn:focus { background: #1a3a1a; }
.theme-tokyo-night .deny-btn { color: #f7768e; }
.theme-tokyo-night .deny-btn:hover { background: #3d2534; }
.theme-tokyo-night .deny-btn:focus { background: #3d2534; }
.theme-tokyo-night #parallel-bar { background: #1a1b26; border: solid #bb9af7; }
.theme-tokyo-night #parallel-bar .parallel-title { color: #bb9af7; }

.theme-tokyo-night #diff-dialog, .theme-tokyo-night #file-dialog, .theme-tokyo-night #session-dialog, .theme-tokyo-night #shortcuts-dialog, .theme-tokyo-night .tv-box { background: #1a1b26; border: solid #292e42; }
.theme-tokyo-night #diff-dialog, .theme-tokyo-night #file-dialog { border-top: solid #7aa2f7; }
.theme-tokyo-night #session-dialog { border-top: solid #bb9af7; }
.theme-tokyo-night #shortcuts-dialog, .theme-tokyo-night .tv-box { border-top: solid #7aa2f7; }
.theme-tokyo-night #diff-header, .theme-tokyo-night #file-header, .theme-tokyo-night #session-header, .theme-tokyo-night .tv-header { border-bottom: solid #292e42; }
.theme-tokyo-night #diff-title, .theme-tokyo-night #file-title { color: #7aa2f7; }
.theme-tokyo-night #session-title { color: #bb9af7; }
.theme-tokyo-night .tv-title { color: #7aa2f7; }
.theme-tokyo-night #diff-options, .theme-tokyo-night #session-options, .theme-tokyo-night DirectoryTree { background: #1a1b26; }
.theme-tokyo-night #tree-container { border-right: solid #292e42; }
.theme-tokyo-night #preview-container { scrollbar-color: #7aa2f7 #1a1b26; }
.theme-tokyo-night #file-preview { color: #a9b1d6; }
.theme-tokyo-night #diff-file-list, .theme-tokyo-night #session-list-col { border-right: solid #292e42; }
.theme-tokyo-night .shortcuts-header { color: #7aa2f7; border-bottom: solid #292e42; }

/* ── Solarized Dark ────────────────────────────────────────────────────── */
.theme-solarized-dark { background: #00212b; }
.theme-solarized-dark #agent-dashboard { background: #002b36; border-left: solid #073642; }
.theme-solarized-dark .dashboard-title { color: #268bd2; }
.theme-solarized-dark .agent-entry { background: #002b36; border: solid #073642; }
.theme-solarized-dark .agent-status { color: #657b83; }
.theme-solarized-dark .agent-task { color: #657b83; }
.theme-solarized-dark .agent-tools { color: #268bd2; }
.theme-solarized-dark .agent-progress { color: #859900; }
.theme-solarized-dark .dashboard-separator { color: #073642; }
.theme-solarized-dark .dashboard-stats { color: #657b83; }
.theme-solarized-dark .active-color { color: #859900; }
.theme-solarized-dark .idle-color { color: #657b83; }
.theme-solarized-dark .error-color { color: #dc322f; }
.theme-solarized-dark .completed-color { color: #268bd2; }

.theme-solarized-dark #messages { scrollbar-color: #268bd2 #002b36; scrollbar-color-hover: #2aa198 #002b36; }
.theme-solarized-dark #new-messages-badge { background: #268bd2; }
.theme-solarized-dark .msg-user { border-left: solid #268bd2; color: #268bd2; }
.theme-solarized-dark .msg-assistant { color: #839496; }
.theme-solarized-dark .msg-system { color: #b58900; border-left: solid #b58900; }
.theme-solarized-dark .msg-error-inline { color: #dc322f; border-left: solid #dc322f; }
.theme-solarized-dark .msg-notice-inline { color: #b58900; border-left: solid #b58900; }
.theme-solarized-dark .msg-meta { color: #586e75; }
.theme-solarized-dark .msg-parallel { color: #6c71c4; border-left: solid #6c71c4; }

.theme-solarized-dark .exchange-box { border: solid #073642; }
.theme-solarized-dark .exchange-box--user { border-left: solid #268bd2; }
.theme-solarized-dark .exchange-box--delegate { border-left: solid #6c71c4; }
.theme-solarized-dark .exchange-box--chain { border-left: solid #268bd2; }
.theme-solarized-dark .exchange-box--orchestrate { border-left: solid #859900; }
.theme-solarized-dark .exchange-box--plan { border-left: #b58900; }
.theme-solarized-dark .exchange-box--command { border-left: solid #2aa198; }
.theme-solarized-dark .exchange-prompt-header { color: #93a1a1; border-bottom: solid #073642; }
.theme-solarized-dark .exchange-body { color: #839496; }
.theme-solarized-dark .exchange-divider { color: #073642; }
.theme-solarized-dark .exchange-prompt { color: #268bd2; border-bottom: solid #073642; }
.theme-solarized-dark .exchange-assistant { color: #839496; }
.theme-solarized-dark .agent-tag { color: #268bd2; }
.theme-solarized-dark .thinking-text { color: #657b83; border-left: solid #6c71c4; }
.theme-solarized-dark .trace-badge { color: #073642; }
.theme-solarized-dark .trace-action-bar { background: #002b36; border-top: solid #073642; }
.theme-solarized-dark .btn-view-trace { background: #002b36; color: #268bd2; }
.theme-solarized-dark .btn-view-trace:hover { background: #073642; color: #2aa198; }
.theme-solarized-dark .btn-view-trace:focus { background: #073642; color: #2aa198; }
.theme-solarized-dark .plan-text { color: #859900; border-left: solid #859900; }

.theme-solarized-dark .collapsible-card-box { border: solid #073642; color: #839496; }
.theme-solarized-dark .card-header { color: #93a1a1; border-bottom: solid #073642; }
.theme-solarized-dark .card-body { color: #839496; }
.theme-solarized-dark Collapsible { background: #002b36; border: solid #073642; }
.theme-solarized-dark Collapsible .collapsible-title { background: #002b36; color: #268bd2; }
.theme-solarized-dark Collapsible .collapsible-body { background: #002b36; color: #839496; scrollbar-color: #268bd2 #002b36; }

.theme-solarized-dark .btn-copy-code { background: #002b36; color: #657b83; }
.theme-solarized-dark .btn-copy-code:hover { background: #073642; color: #268bd2; }
.theme-solarized-dark .btn-copy-code:focus { background: #073642; color: #268bd2; }

.theme-solarized-dark #input-area { background: #00212b; border-top: solid #073642; }
.theme-solarized-dark #msg-input { background: #00212b; border-top: solid #073642; color: #93a1a1; }
.theme-solarized-dark #msg-input:focus { border-top: solid #268bd2; color: #fdf6e3; background: #00212b; }
.theme-solarized-dark .btn-input-action { background: #002b36; color: #657b83; }
.theme-solarized-dark .btn-input-action:hover { background: #073642; color: #839496; }
.theme-solarized-dark .btn-input-action:focus { background: #073642; color: #839496; }
.theme-solarized-dark .btn-action-traces { color: #268bd2; }
.theme-solarized-dark .btn-action-traces:hover { background: #073642; color: #2aa198; }
.theme-solarized-dark .btn-action-traces:focus { background: #073642; color: #2aa198; }
.theme-solarized-dark .btn-action-cancel:hover { background: #3d2525; color: #dc322f; }
.theme-solarized-dark .btn-action-cancel:focus { background: #3d2525; }
.theme-solarized-dark .btn-action-exit { color: #657b83; }
.theme-solarized-dark .btn-action-exit:hover { background: #3d2525; color: #dc322f; }

.theme-solarized-dark #suggestions { background: #00212b; border-top: solid #073642; scrollbar-color: #268bd2 #002b36; }
.theme-solarized-dark .suggestion-item { color: #657b83; }
.theme-solarized-dark .suggestion-item.highlighted { color: #fdf6e3; background: #268bd2; }

.theme-solarized-dark .code-block { background: #002b36; color: #93a1a1; border: tall #073642; }
.theme-solarized-dark .shell-escape-card { background: #002b36; border: solid #073642; }
.theme-solarized-dark .shell-card-header { background: #073642; color: #93a1a1; border-bottom: solid #073642; }
.theme-solarized-dark .shell-output-text { color: #93a1a1; }
.theme-solarized-dark .spinner { color: #268bd2; }
.theme-solarized-dark .summary-box { background: #002b36; border: solid #268bd2; color: #93a1a1; }
.theme-solarized-dark .dev-trace-text { color: #2aa198; background: #00212b; border: solid #073642; border-left: solid #dc322f; }
.theme-solarized-dark #welcome-screen { background: #002b36; }
.theme-solarized-dark .welcome-logo { color: #268bd2; }
.theme-solarized-dark .welcome-version { color: #fdf6e3; }
.theme-solarized-dark .welcome-subtitle { color: #657b83; }
.theme-solarized-dark .welcome-hint { color: #586e75; }
.theme-solarized-dark .welcome-separator { color: #073642; }
.theme-solarized-dark #approval-bar { border-left: solid #b58900; }
.theme-solarized-dark #approval-bar .approval-label { color: #b58900; }
.theme-solarized-dark .approve-btn { color: #859900; }
.theme-solarized-dark .approve-btn:hover { background: #1a3a1a; }
.theme-solarized-dark .approve-btn:focus { background: #1a3a1a; }
.theme-solarized-dark .deny-btn { color: #dc322f; }
.theme-solarized-dark .deny-btn:hover { background: #3d2525; }
.theme-solarized-dark .deny-btn:focus { background: #3d2525; }
.theme-solarized-dark #parallel-bar { background: #002b36; border: solid #6c71c4; }
.theme-solarized-dark #parallel-bar .parallel-title { color: #6c71c4; }

.theme-solarized-dark #diff-dialog, .theme-solarized-dark #file-dialog, .theme-solarized-dark #session-dialog, .theme-solarized-dark #shortcuts-dialog, .theme-solarized-dark .tv-box { background: #002b36; border: solid #073642; }
.theme-solarized-dark #diff-dialog, .theme-solarized-dark #file-dialog { border-top: solid #268bd2; }
.theme-solarized-dark #session-dialog { border-top: solid #6c71c4; }
.theme-solarized-dark #shortcuts-dialog, .theme-solarized-dark .tv-box { border-top: solid #268bd2; }
.theme-solarized-dark #diff-header, .theme-solarized-dark #file-header, .theme-solarized-dark #session-header, .theme-solarized-dark .tv-header { border-bottom: solid #073642; }
.theme-solarized-dark #diff-title, .theme-solarized-dark #file-title { color: #268bd2; }
.theme-solarized-dark #session-title { color: #6c71c4; }
.theme-solarized-dark .tv-title { color: #268bd2; }
.theme-solarized-dark #diff-options, .theme-solarized-dark #session-options, .theme-solarized-dark DirectoryTree { background: #002b36; }
.theme-solarized-dark #tree-container { border-right: solid #073642; }
.theme-solarized-dark #preview-container { scrollbar-color: #268bd2 #002b36; }
.theme-solarized-dark #file-preview { color: #93a1a1; }
.theme-solarized-dark #diff-file-list, .theme-solarized-dark #session-list-col { border-right: solid #073642; }
.theme-solarized-dark .shortcuts-header { color: #268bd2; border-bottom: solid #073642; }

/* ── Cyberpunk ─────────────────────────────────────────────────────────── */
.theme-cyberpunk { background: #08090f; }
.theme-cyberpunk #agent-dashboard { background: #10121d; border-left: solid #202637; }
.theme-cyberpunk .dashboard-title { color: #00f0ff; }
.theme-cyberpunk .agent-entry { background: #10121d; border: solid #202637; }
.theme-cyberpunk .agent-status { color: #008094; }
.theme-cyberpunk .agent-task { color: #008094; }
.theme-cyberpunk .agent-tools { color: #00f0ff; }
.theme-cyberpunk .agent-progress { color: #39ff14; }
.theme-cyberpunk .dashboard-separator { color: #202637; }
.theme-cyberpunk .dashboard-stats { color: #008094; }
.theme-cyberpunk .active-color { color: #39ff14; }
.theme-cyberpunk .idle-color { color: #008094; }
.theme-cyberpunk .error-color { color: #ff003c; }
.theme-cyberpunk .completed-color { color: #00f0ff; }

.theme-cyberpunk #messages { scrollbar-color: #00f0ff #10121d; scrollbar-color-hover: #ffee00 #10121d; }
.theme-cyberpunk #new-messages-badge { background: #005060; }
.theme-cyberpunk .msg-user { border-left: solid #00f0ff; color: #00f0ff; }
.theme-cyberpunk .msg-assistant { color: #00f0ff; }
.theme-cyberpunk .msg-system { color: #ffee00; border-left: solid #ffee00; }
.theme-cyberpunk .msg-error-inline { color: #ff003c; border-left: solid #ff003c; }
.theme-cyberpunk .msg-notice-inline { color: #ffee00; border-left: solid #ffee00; }
.theme-cyberpunk .msg-meta { color: #005060; }
.theme-cyberpunk .msg-parallel { color: #ff00ff; border-left: solid #ff00ff; }

.theme-cyberpunk .exchange-box { border: solid #202637; }
.theme-cyberpunk .exchange-box--user { border-left: solid #00f0ff; }
.theme-cyberpunk .exchange-box--delegate { border-left: solid #ff00ff; }
.theme-cyberpunk .exchange-box--chain { border-left: solid #005060; }
.theme-cyberpunk .exchange-box--orchestrate { border-left: solid #39ff14; }
.theme-cyberpunk .exchange-box--plan { border-left: #ffee00; }
.theme-cyberpunk .exchange-box--command { border-left: solid #00f0ff; }
.theme-cyberpunk .exchange-prompt-header { color: #00d4e6; border-bottom: solid #202637; }
.theme-cyberpunk .exchange-body { color: #00f0ff; }
.theme-cyberpunk .exchange-divider { color: #202637; }
.theme-cyberpunk .exchange-prompt { color: #00f0ff; border-bottom: solid #202637; }
.theme-cyberpunk .exchange-assistant { color: #00f0ff; }
.theme-cyberpunk .agent-tag { color: #00f0ff; }
.theme-cyberpunk .thinking-text { color: #008094; border-left: solid #aa00aa; }
.theme-cyberpunk .trace-badge { color: #202637; }
.theme-cyberpunk .trace-action-bar { background: #10121d; border-top: solid #202637; }
.theme-cyberpunk .btn-view-trace { background: #10121d; color: #00f0ff; }
.theme-cyberpunk .btn-view-trace:hover { background: #181c2a; color: #ffee00; }
.theme-cyberpunk .btn-view-trace:focus { background: #181c2a; color: #ffee00; }
.theme-cyberpunk .plan-text { color: #39ff14; border-left: solid #39ff14; }

.theme-cyberpunk .collapsible-card-box { border: solid #202637; color: #00f0ff; }
.theme-cyberpunk .card-header { color: #00d4e6; border-bottom: solid #202637; }
.theme-cyberpunk .card-body { color: #00f0ff; }
.theme-cyberpunk Collapsible { background: #10121d; border: solid #202637; }
.theme-cyberpunk Collapsible .collapsible-title { background: #10121d; color: #00f0ff; }
.theme-cyberpunk Collapsible .collapsible-body { background: #10121d; color: #00f0ff; scrollbar-color: #00f0ff #10121d; }

.theme-cyberpunk .btn-copy-code { background: #10121d; color: #008094; }
.theme-cyberpunk .btn-copy-code:hover { background: #181c2a; color: #00f0ff; }
.theme-cyberpunk .btn-copy-code:focus { background: #181c2a; color: #00f0ff; }

.theme-cyberpunk #input-area { background: #08090f; border-top: solid #202637; }
.theme-cyberpunk #msg-input { background: #08090f; border-top: solid #202637; color: #00d4e6; }
.theme-cyberpunk #msg-input:focus { border-top: solid #00f0ff; color: #ffee00; background: #08090f; }
.theme-cyberpunk .btn-input-action { background: #10121d; color: #008094; }
.theme-cyberpunk .btn-input-action:hover { background: #181c2a; color: #00f0ff; }
.theme-cyberpunk .btn-input-action:focus { background: #181c2a; color: #00f0ff; }
.theme-cyberpunk .btn-action-traces { color: #00f0ff; }
.theme-cyberpunk .btn-action-traces:hover { background: #181c2a; color: #ffee00; }
.theme-cyberpunk .btn-action-traces:focus { background: #181c2a; color: #ffee00; }
.theme-cyberpunk .btn-action-cancel:hover { background: #3d0012; color: #ff003c; }
.theme-cyberpunk .btn-action-cancel:focus { background: #3d0012; }
.theme-cyberpunk .btn-action-exit { color: #008094; }
.theme-cyberpunk .btn-action-exit:hover { background: #3d0012; color: #ff003c; }

.theme-cyberpunk #suggestions { background: #08090f; border-top: solid #202637; scrollbar-color: #00f0ff #10121d; }
.theme-cyberpunk .suggestion-item { color: #008094; }
.theme-cyberpunk .suggestion-item.highlighted { color: #ffee00; background: #005060; }

.theme-cyberpunk .code-block { background: #10121d; color: #00d4e6; border: tall #202637; }
.theme-cyberpunk .shell-escape-card { background: #10121d; border: solid #202637; }
.theme-cyberpunk .shell-card-header { background: #181c2a; color: #00d4e6; border-bottom: solid #202637; }
.theme-cyberpunk .shell-output-text { color: #00d4e6; }
.theme-cyberpunk .spinner { color: #00f0ff; }
.theme-cyberpunk .summary-box { background: #10121d; border: solid #005060; color: #00d4e6; }
.theme-cyberpunk .dev-trace-text { color: #00f0ff; background: #08090f; border: solid #202637; border-left: solid #ff003c; }
.theme-cyberpunk #welcome-screen { background: #10121d; }
.theme-cyberpunk .welcome-logo { color: #00f0ff; }
.theme-cyberpunk .welcome-version { color: #ffee00; }
.theme-cyberpunk .welcome-subtitle { color: #008094; }
.theme-cyberpunk .welcome-hint { color: #005060; }
.theme-cyberpunk .welcome-separator { color: #202637; }
.theme-cyberpunk #approval-bar { border-left: solid #ffee00; }
.theme-cyberpunk #approval-bar .approval-label { color: #ffee00; }
.theme-cyberpunk .approve-btn { color: #39ff14; }
.theme-cyberpunk .approve-btn:hover { background: #0a2a0a; }
.theme-cyberpunk .approve-btn:focus { background: #0a2a0a; }
.theme-cyberpunk .deny-btn { color: #ff003c; }
.theme-cyberpunk .deny-btn:hover { background: #3d0012; }
.theme-cyberpunk .deny-btn:focus { background: #3d0012; }
.theme-cyberpunk #parallel-bar { background: #10121d; border: solid #ff00ff; }
.theme-cyberpunk #parallel-bar .parallel-title { color: #ff00ff; }

.theme-cyberpunk #diff-dialog, .theme-cyberpunk #file-dialog, .theme-cyberpunk #session-dialog, .theme-cyberpunk #shortcuts-dialog, .theme-cyberpunk .tv-box { background: #10121d; border: solid #202637; }
.theme-cyberpunk #diff-dialog, .theme-cyberpunk #file-dialog { border-top: solid #00f0ff; }
.theme-cyberpunk #session-dialog { border-top: solid #ffee00; }
.theme-cyberpunk #shortcuts-dialog, .theme-cyberpunk .tv-box { border-top: solid #00f0ff; }
.theme-cyberpunk #diff-header, .theme-cyberpunk #file-header, .theme-cyberpunk #session-header, .theme-cyberpunk .tv-header { border-bottom: solid #202637; }
.theme-cyberpunk #diff-title, .theme-cyberpunk #file-title { color: #00f0ff; }
.theme-cyberpunk #session-title { color: #ffee00; }
.theme-cyberpunk .tv-title { color: #00f0ff; }
.theme-cyberpunk #diff-options, .theme-cyberpunk #session-options, .theme-cyberpunk DirectoryTree { background: #10121d; }
.theme-cyberpunk #tree-container { border-right: solid #202637; }
.theme-cyberpunk #preview-container { scrollbar-color: #00f0ff #10121d; }
.theme-cyberpunk #file-preview { color: #00d4e6; }
.theme-cyberpunk #diff-file-list, .theme-cyberpunk #session-list-col { border-right: solid #202637; }
.theme-cyberpunk .shortcuts-header { color: #00f0ff; border-bottom: solid #202637; }

/* ── Catppuccin Mocha ──────────────────────────────────────────────────── */
.theme-catppuccin-mocha { background: #1e1e2e; }
.theme-catppuccin-mocha #agent-dashboard { background: #181825; border-left: solid #313244; }
.theme-catppuccin-mocha .dashboard-title { color: #cba6f7; }
.theme-catppuccin-mocha .agent-entry { background: #181825; border: solid #313244; }
.theme-catppuccin-mocha .agent-status { color: #6c7086; }
.theme-catppuccin-mocha .agent-task { color: #6c7086; }
.theme-catppuccin-mocha .agent-tools { color: #cba6f7; }
.theme-catppuccin-mocha .agent-progress { color: #a6e3a1; }
.theme-catppuccin-mocha .dashboard-separator { color: #313244; }
.theme-catppuccin-mocha .dashboard-stats { color: #6c7086; }
.theme-catppuccin-mocha .active-color { color: #a6e3a1; }
.theme-catppuccin-mocha .idle-color { color: #6c7086; }
.theme-catppuccin-mocha .error-color { color: #f38ba8; }
.theme-catppuccin-mocha .completed-color { color: #89b4fa; }

.theme-catppuccin-mocha #messages { scrollbar-color: #cba6f7 #181825; scrollbar-color-hover: #f5c2e7 #181825; }
.theme-catppuccin-mocha #new-messages-badge { background: #45475a; }
.theme-catppuccin-mocha .msg-user { border-left: solid #cba6f7; color: #cba6f7; }
.theme-catppuccin-mocha .msg-assistant { color: #cdd6f4; }
.theme-catppuccin-mocha .msg-system { color: #f9e2af; border-left: solid #f9e2af; }
.theme-catppuccin-mocha .msg-error-inline { color: #f38ba8; border-left: solid #f38ba8; }
.theme-catppuccin-mocha .msg-notice-inline { color: #f9e2af; border-left: solid #f9e2af; }
.theme-catppuccin-mocha .msg-meta { color: #585b70; }
.theme-catppuccin-mocha .msg-parallel { color: #cba6f7; border-left: solid #cba6f7; }

.theme-catppuccin-mocha .exchange-box { border: solid #313244; }
.theme-catppuccin-mocha .exchange-box--user { border-left: solid #cba6f7; }
.theme-catppuccin-mocha .exchange-box--delegate { border-left: solid #cba6f7; }
.theme-catppuccin-mocha .exchange-box--chain { border-left: solid #45475a; }
.theme-catppuccin-mocha .exchange-box--orchestrate { border-left: solid #a6e3a1; }
.theme-catppuccin-mocha .exchange-box--plan { border-left: #f9e2af; }
.theme-catppuccin-mocha .exchange-box--command { border-left: solid #89b4fa; }
.theme-catppuccin-mocha .exchange-prompt-header { color: #bac2de; border-bottom: solid #313244; }
.theme-catppuccin-mocha .exchange-body { color: #cdd6f4; }
.theme-catppuccin-mocha .exchange-divider { color: #313244; }
.theme-catppuccin-mocha .exchange-prompt { color: #cba6f7; border-bottom: solid #313244; }
.theme-catppuccin-mocha .exchange-assistant { color: #cdd6f4; }
.theme-catppuccin-mocha .agent-tag { color: #89b4fa; }
.theme-catppuccin-mocha .thinking-text { color: #6c7086; border-left: solid #cba6f7; }
.theme-catppuccin-mocha .trace-badge { color: #45475a; }
.theme-catppuccin-mocha .trace-action-bar { background: #181825; border-top: solid #313244; }
.theme-catppuccin-mocha .btn-view-trace { background: #181825; color: #cba6f7; }
.theme-catppuccin-mocha .btn-view-trace:hover { background: #313244; color: #f5c2e7; }
.theme-catppuccin-mocha .btn-view-trace:focus { background: #313244; color: #f5c2e7; }
.theme-catppuccin-mocha .plan-text { color: #a6e3a1; border-left: solid #a6e3a1; }

.theme-catppuccin-mocha .collapsible-card-box { border: solid #313244; color: #cdd6f4; }
.theme-catppuccin-mocha .card-header { color: #bac2de; border-bottom: solid #313244; }
.theme-catppuccin-mocha .card-body { color: #cdd6f4; }
.theme-catppuccin-mocha Collapsible { background: #181825; border: solid #313244; }
.theme-catppuccin-mocha Collapsible .collapsible-title { background: #181825; color: #cba6f7; }
.theme-catppuccin-mocha Collapsible .collapsible-body { background: #181825; color: #cdd6f4; scrollbar-color: #cba6f7 #181825; }

.theme-catppuccin-mocha .btn-copy-code { background: #181825; color: #6c7086; }
.theme-catppuccin-mocha .btn-copy-code:hover { background: #313244; color: #cba6f7; }
.theme-catppuccin-mocha .btn-copy-code:focus { background: #313244; color: #cba6f7; }

.theme-catppuccin-mocha #input-area { background: #1e1e2e; border-top: solid #313244; }
.theme-catppuccin-mocha #msg-input { background: #1e1e2e; border-top: solid #313244; color: #bac2de; }
.theme-catppuccin-mocha #msg-input:focus { border-top: solid #cba6f7; color: #ffffff; background: #1e1e2e; }
.theme-catppuccin-mocha .btn-input-action { background: #181825; color: #6c7086; }
.theme-catppuccin-mocha .btn-input-action:hover { background: #313244; color: #cdd6f4; }
.theme-catppuccin-mocha .btn-input-action:focus { background: #313244; color: #cdd6f4; }
.theme-catppuccin-mocha .btn-action-traces { color: #cba6f7; }
.theme-catppuccin-mocha .btn-action-traces:hover { background: #313244; color: #f5c2e7; }
.theme-catppuccin-mocha .btn-action-traces:focus { background: #313244; color: #f5c2e7; }
.theme-catppuccin-mocha .btn-action-cancel:hover { background: #3d2030; color: #f38ba8; }
.theme-catppuccin-mocha .btn-action-cancel:focus { background: #3d2030; }
.theme-catppuccin-mocha .btn-action-exit { color: #6c7086; }
.theme-catppuccin-mocha .btn-action-exit:hover { background: #3d2030; color: #f38ba8; }

.theme-catppuccin-mocha #suggestions { background: #1e1e2e; border-top: solid #313244; scrollbar-color: #cba6f7 #181825; }
.theme-catppuccin-mocha .suggestion-item { color: #6c7086; }
.theme-catppuccin-mocha .suggestion-item.highlighted { color: #ffffff; background: #45475a; }

.theme-catppuccin-mocha .code-block { background: #181825; color: #bac2de; border: tall #313244; }
.theme-catppuccin-mocha .shell-escape-card { background: #181825; border: solid #313244; }
.theme-catppuccin-mocha .shell-card-header { background: #313244; color: #bac2de; border-bottom: solid #313244; }
.theme-catppuccin-mocha .shell-output-text { color: #bac2de; }
.theme-catppuccin-mocha .spinner { color: #cba6f7; }
.theme-catppuccin-mocha .summary-box { background: #181825; border: solid #45475a; color: #bac2de; }
.theme-catppuccin-mocha .dev-trace-text { color: #89dceb; background: #1e1e2e; border: solid #313244; border-left: solid #f38ba8; }
.theme-catppuccin-mocha #welcome-screen { background: #181825; }
.theme-catppuccin-mocha .welcome-logo { color: #cba6f7; }
.theme-catppuccin-mocha .welcome-version { color: #cdd6f4; }
.theme-catppuccin-mocha .welcome-subtitle { color: #6c7086; }
.theme-catppuccin-mocha .welcome-hint { color: #45475a; }
.theme-catppuccin-mocha .welcome-separator { color: #313244; }
.theme-catppuccin-mocha #approval-bar { border-left: solid #f9e2af; }
.theme-catppuccin-mocha #approval-bar .approval-label { color: #f9e2af; }
.theme-catppuccin-mocha .approve-btn { color: #a6e3a1; }
.theme-catppuccin-mocha .approve-btn:hover { background: #1a3a1a; }
.theme-catppuccin-mocha .approve-btn:focus { background: #1a3a1a; }
.theme-catppuccin-mocha .deny-btn { color: #f38ba8; }
.theme-catppuccin-mocha .deny-btn:hover { background: #3d2030; }
.theme-catppuccin-mocha .deny-btn:focus { background: #3d2030; }
.theme-catppuccin-mocha #parallel-bar { background: #181825; border: solid #cba6f7; }
.theme-catppuccin-mocha #parallel-bar .parallel-title { color: #cba6f7; }

.theme-catppuccin-mocha #diff-dialog, .theme-catppuccin-mocha #file-dialog, .theme-catppuccin-mocha #session-dialog, .theme-catppuccin-mocha #shortcuts-dialog, .theme-catppuccin-mocha .tv-box { background: #181825; border: solid #313244; }
.theme-catppuccin-mocha #diff-dialog, .theme-catppuccin-mocha #file-dialog { border-top: solid #cba6f7; }
.theme-catppuccin-mocha #session-dialog { border-top: solid #f5c2e7; }
.theme-catppuccin-mocha #shortcuts-dialog, .theme-catppuccin-mocha .tv-box { border-top: solid #cba6f7; }
.theme-catppuccin-mocha #diff-header, .theme-catppuccin-mocha #file-header, .theme-catppuccin-mocha #session-header, .theme-catppuccin-mocha .tv-header { border-bottom: solid #313244; }
.theme-catppuccin-mocha #diff-title, .theme-catppuccin-mocha #file-title { color: #cba6f7; }
.theme-catppuccin-mocha #session-title { color: #f5c2e7; }
.theme-catppuccin-mocha .tv-title { color: #cba6f7; }
.theme-catppuccin-mocha #diff-options, .theme-catppuccin-mocha #session-options, .theme-catppuccin-mocha DirectoryTree { background: #181825; }
.theme-catppuccin-mocha #tree-container { border-right: solid #313244; }
.theme-catppuccin-mocha #preview-container { scrollbar-color: #cba6f7 #181825; }
.theme-catppuccin-mocha #file-preview { color: #bac2de; }
.theme-catppuccin-mocha #diff-file-list, .theme-catppuccin-mocha #session-list-col { border-right: solid #313244; }
.theme-catppuccin-mocha .shortcuts-header { color: #cba6f7; border-bottom: solid #313244; }

/* ── Gruvbox Dark ──────────────────────────────────────────────────────── */
.theme-gruvbox-dark { background: #1d2021; }
.theme-gruvbox-dark #agent-dashboard { background: #282828; border-left: solid #3c3836; }
.theme-gruvbox-dark .dashboard-title { color: #fabd2f; }
.theme-gruvbox-dark .agent-entry { background: #282828; border: solid #3c3836; }
.theme-gruvbox-dark .agent-status { color: #a89984; }
.theme-gruvbox-dark .agent-task { color: #a89984; }
.theme-gruvbox-dark .agent-tools { color: #fabd2f; }
.theme-gruvbox-dark .agent-progress { color: #b8bb26; }
.theme-gruvbox-dark .dashboard-separator { color: #3c3836; }
.theme-gruvbox-dark .dashboard-stats { color: #a89984; }
.theme-gruvbox-dark .active-color { color: #b8bb26; }
.theme-gruvbox-dark .idle-color { color: #a89984; }
.theme-gruvbox-dark .error-color { color: #fb4934; }
.theme-gruvbox-dark .completed-color { color: #83a598; }

.theme-gruvbox-dark #messages { scrollbar-color: #fabd2f #282828; scrollbar-color-hover: #fe8019 #282828; }
.theme-gruvbox-dark #new-messages-badge { background: #504945; }
.theme-gruvbox-dark .msg-user { border-left: solid #fabd2f; color: #fabd2f; }
.theme-gruvbox-dark .msg-assistant { color: #ebdbb2; }
.theme-gruvbox-dark .msg-system { color: #fabd2f; border-left: solid #fabd2f; }
.theme-gruvbox-dark .msg-error-inline { color: #fb4934; border-left: solid #fb4934; }
.theme-gruvbox-dark .msg-notice-inline { color: #fabd2f; border-left: solid #fabd2f; }
.theme-gruvbox-dark .msg-meta { color: #7c6f64; }
.theme-gruvbox-dark .msg-parallel { color: #d3869b; border-left: solid #d3869b; }

.theme-gruvbox-dark .exchange-box { border: solid #3c3836; }
.theme-gruvbox-dark .exchange-box--user { border-left: solid #fabd2f; }
.theme-gruvbox-dark .exchange-box--delegate { border-left: solid #d3869b; }
.theme-gruvbox-dark .exchange-box--chain { border-left: solid #504945; }
.theme-gruvbox-dark .exchange-box--orchestrate { border-left: solid #b8bb26; }
.theme-gruvbox-dark .exchange-box--plan { border-left: #fabd2f; }
.theme-gruvbox-dark .exchange-box--command { border-left: solid #83a598; }
.theme-gruvbox-dark .exchange-prompt-header { color: #d5c4a1; border-bottom: solid #3c3836; }
.theme-gruvbox-dark .exchange-body { color: #ebdbb2; }
.theme-gruvbox-dark .exchange-divider { color: #3c3836; }
.theme-gruvbox-dark .exchange-prompt { color: #fabd2f; border-bottom: solid #3c3836; }
.theme-gruvbox-dark .exchange-assistant { color: #ebdbb2; }
.theme-gruvbox-dark .agent-tag { color: #fabd2f; }
.theme-gruvbox-dark .thinking-text { color: #a89984; border-left: solid #d3869b; }
.theme-gruvbox-dark .trace-badge { color: #504945; }
.theme-gruvbox-dark .trace-action-bar { background: #282828; border-top: solid #3c3836; }
.theme-gruvbox-dark .btn-view-trace { background: #282828; color: #fabd2f; }
.theme-gruvbox-dark .btn-view-trace:hover { background: #3c3836; color: #fe8019; }
.theme-gruvbox-dark .btn-view-trace:focus { background: #3c3836; color: #fe8019; }
.theme-gruvbox-dark .plan-text { color: #b8bb26; border-left: solid #b8bb26; }

.theme-gruvbox-dark .collapsible-card-box { border: solid #3c3836; color: #ebdbb2; }
.theme-gruvbox-dark .card-header { color: #d5c4a1; border-bottom: solid #3c3836; }
.theme-gruvbox-dark .card-body { color: #ebdbb2; }
.theme-gruvbox-dark Collapsible { background: #282828; border: solid #3c3836; }
.theme-gruvbox-dark Collapsible .collapsible-title { background: #282828; color: #fabd2f; }
.theme-gruvbox-dark Collapsible .collapsible-body { background: #282828; color: #ebdbb2; scrollbar-color: #fabd2f #282828; }

.theme-gruvbox-dark .btn-copy-code { background: #282828; color: #a89984; }
.theme-gruvbox-dark .btn-copy-code:hover { background: #3c3836; color: #fabd2f; }
.theme-gruvbox-dark .btn-copy-code:focus { background: #3c3836; color: #fabd2f; }

.theme-gruvbox-dark #input-area { background: #1d2021; border-top: solid #3c3836; }
.theme-gruvbox-dark #msg-input { background: #1d2021; border-top: solid #3c3836; color: #d5c4a1; }
.theme-gruvbox-dark #msg-input:focus { border-top: solid #fabd2f; color: #fbf1c7; background: #1d2021; }
.theme-gruvbox-dark .btn-input-action { background: #282828; color: #a89984; }
.theme-gruvbox-dark .btn-input-action:hover { background: #3c3836; color: #ebdbb2; }
.theme-gruvbox-dark .btn-input-action:focus { background: #3c3836; color: #ebdbb2; }
.theme-gruvbox-dark .btn-action-traces { color: #fabd2f; }
.theme-gruvbox-dark .btn-action-traces:hover { background: #3c3836; color: #fe8019; }
.theme-gruvbox-dark .btn-action-traces:focus { background: #3c3836; color: #fe8019; }
.theme-gruvbox-dark .btn-action-cancel:hover { background: #3d2020; color: #fb4934; }
.theme-gruvbox-dark .btn-action-cancel:focus { background: #3d2020; }
.theme-gruvbox-dark .btn-action-exit { color: #a89984; }
.theme-gruvbox-dark .btn-action-exit:hover { background: #3d2020; color: #fb4934; }

.theme-gruvbox-dark #suggestions { background: #1d2021; border-top: solid #3c3836; scrollbar-color: #fabd2f #282828; }
.theme-gruvbox-dark .suggestion-item { color: #a89984; }
.theme-gruvbox-dark .suggestion-item.highlighted { color: #fbf1c7; background: #504945; }

.theme-gruvbox-dark .code-block { background: #282828; color: #d5c4a1; border: tall #3c3836; }
.theme-gruvbox-dark .shell-escape-card { background: #282828; border: solid #3c3836; }
.theme-gruvbox-dark .shell-card-header { background: #3c3836; color: #d5c4a1; border-bottom: solid #3c3836; }
.theme-gruvbox-dark .shell-output-text { color: #d5c4a1; }
.theme-gruvbox-dark .spinner { color: #fabd2f; }
.theme-gruvbox-dark .summary-box { background: #282828; border: solid #504945; color: #d5c4a1; }
.theme-gruvbox-dark .dev-trace-text { color: #8ec07c; background: #1d2021; border: solid #3c3836; border-left: solid #fb4934; }
.theme-gruvbox-dark #welcome-screen { background: #282828; }
.theme-gruvbox-dark .welcome-logo { color: #fabd2f; }
.theme-gruvbox-dark .welcome-version { color: #ebdbb2; }
.theme-gruvbox-dark .welcome-subtitle { color: #a89984; }
.theme-gruvbox-dark .welcome-hint { color: #504945; }
.theme-gruvbox-dark .welcome-separator { color: #3c3836; }
.theme-gruvbox-dark #approval-bar { border-left: solid #fabd2f; }
.theme-gruvbox-dark #approval-bar .approval-label { color: #fabd2f; }
.theme-gruvbox-dark .approve-btn { color: #b8bb26; }
.theme-gruvbox-dark .approve-btn:hover { background: #1a3a1a; }
.theme-gruvbox-dark .approve-btn:focus { background: #1a3a1a; }
.theme-gruvbox-dark .deny-btn { color: #fb4934; }
.theme-gruvbox-dark .deny-btn:hover { background: #3d2020; }
.theme-gruvbox-dark .deny-btn:focus { background: #3d2020; }
.theme-gruvbox-dark #parallel-bar { background: #282828; border: solid #d3869b; }
.theme-gruvbox-dark #parallel-bar .parallel-title { color: #d3869b; }

.theme-gruvbox-dark #diff-dialog, .theme-gruvbox-dark #file-dialog, .theme-gruvbox-dark #session-dialog, .theme-gruvbox-dark #shortcuts-dialog, .theme-gruvbox-dark .tv-box { background: #282828; border: solid #3c3836; }
.theme-gruvbox-dark #diff-dialog, .theme-gruvbox-dark #file-dialog { border-top: solid #fabd2f; }
.theme-gruvbox-dark #session-dialog { border-top: solid #d3869b; }
.theme-gruvbox-dark #shortcuts-dialog, .theme-gruvbox-dark .tv-box { border-top: solid #fabd2f; }
.theme-gruvbox-dark #diff-header, .theme-gruvbox-dark #file-header, .theme-gruvbox-dark #session-header, .theme-gruvbox-dark .tv-header { border-bottom: solid #3c3836; }
.theme-gruvbox-dark #diff-title, .theme-gruvbox-dark #file-title { color: #fabd2f; }
.theme-gruvbox-dark #session-title { color: #d3869b; }
.theme-gruvbox-dark .tv-title { color: #fabd2f; }
.theme-gruvbox-dark #diff-options, .theme-gruvbox-dark #session-options, .theme-gruvbox-dark DirectoryTree { background: #282828; }
.theme-gruvbox-dark #tree-container { border-right: solid #3c3836; }
.theme-gruvbox-dark #preview-container { scrollbar-color: #fabd2f #282828; }
.theme-gruvbox-dark #file-preview { color: #d5c4a1; }
.theme-gruvbox-dark #diff-file-list, .theme-gruvbox-dark #session-list-col { border-right: solid #3c3836; }
.theme-gruvbox-dark .shortcuts-header { color: #fabd2f; border-bottom: solid #3c3836; }

/* ── Rose Pine ─────────────────────────────────────────────────────────── */
.theme-rose-pine { background: #191724; }
.theme-rose-pine #agent-dashboard { background: #1f1d2e; border-left: solid #26233a; }
.theme-rose-pine .dashboard-title { color: #9ccfd8; }
.theme-rose-pine .agent-entry { background: #1f1d2e; border: solid #26233a; }
.theme-rose-pine .agent-status { color: #908caa; }
.theme-rose-pine .agent-task { color: #908caa; }
.theme-rose-pine .agent-tools { color: #9ccfd8; }
.theme-rose-pine .agent-progress { color: #31748f; }
.theme-rose-pine .dashboard-separator { color: #26233a; }
.theme-rose-pine .dashboard-stats { color: #908caa; }
.theme-rose-pine .active-color { color: #31748f; }
.theme-rose-pine .idle-color { color: #908caa; }
.theme-rose-pine .error-color { color: #eb6f92; }
.theme-rose-pine .completed-color { color: #9ccfd8; }

.theme-rose-pine #messages { scrollbar-color: #eb6f92 #1f1d2e; scrollbar-color-hover: #c4a7e7 #1f1d2e; }
.theme-rose-pine #new-messages-badge { background: #393552; }
.theme-rose-pine .msg-user { border-left: solid #eb6f92; color: #eb6f92; }
.theme-rose-pine .msg-assistant { color: #e0def4; }
.theme-rose-pine .msg-system { color: #f6c177; border-left: solid #f6c177; }
.theme-rose-pine .msg-error-inline { color: #eb6f92; border-left: solid #eb6f92; }
.theme-rose-pine .msg-notice-inline { color: #f6c177; border-left: solid #f6c177; }
.theme-rose-pine .msg-meta { color: #6e6a86; }
.theme-rose-pine .msg-parallel { color: #c4a7e7; border-left: solid #c4a7e7; }

.theme-rose-pine .exchange-box { border: solid #26233a; }
.theme-rose-pine .exchange-box--user { border-left: solid #eb6f92; }
.theme-rose-pine .exchange-box--delegate { border-left: solid #c4a7e7; }
.theme-rose-pine .exchange-box--chain { border-left: solid #393552; }
.theme-rose-pine .exchange-box--orchestrate { border-left: solid #31748f; }
.theme-rose-pine .exchange-box--plan { border-left: #f6c177; }
.theme-rose-pine .exchange-box--command { border-left: solid #9ccfd8; }
.theme-rose-pine .exchange-prompt-header { color: #c4c0e4; border-bottom: solid #26233a; }
.theme-rose-pine .exchange-body { color: #e0def4; }
.theme-rose-pine .exchange-divider { color: #26233a; }
.theme-rose-pine .exchange-prompt { color: #eb6f92; border-bottom: solid #26233a; }
.theme-rose-pine .exchange-assistant { color: #e0def4; }
.theme-rose-pine .agent-tag { color: #9ccfd8; }
.theme-rose-pine .thinking-text { color: #908caa; border-left: solid #c4a7e7; }
.theme-rose-pine .trace-badge { color: #393552; }
.theme-rose-pine .trace-action-bar { background: #1f1d2e; border-top: solid #26233a; }
.theme-rose-pine .btn-view-trace { background: #1f1d2e; color: #eb6f92; }
.theme-rose-pine .btn-view-trace:hover { background: #26233a; color: #c4a7e7; }
.theme-rose-pine .btn-view-trace:focus { background: #26233a; color: #c4a7e7; }
.theme-rose-pine .plan-text { color: #31748f; border-left: solid #31748f; }

.theme-rose-pine .collapsible-card-box { border: solid #26233a; color: #e0def4; }
.theme-rose-pine .card-header { color: #c4c0e4; border-bottom: solid #26233a; }
.theme-rose-pine .card-body { color: #e0def4; }
.theme-rose-pine Collapsible { background: #1f1d2e; border: solid #26233a; }
.theme-rose-pine Collapsible .collapsible-title { background: #1f1d2e; color: #eb6f92; }
.theme-rose-pine Collapsible .collapsible-body { background: #1f1d2e; color: #e0def4; scrollbar-color: #eb6f92 #1f1d2e; }

.theme-rose-pine .btn-copy-code { background: #1f1d2e; color: #908caa; }
.theme-rose-pine .btn-copy-code:hover { background: #26233a; color: #eb6f92; }
.theme-rose-pine .btn-copy-code:focus { background: #26233a; color: #eb6f92; }

.theme-rose-pine #input-area { background: #191724; border-top: solid #26233a; }
.theme-rose-pine #msg-input { background: #191724; border-top: solid #26233a; color: #c4c0e4; }
.theme-rose-pine #msg-input:focus { border-top: solid #eb6f92; color: #e0def4; background: #191724; }
.theme-rose-pine .btn-input-action { background: #1f1d2e; color: #908caa; }
.theme-rose-pine .btn-input-action:hover { background: #26233a; color: #e0def4; }
.theme-rose-pine .btn-input-action:focus { background: #26233a; color: #e0def4; }
.theme-rose-pine .btn-action-traces { color: #eb6f92; }
.theme-rose-pine .btn-action-traces:hover { background: #26233a; color: #c4a7e7; }
.theme-rose-pine .btn-action-traces:focus { background: #26233a; color: #c4a7e7; }
.theme-rose-pine .btn-action-cancel:hover { background: #3d2530; color: #eb6f92; }
.theme-rose-pine .btn-action-cancel:focus { background: #3d2530; }
.theme-rose-pine .btn-action-exit { color: #908caa; }
.theme-rose-pine .btn-action-exit:hover { background: #3d2530; color: #eb6f92; }

.theme-rose-pine #suggestions { background: #191724; border-top: solid #26233a; scrollbar-color: #eb6f92 #1f1d2e; }
.theme-rose-pine .suggestion-item { color: #908caa; }
.theme-rose-pine .suggestion-item.highlighted { color: #e0def4; background: #393552; }

.theme-rose-pine .code-block { background: #1f1d2e; color: #c4c0e4; border: tall #26233a; }
.theme-rose-pine .shell-escape-card { background: #1f1d2e; border: solid #26233a; }
.theme-rose-pine .shell-card-header { background: #26233a; color: #c4c0e4; border-bottom: solid #26233a; }
.theme-rose-pine .shell-output-text { color: #c4c0e4; }
.theme-rose-pine .spinner { color: #eb6f92; }
.theme-rose-pine .summary-box { background: #1f1d2e; border: solid #393552; color: #c4c0e4; }
.theme-rose-pine .dev-trace-text { color: #9ccfd8; background: #191724; border: solid #26233a; border-left: solid #eb6f92; }
.theme-rose-pine #welcome-screen { background: #1f1d2e; }
.theme-rose-pine .welcome-logo { color: #eb6f92; }
.theme-rose-pine .welcome-version { color: #e0def4; }
.theme-rose-pine .welcome-subtitle { color: #908caa; }
.theme-rose-pine .welcome-hint { color: #6e6a86; }
.theme-rose-pine .welcome-separator { color: #26233a; }
.theme-rose-pine #approval-bar { border-left: solid #f6c177; }
.theme-rose-pine #approval-bar .approval-label { color: #f6c177; }
.theme-rose-pine .approve-btn { color: #31748f; }
.theme-rose-pine .approve-btn:hover { background: #1a3a2a; }
.theme-rose-pine .approve-btn:focus { background: #1a3a2a; }
.theme-rose-pine .deny-btn { color: #eb6f92; }
.theme-rose-pine .deny-btn:hover { background: #3d2530; }
.theme-rose-pine .deny-btn:focus { background: #3d2530; }
.theme-rose-pine #parallel-bar { background: #1f1d2e; border: solid #c4a7e7; }
.theme-rose-pine #parallel-bar .parallel-title { color: #c4a7e7; }

.theme-rose-pine #diff-dialog, .theme-rose-pine #file-dialog, .theme-rose-pine #session-dialog, .theme-rose-pine #shortcuts-dialog, .theme-rose-pine .tv-box { background: #1f1d2e; border: solid #26233a; }
.theme-rose-pine #diff-dialog, .theme-rose-pine #file-dialog { border-top: solid #eb6f92; }
.theme-rose-pine #session-dialog { border-top: solid #c4a7e7; }
.theme-rose-pine #shortcuts-dialog, .theme-rose-pine .tv-box { border-top: solid #eb6f92; }
.theme-rose-pine #diff-header, .theme-rose-pine #file-header, .theme-rose-pine #session-header, .theme-rose-pine .tv-header { border-bottom: solid #26233a; }
.theme-rose-pine #diff-title, .theme-rose-pine #file-title { color: #eb6f92; }
.theme-rose-pine #session-title { color: #c4a7e7; }
.theme-rose-pine .tv-title { color: #eb6f92; }
.theme-rose-pine #diff-options, .theme-rose-pine #session-options, .theme-rose-pine DirectoryTree { background: #1f1d2e; }
.theme-rose-pine #tree-container { border-right: solid #26233a; }
.theme-rose-pine #preview-container { scrollbar-color: #eb6f92 #1f1d2e; }
.theme-rose-pine #file-preview { color: #c4c0e4; }
.theme-rose-pine #diff-file-list, .theme-rose-pine #session-list-col { border-right: solid #26233a; }
.theme-rose-pine .shortcuts-header { color: #eb6f92; border-bottom: solid #26233a; }

/* ═══════════════════════════════════════════════════════════════════════════
   TRACE VIEWER internal element theme overrides
   ═══════════════════════════════════════════════════════════════════════════ */

/* Nord Trace Viewer */
.theme-nord .tv-header { background: #2e3440; border-bottom: solid #434c5e; }
.theme-nord .tv-btn { background: #2e3440; color: #a0a8b8; }
.theme-nord .tv-btn:hover { background: #3b4252; color: #eceff4; }
.theme-nord .tv-btn:focus { background: #3b4252; color: #eceff4; }
.theme-nord .tv-btn-export { color: #d08770; }
.theme-nord .tv-btn-close { color: #bf616a; }
.theme-nord .tv-shortcuts { background: #2e3440; border-bottom: solid #434c5e; color: #5e6b7e; }
.theme-nord TabbedContent { background: #2e3440; }
.theme-nord TabPane { background: #2e3440; }
.theme-nord .tv-tab-scroll { scrollbar-color: #88c0d0 #2e3440; }
.theme-nord .tv-section-head { color: #88c0d0; border-left: solid #88c0d0; }
.theme-nord .tv-empty { color: #5e6b7e; }
.theme-nord .tv-event { border-left: solid #434c5e; background: #2e3440; }
.theme-nord .tv-event:hover { border-left: solid #88c0d0; background: #3b4252; }
.theme-nord .tv-stat-box { background: #3b4252; border: solid #434c5e; }
.theme-nord .tv-stat-label { color: #a0a8b8; }
.theme-nord .tv-timeline-row { color: #a0a8b8; }
.theme-nord .tv-timeline-row:hover { background: #3b4252; color: #eceff4; }
.theme-nord .tv-thinking-block { background: #2d2040; border-left: solid #b48ead; color: #b48ead; }
.theme-nord .tv-response-block { background: #1a2a3a; border-left: solid #88c0d0; color: #eceff4; }
.theme-nord .tv-graph-block { background: #2e3440; border: solid #434c5e; border-left: solid #88c0d0; color: #8fbcbb; }
.theme-nord .tv-export-note { background: #2a3a2a; color: #a3be8c; }

/* Dracula Trace Viewer */
.theme-dracula .tv-header { background: #282a36; border-bottom: solid #44475a; }
.theme-dracula .tv-btn { background: #282a36; color: #6272a4; }
.theme-dracula .tv-btn:hover { background: #343746; color: #f8f8f2; }
.theme-dracula .tv-btn:focus { background: #343746; color: #f8f8f2; }
.theme-dracula .tv-btn-export { color: #ffb86c; }
.theme-dracula .tv-btn-close { color: #ff5555; }
.theme-dracula .tv-shortcuts { background: #282a36; border-bottom: solid #44475a; color: #44475a; }
.theme-dracula TabbedContent { background: #282a36; }
.theme-dracula TabPane { background: #282a36; }
.theme-dracula .tv-tab-scroll { scrollbar-color: #bd93f9 #282a36; }
.theme-dracula .tv-section-head { color: #bd93f9; border-left: solid #bd93f9; }
.theme-dracula .tv-empty { color: #44475a; }
.theme-dracula .tv-event { border-left: solid #44475a; background: #282a36; }
.theme-dracula .tv-event:hover { border-left: solid #bd93f9; background: #343746; }
.theme-dracula .tv-stat-box { background: #343746; border: solid #44475a; }
.theme-dracula .tv-stat-label { color: #6272a4; }
.theme-dracula .tv-timeline-row { color: #6272a4; }
.theme-dracula .tv-timeline-row:hover { background: #343746; color: #f8f8f2; }
.theme-dracula .tv-thinking-block { background: #2a1a3a; border-left: solid #ff79c6; color: #ff79c6; }
.theme-dracula .tv-response-block { background: #1a2a3a; border-left: solid #8be9fd; color: #f8f8f2; }
.theme-dracula .tv-graph-block { background: #282a36; border: solid #44475a; border-left: solid #bd93f9; color: #bd93f9; }
.theme-dracula .tv-export-note { background: #1a3a1a; color: #50fa7b; }

/* Monokai Trace Viewer */
.theme-monokai .tv-header { background: #272822; border-bottom: solid #3e3d32; }
.theme-monokai .tv-btn { background: #272822; color: #75715e; }
.theme-monokai .tv-btn:hover { background: #3e3d32; color: #f8f8f2; }
.theme-monokai .tv-btn:focus { background: #3e3d32; color: #f8f8f2; }
.theme-monokai .tv-btn-export { color: #fd971f; }
.theme-monokai .tv-btn-close { color: #f92672; }
.theme-monokai .tv-shortcuts { background: #272822; border-bottom: solid #3e3d32; color: #49483e; }
.theme-monokai TabbedContent { background: #272822; }
.theme-monokai TabPane { background: #272822; }
.theme-monokai .tv-tab-scroll { scrollbar-color: #a6e22e #272822; }
.theme-monokai .tv-section-head { color: #a6e22e; border-left: solid #a6e22e; }
.theme-monokai .tv-empty { color: #49483e; }
.theme-monokai .tv-event { border-left: solid #3e3d32; background: #272822; }
.theme-monokai .tv-event:hover { border-left: solid #a6e22e; background: #3e3d32; }
.theme-monokai .tv-stat-box { background: #3e3d32; border: solid #3e3d32; }
.theme-monokai .tv-stat-label { color: #75715e; }
.theme-monokai .tv-timeline-row { color: #75715e; }
.theme-monokai .tv-timeline-row:hover { background: #3e3d32; color: #f8f8f2; }
.theme-monokai .tv-thinking-block { background: #2a1a3a; border-left: solid #ae81ff; color: #ae81ff; }
.theme-monokai .tv-response-block { background: #1a2a2a; border-left: solid #66d9ef; color: #f8f8f2; }
.theme-monokai .tv-graph-block { background: #272822; border: solid #3e3d32; border-left: solid #66d9ef; color: #66d9ef; }
.theme-monokai .tv-export-note { background: #1a3a1a; color: #a6e22e; }

/* Tokyo Night Trace Viewer */
.theme-tokyo-night .tv-header { background: #1a1b26; border-bottom: solid #292e42; }
.theme-tokyo-night .tv-btn { background: #1a1b26; color: #565f89; }
.theme-tokyo-night .tv-btn:hover { background: #24283b; color: #c0caf5; }
.theme-tokyo-night .tv-btn:focus { background: #24283b; color: #c0caf5; }
.theme-tokyo-night .tv-btn-export { color: #ff9e64; }
.theme-tokyo-night .tv-btn-close { color: #f7768e; }
.theme-tokyo-night .tv-shortcuts { background: #1a1b26; border-bottom: solid #292e42; color: #3b4261; }
.theme-tokyo-night TabbedContent { background: #1a1b26; }
.theme-tokyo-night TabPane { background: #1a1b26; }
.theme-tokyo-night .tv-tab-scroll { scrollbar-color: #7aa2f7 #1a1b26; }
.theme-tokyo-night .tv-section-head { color: #7aa2f7; border-left: solid #7aa2f7; }
.theme-tokyo-night .tv-empty { color: #3b4261; }
.theme-tokyo-night .tv-event { border-left: solid #292e42; background: #1a1b26; }
.theme-tokyo-night .tv-event:hover { border-left: solid #7aa2f7; background: #24283b; }
.theme-tokyo-night .tv-stat-box { background: #24283b; border: solid #292e42; }
.theme-tokyo-night .tv-stat-label { color: #565f89; }
.theme-tokyo-night .tv-timeline-row { color: #565f89; }
.theme-tokyo-night .tv-timeline-row:hover { background: #24283b; color: #c0caf5; }
.theme-tokyo-night .tv-thinking-block { background: #2a1a3a; border-left: solid #bb9af7; color: #bb9af7; }
.theme-tokyo-night .tv-response-block { background: #1a2a3a; border-left: solid #7aa2f7; color: #c0caf5; }
.theme-tokyo-night .tv-graph-block { background: #1a1b26; border: solid #292e42; border-left: solid #7aa2f7; color: #89b4fa; }
.theme-tokyo-night .tv-export-note { background: #1a3a1a; color: #9ece6a; }

/* Solarized Dark Trace Viewer */
.theme-solarized-dark .tv-header { background: #002b36; border-bottom: solid #073642; }
.theme-solarized-dark .tv-btn { background: #002b36; color: #657b83; }
.theme-solarized-dark .tv-btn:hover { background: #073642; color: #839496; }
.theme-solarized-dark .tv-btn:focus { background: #073642; color: #839496; }
.theme-solarized-dark .tv-btn-export { color: #cb4b16; }
.theme-solarized-dark .tv-btn-close { color: #dc322f; }
.theme-solarized-dark .tv-shortcuts { background: #002b36; border-bottom: solid #073642; color: #586e75; }
.theme-solarized-dark TabbedContent { background: #002b36; }
.theme-solarized-dark TabPane { background: #002b36; }
.theme-solarized-dark .tv-tab-scroll { scrollbar-color: #268bd2 #002b36; }
.theme-solarized-dark .tv-section-head { color: #268bd2; border-left: solid #268bd2; }
.theme-solarized-dark .tv-empty { color: #586e75; }
.theme-solarized-dark .tv-event { border-left: solid #073642; background: #002b36; }
.theme-solarized-dark .tv-event:hover { border-left: solid #268bd2; background: #073642; }
.theme-solarized-dark .tv-stat-box { background: #073642; border: solid #073642; }
.theme-solarized-dark .tv-stat-label { color: #657b83; }
.theme-solarized-dark .tv-timeline-row { color: #657b83; }
.theme-solarized-dark .tv-timeline-row:hover { background: #073642; color: #839496; }
.theme-solarized-dark .tv-thinking-block { background: #1a1a3a; border-left: solid #6c71c4; color: #6c71c4; }
.theme-solarized-dark .tv-response-block { background: #0a2a3a; border-left: solid #268bd2; color: #839496; }
.theme-solarized-dark .tv-graph-block { background: #002b36; border: solid #073642; border-left: solid #2aa198; color: #2aa198; }
.theme-solarized-dark .tv-export-note { background: #0a3a0a; color: #859900; }

/* Cyberpunk Trace Viewer */
.theme-cyberpunk .tv-header { background: #10121d; border-bottom: solid #202637; }
.theme-cyberpunk .tv-btn { background: #10121d; color: #008094; }
.theme-cyberpunk .tv-btn:hover { background: #181c2a; color: #00f0ff; }
.theme-cyberpunk .tv-btn:focus { background: #181c2a; color: #00f0ff; }
.theme-cyberpunk .tv-btn-export { color: #ff6600; }
.theme-cyberpunk .tv-btn-close { color: #ff003c; }
.theme-cyberpunk .tv-shortcuts { background: #10121d; border-bottom: solid #202637; color: #005060; }
.theme-cyberpunk TabbedContent { background: #10121d; }
.theme-cyberpunk TabPane { background: #10121d; }
.theme-cyberpunk .tv-tab-scroll { scrollbar-color: #00f0ff #10121d; }
.theme-cyberpunk .tv-section-head { color: #00f0ff; border-left: solid #00f0ff; }
.theme-cyberpunk .tv-empty { color: #005060; }
.theme-cyberpunk .tv-event { border-left: solid #202637; background: #10121d; }
.theme-cyberpunk .tv-event:hover { border-left: solid #00f0ff; background: #181c2a; }
.theme-cyberpunk .tv-stat-box { background: #181c2a; border: solid #202637; }
.theme-cyberpunk .tv-stat-label { color: #008094; }
.theme-cyberpunk .tv-timeline-row { color: #008094; }
.theme-cyberpunk .tv-timeline-row:hover { background: #181c2a; color: #00f0ff; }
.theme-cyberpunk .tv-thinking-block { background: #1a0a2a; border-left: solid #ff00ff; color: #ff00ff; }
.theme-cyberpunk .tv-response-block { background: #0a1a2a; border-left: solid #00f0ff; color: #00f0ff; }
.theme-cyberpunk .tv-graph-block { background: #10121d; border: solid #202637; border-left: solid #ffee00; color: #ffee00; }
.theme-cyberpunk .tv-export-note { background: #0a3a0a; color: #39ff14; }

/* Catppuccin Mocha Trace Viewer */
.theme-catppuccin-mocha .tv-header { background: #181825; border-bottom: solid #313244; }
.theme-catppuccin-mocha .tv-btn { background: #181825; color: #6c7086; }
.theme-catppuccin-mocha .tv-btn:hover { background: #313244; color: #cdd6f4; }
.theme-catppuccin-mocha .tv-btn:focus { background: #313244; color: #cdd6f4; }
.theme-catppuccin-mocha .tv-btn-export { color: #fab387; }
.theme-catppuccin-mocha .tv-btn-close { color: #f38ba8; }
.theme-catppuccin-mocha .tv-shortcuts { background: #181825; border-bottom: solid #313244; color: #45475a; }
.theme-catppuccin-mocha TabbedContent { background: #181825; }
.theme-catppuccin-mocha TabPane { background: #181825; }
.theme-catppuccin-mocha .tv-tab-scroll { scrollbar-color: #cba6f7 #181825; }
.theme-catppuccin-mocha .tv-section-head { color: #cba6f7; border-left: solid #cba6f7; }
.theme-catppuccin-mocha .tv-empty { color: #45475a; }
.theme-catppuccin-mocha .tv-event { border-left: solid #313244; background: #181825; }
.theme-catppuccin-mocha .tv-event:hover { border-left: solid #cba6f7; background: #313244; }
.theme-catppuccin-mocha .tv-stat-box { background: #313244; border: solid #313244; }
.theme-catppuccin-mocha .tv-stat-label { color: #6c7086; }
.theme-catppuccin-mocha .tv-timeline-row { color: #6c7086; }
.theme-catppuccin-mocha .tv-timeline-row:hover { background: #313244; color: #cdd6f4; }
.theme-catppuccin-mocha .tv-thinking-block { background: #2a1a3a; border-left: solid #f5c2e7; color: #cba6f7; }
.theme-catppuccin-mocha .tv-response-block { background: #1a2a3a; border-left: solid #89b4fa; color: #cdd6f4; }
.theme-catppuccin-mocha .tv-graph-block { background: #181825; border: solid #313244; border-left: solid #89dceb; color: #89dceb; }
.theme-catppuccin-mocha .tv-export-note { background: #1a3a1a; color: #a6e3a1; }

/* Gruvbox Dark Trace Viewer */
.theme-gruvbox-dark .tv-header { background: #282828; border-bottom: solid #3c3836; }
.theme-gruvbox-dark .tv-btn { background: #282828; color: #a89984; }
.theme-gruvbox-dark .tv-btn:hover { background: #3c3836; color: #ebdbb2; }
.theme-gruvbox-dark .tv-btn:focus { background: #3c3836; color: #ebdbb2; }
.theme-gruvbox-dark .tv-btn-export { color: #fe8019; }
.theme-gruvbox-dark .tv-btn-close { color: #fb4934; }
.theme-gruvbox-dark .tv-shortcuts { background: #282828; border-bottom: solid #3c3836; color: #504945; }
.theme-gruvbox-dark TabbedContent { background: #282828; }
.theme-gruvbox-dark TabPane { background: #282828; }
.theme-gruvbox-dark .tv-tab-scroll { scrollbar-color: #fabd2f #282828; }
.theme-gruvbox-dark .tv-section-head { color: #fabd2f; border-left: solid #fabd2f; }
.theme-gruvbox-dark .tv-empty { color: #504945; }
.theme-gruvbox-dark .tv-event { border-left: solid #3c3836; background: #282828; }
.theme-gruvbox-dark .tv-event:hover { border-left: solid #fabd2f; background: #3c3836; }
.theme-gruvbox-dark .tv-stat-box { background: #3c3836; border: solid #3c3836; }
.theme-gruvbox-dark .tv-stat-label { color: #a89984; }
.theme-gruvbox-dark .tv-timeline-row { color: #a89984; }
.theme-gruvbox-dark .tv-timeline-row:hover { background: #3c3836; color: #ebdbb2; }
.theme-gruvbox-dark .tv-thinking-block { background: #2a1a3a; border-left: solid #d3869b; color: #d3869b; }
.theme-gruvbox-dark .tv-response-block { background: #1a2a2a; border-left: solid #8ec07c; color: #ebdbb2; }
.theme-gruvbox-dark .tv-graph-block { background: #282828; border: solid #3c3836; border-left: solid #83a598; color: #83a598; }
.theme-gruvbox-dark .tv-export-note { background: #1a3a1a; color: #b8bb26; }

/* Rose Pine Trace Viewer */
.theme-rose-pine .tv-header { background: #1f1d2e; border-bottom: solid #26233a; }
.theme-rose-pine .tv-btn { background: #1f1d2e; color: #908caa; }
.theme-rose-pine .tv-btn:hover { background: #26233a; color: #e0def4; }
.theme-rose-pine .tv-btn:focus { background: #26233a; color: #e0def4; }
.theme-rose-pine .tv-btn-export { color: #ea9a97; }
.theme-rose-pine .tv-btn-close { color: #eb6f92; }
.theme-rose-pine .tv-shortcuts { background: #1f1d2e; border-bottom: solid #26233a; color: #6e6a86; }
.theme-rose-pine TabbedContent { background: #1f1d2e; }
.theme-rose-pine TabPane { background: #1f1d2e; }
.theme-rose-pine .tv-tab-scroll { scrollbar-color: #eb6f92 #1f1d2e; }
.theme-rose-pine .tv-section-head { color: #eb6f92; border-left: solid #eb6f92; }
.theme-rose-pine .tv-empty { color: #6e6a86; }
.theme-rose-pine .tv-event { border-left: solid #26233a; background: #1f1d2e; }
.theme-rose-pine .tv-event:hover { border-left: solid #eb6f92; background: #26233a; }
.theme-rose-pine .tv-stat-box { background: #26233a; border: solid #26233a; }
.theme-rose-pine .tv-stat-label { color: #908caa; }
.theme-rose-pine .tv-timeline-row { color: #908caa; }
.theme-rose-pine .tv-timeline-row:hover { background: #26233a; color: #e0def4; }
.theme-rose-pine .tv-thinking-block { background: #2a1a3a; border-left: solid #c4a7e7; color: #c4a7e7; }
.theme-rose-pine .tv-response-block { background: #1a2a3a; border-left: solid #9ccfd8; color: #e0def4; }
.theme-rose-pine .tv-graph-block { background: #1f1d2e; border: solid #26233a; border-left: solid #9ccfd8; color: #9ccfd8; }
.theme-rose-pine .tv-export-note { background: #1a3a1a; color: #31748f; }
"""

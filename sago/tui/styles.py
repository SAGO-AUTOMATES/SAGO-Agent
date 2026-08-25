"""TUI CSS Styles and Themes definition."""

TUI_CSS = """
Screen { background: #0a0d12; }

#main-layout {
    height: 1fr;
}

#messages-parent {
    width: 1fr;
    height: 1fr;
    min-width: 30;
}

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
    scrollbar-color: #30363d #111418;
}
#agent-dashboard.hidden { display: none; }

.dashboard-title {
    color: #58a6ff;
    text-style: bold;
    padding: 0;
    content-align: center middle;
}
.agent-entry {
    background: #161b22;
    border: solid #21262d;
    padding: 0 1;
    margin: 0 0 1 0;
}
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

#messages {
    height: 1fr;
    padding: 1 1;
    overflow-y: scroll;
    overflow-x: hidden;
    scrollbar-size: 1 1;
    scrollbar-color: #388bfd #161b22;
    scrollbar-color-hover: #388bfd #161b22;
    scrollbar-gutter: stable;
    /* Always visible like dev page's VerticalScroll — not hover-only */
}

.msg-user {
    background: transparent;
    border: none;
    border-left: solid #388bfd;
    color: #58a6ff;
    padding: 0 1;
    margin: 0;
}
.msg-assistant {
    background: transparent;
    border: none;
    color: #e6edf3;
    padding: 0;
    margin: 0;
}
.msg-system {
    background: transparent;
    color: #e3b341;
    padding: 0 1;
    margin: 0;
    border: none;
}
.msg-error-inline {
    background: transparent;
    color: #f85149;
    padding: 0 1;
    margin: 1 0 0 0;
    border: none;
    border-left: solid #f85149;
}
.msg-notice-inline {
    background: transparent;
    color: #e3b341;
    padding: 0 1;
    margin: 1 0 0 0;
    border: none;
    border-left: solid #e3b341;
}
.msg-meta { color: #6e7681; padding: 0; }
.msg-parallel {
    background: transparent;
    color: #d2a8ff;
    border: none;
    border-left: solid #d2a8ff;
    padding: 0 1;
    margin: 1 0;
}

.exchange-box {
    background: transparent;
    border: solid #30363d;
    padding: 0;
    margin: 1 0;
    /* Override Textual's Vertical default (height: 1fr) which made every turn
       card stretch to fill the viewport and clip content when multiple cards
       shared the screen. Size strictly by content instead. */
    height: auto;
}
.exchange-box--user {
    border-left: solid #388bfd;
}
.exchange-box--delegate {
    border-left: solid #8957e5;
}
.exchange-box--chain {
    border-left: solid #1f6feb;
}
.exchange-box--orchestrate {
    border-left: solid #2ea043;
}
.exchange-box--plan {
    border-left: solid #d29922;
}
.exchange-box--command {
    border-left: solid #58a6ff;
}

.exchange-prompt-header {
    background: transparent;
    color: #c9d1d9;
    padding: 0 1;
    border-bottom: solid #30363d;
}
.exchange-user-prompt-header {
    background: transparent;
    padding: 0;
    height: auto;
    min-height: 0;
}
.exchange-user-prompt {
    background: transparent;
    padding: 0;
    height: auto;
    min-height: 0;
}
.exchange-body {
    background: transparent;
    padding: 0 1;
    height: auto;
    min-height: 0;
    color: #e6edf3;
}
.exchange-divider {
    color: #30363d;
    padding: 0;
    margin: 0;
    height: auto;
    min-height: 0;
}
.exchange-response {
    background: transparent;
    padding: 0;
    height: auto;
    min-height: 0;
}
.exchange-prompt {
    color: #58a6ff;
    text-style: bold;
    padding: 0;
    border-bottom: solid #30363d;
}
.exchange-assistant {
    color: #e6edf3;
    background: transparent;
    padding: 0;
}
.markdown-body {
    background: transparent;
    padding: 0;
    margin: 0;
}
.agent-tag {
    color: #58a6ff;
    text-style: bold;
    padding: 0;
    margin: 0;
}
.thinking-text {
    color: #8b949e;
    text-style: italic;
    padding: 0 1;
    background: transparent;
    border: none;
    border-left: solid #6e40c9;
    margin: 1 0;
}
.trace-badge {
    color: #484f58;
    padding: 0 1;
    margin: 0;
    width: 1fr;
    content-align: left middle;
    height: 1;
}
.trace-action-bar {
    height: 1;
    margin: 0;
    padding: 0;
    background: #0d1117;
    border-top: solid #21262d;
}
.btn-view-trace {
    height: 1;
    min-width: 12;
    border: none;
    background: #1a2433;
    color: #388bfd;
    padding: 0 1;
}
.btn-view-trace:hover {
    background: #1f3148;
    color: #58a6ff;
}

.plan-text {
    color: #7ee787;
    padding: 0 1;
    background: transparent;
    border: none;
    border-left: solid #2ea043;
    margin: 1 0;
}

.collapsible-card-box {
    background: transparent;
    border: solid #30363d;
    padding: 0;
    margin: 1 0;
    height: auto;
    max-height: 30;
    overflow-y: auto;
    color: #e6edf3;
}
.card-header {
    background: transparent;
    color: #c9d1d9;
    padding: 0 1;
    border-bottom: solid #30363d;
}
.card-body {
    padding: 1 1;
    height: auto;
    max-height: 28;
    overflow-y: auto;
    color: #e6edf3;
}

/* Textual built-in Collapsible widget */
Collapsible {
    border: solid #21262d;
    background: transparent;
    color: #e6edf3;
    margin: 1 0;
    padding: 0;
}
Collapsible:focus {
    border: solid #30363d;
    background: transparent;
}
CollapsibleTitle {
    background: transparent;
    color: #c9d1d9;
    padding: 0 1;
    border-bottom: solid #21262d;
    text-style: none;
}
CollapsibleTitle:hover {
    background: transparent;
    color: #ffffff;
}
CollapsibleTitle:focus {
    background: transparent;
    color: #ffffff;
    text-style: none;
}
CollapsibleTitle:focus > .collapsible-title--text {
    background: transparent;
    color: #ffffff;
}
CollapsibleTitle:focus > .collapsible-title--symbol {
    background: transparent;
    color: #58a6ff;
}
Collapsible > Contents {
    background: transparent;
    color: #e6edf3;
    padding: 1 1;
    height: auto;
}
Collapsible > Contents Static {
    color: #e6edf3;
    background: transparent;
}

/* Tool-call / reasoning / plan collapsibles inside a turn card: collapse the
   vertical chrome so long agent runs stay scannable instead of turning into
   blank-line marathons. */
.exchange-body Collapsible {
    margin: 1 0 0 0;
    padding: 0;
}
.exchange-body Collapsible > Contents {
    padding: 0 1;
}

.code-action-bar {
    height: 1;
    margin: 1 0 0 0;
    padding: 0;
}
.spacer {
    width: 1fr;
}
.btn-copy-code {
    min-width: 12;
    height: 1;
    background: #21262d;
    color: #8b949e;
    border: solid #30363d;
    padding: 0 1;
}
.btn-copy-code:focus, .btn-copy-code:hover {
    background: #30363d;
    color: #58a6ff;
    border: solid #58a6ff;
}

/* Nord Theme */
.theme-nord { background: #242933; }
.theme-nord #agent-dashboard { background: #2e3440; border-left: solid #434c5e; }
.theme-nord .exchange-box { border: solid #434c5e; border-left: solid #88c0d0; }
.theme-nord .exchange-prompt-header { color: #88c0d0; border-bottom: solid #434c5e; }
.theme-nord .exchange-user-prompt { color: #eceff4; }
.theme-nord .exchange-divider { color: #434c5e; }
.theme-nord .exchange-assistant { color: #eceff4; }
.theme-nord .msg-system { border-left: solid #ebcb8b; }
.theme-nord #input-area { background: #242933; border-top: solid #434c5e; }
.theme-nord #msg-input { background: #2e3440; border: solid #434c5e; color: #eceff4; }
.theme-nord #msg-input:focus { border: solid #88c0d0; }

/* Dracula Theme */
.theme-dracula { background: #1e1f29; }
.theme-dracula #agent-dashboard { background: #282a36; border-left: solid #44475a; }
.theme-dracula .exchange-box { border: solid #44475a; border-left: solid #bd93f9; }
.theme-dracula .exchange-prompt-header { color: #bd93f9; border-bottom: solid #6272a4; }
.theme-dracula .exchange-user-prompt { color: #f8f8f2; }
.theme-dracula .exchange-divider { color: #44475a; }
.theme-dracula .exchange-assistant { color: #f8f8f2; }
.theme-dracula .msg-system { border-left: solid #f1fa8c; }
.theme-dracula #input-area { background: #1e1f29; border-top: solid #44475a; }
.theme-dracula #msg-input { background: #282a36; border: solid #44475a; color: #f8f8f2; }
.theme-dracula #msg-input:focus { border: solid #bd93f9; }

/* Monokai Theme */
.theme-monokai { background: #1e1f1c; }
.theme-monokai #agent-dashboard { background: #272822; border-left: solid #3e3d32; }
.theme-monokai .exchange-box { border: solid #3e3d32; border-left: solid #a6e22e; }
.theme-monokai .exchange-prompt-header { color: #a6e22e; border-bottom: solid #49483e; }
.theme-monokai .exchange-user-prompt { color: #f8f8f2; }
.theme-monokai .exchange-divider { color: #3e3d32; }
.theme-monokai .exchange-assistant { color: #f8f8f2; }
.theme-monokai .msg-system { border-left: solid #e6db74; }
.theme-monokai #input-area { background: #1e1f1c; border-top: solid #3e3d32; }
.theme-monokai #msg-input { background: #272822; border: solid #3e3d32; color: #f8f8f2; }
.theme-monokai #msg-input:focus { border: solid #a6e22e; }

/* Tokyo Night Theme */
.theme-tokyo-night { background: #16161e; }
.theme-tokyo-night #agent-dashboard { background: #1a1b26; border-left: solid #292e42; }
.theme-tokyo-night .exchange-box { border: solid #292e42; border-left: solid #7aa2f7; }
.theme-tokyo-night .exchange-prompt-header { color: #7aa2f7; border-bottom: solid #3b4261; }
.theme-tokyo-night .exchange-user-prompt { color: #c0caf5; }
.theme-tokyo-night .exchange-divider { color: #292e42; }
.theme-tokyo-night .exchange-assistant { color: #c0caf5; }
.theme-tokyo-night .msg-system { border-left: solid #e0af68; }
.theme-tokyo-night #input-area { background: #16161e; border-top: solid #292e42; }
.theme-tokyo-night #msg-input { background: #1a1b26; border: solid #292e42; color: #c0caf5; }
.theme-tokyo-night #msg-input:focus { border: solid #7aa2f7; }

/* Solarized Dark Theme */
.theme-solarized-dark { background: #00212b; }
.theme-solarized-dark #agent-dashboard { background: #002b36; border-left: solid #073642; }
.theme-solarized-dark .exchange-box { border: solid #073642; border-left: solid #268bd2; }
.theme-solarized-dark .exchange-prompt-header { color: #268bd2; border-bottom: solid #586e75; }
.theme-solarized-dark .exchange-user-prompt { color: #839496; }
.theme-solarized-dark .exchange-divider { color: #073642; }
.theme-solarized-dark .exchange-assistant { color: #839496; }
.theme-solarized-dark .msg-system { border-left: solid #b58900; }
.theme-solarized-dark #input-area { background: #00212b; border-top: solid #073642; }
.theme-solarized-dark #msg-input { background: #002b36; border: solid #073642; color: #839496; }
.theme-solarized-dark #msg-input:focus { border: solid #268bd2; }

/* Cyberpunk Theme */
.theme-cyberpunk { background: #08090f; }
.theme-cyberpunk #agent-dashboard { background: #10121d; border-left: solid #00f0ff; }
.theme-cyberpunk .exchange-box { border: solid #202637; border-left: solid #ffee00; }
.theme-cyberpunk .exchange-prompt-header { color: #00f0ff; border-bottom: solid #00f0ff; }
.theme-cyberpunk .exchange-user-prompt { color: #00f0ff; }
.theme-cyberpunk .exchange-divider { color: #202637; }
.theme-cyberpunk .exchange-assistant { color: #00f0ff; }
.theme-cyberpunk .msg-system { border-left: solid #00f0ff; }
.theme-cyberpunk #input-area { background: #08090f; border-top: solid #202637; }
.theme-cyberpunk #msg-input { background: #10121d; border: solid #202637; color: #00f0ff; }
.theme-cyberpunk #msg-input:focus { border: solid #00f0ff; }

/* Catppuccin Mocha Theme */
.theme-catppuccin-mocha { background: #1e1e2e; }
.theme-catppuccin-mocha #agent-dashboard { background: #181825; border-left: solid #313244; }
.theme-catppuccin-mocha .exchange-box { border: solid #313244; border-left: solid #cba6f7; }
.theme-catppuccin-mocha .exchange-prompt-header { color: #cba6f7; border-bottom: solid #45475a; }
.theme-catppuccin-mocha .exchange-user-prompt { color: #cdd6f4; }
.theme-catppuccin-mocha .exchange-divider { color: #313244; }
.theme-catppuccin-mocha .exchange-assistant { color: #cdd6f4; }
.theme-catppuccin-mocha .msg-system { border-left: solid #f9e2af; }
.theme-catppuccin-mocha #input-area { background: #1e1e2e; border-top: solid #313244; }
.theme-catppuccin-mocha #msg-input { background: #181825; border: solid #313244; color: #cdd6f4; }
.theme-catppuccin-mocha #msg-input:focus { border: solid #cba6f7; }

/* Gruvbox Dark Theme */
.theme-gruvbox-dark { background: #1d2021; }
.theme-gruvbox-dark #agent-dashboard { background: #282828; border-left: solid #3c3836; }
.theme-gruvbox-dark .exchange-box { border: solid #3c3836; border-left: solid #fabd2f; }
.theme-gruvbox-dark .exchange-prompt-header { color: #fabd2f; border-bottom: solid #504945; }
.theme-gruvbox-dark .exchange-user-prompt { color: #ebdbb2; }
.theme-gruvbox-dark .exchange-divider { color: #3c3836; }
.theme-gruvbox-dark .exchange-assistant { color: #ebdbb2; }
.theme-gruvbox-dark .msg-system { border-left: solid #fabd2f; }
.theme-gruvbox-dark #input-area { background: #1d2021; border-top: solid #3c3836; }
.theme-gruvbox-dark #msg-input { background: #282828; border: solid #3c3836; color: #ebdbb2; }
.theme-gruvbox-dark #msg-input:focus { border: solid #fabd2f; }

/* Rosé Pine Theme */
.theme-rose-pine { background: #191724; }
.theme-rose-pine #agent-dashboard { background: #1f1d2e; border-left: solid #26233a; }
.theme-rose-pine .exchange-box { border: solid #26233a; border-left: solid #eb6f92; }
.theme-rose-pine .exchange-prompt-header { color: #eb6f92; border-bottom: solid #393552; }
.theme-rose-pine .exchange-user-prompt { color: #e0def4; }
.theme-rose-pine .exchange-divider { color: #26233a; }
.theme-rose-pine .exchange-assistant { color: #e0def4; }
.theme-rose-pine .msg-system { border-left: solid #f6c177; }
.theme-rose-pine #input-area { background: #191724; border-top: solid #26233a; }
.theme-rose-pine #msg-input { background: #1f1d2e; border: solid #26233a; color: #e0def4; }
.theme-rose-pine #msg-input:focus { border: solid #eb6f92; }

/* Clean Light Theme */
.theme-light { background: #f6f8fa; }
.theme-light #agent-dashboard { background: #ffffff; border-left: solid #d0d7de; }
.theme-light .exchange-box { border: solid #d0d7de; border-left: solid #0969da; }
.theme-light .exchange-prompt-header { color: #0969da; border-bottom: solid #d0d7de; }
.theme-light .exchange-user-prompt { color: #24292f; }
.theme-light .exchange-divider { color: #d0d7de; }
.theme-light .exchange-assistant { color: #24292f; }
.theme-light .msg-system { border-left: solid #9a6700; color: #24292f; }
.theme-light #input-area { background: #f6f8fa; border-top: solid #d0d7de; }
.theme-light #msg-input { background: #ffffff; border: solid #d0d7de; color: #24292f; }
.theme-light #msg-input:focus { border: solid #0969da; }

/* Theme overrides for approval and parallel bars */
.theme-nord #approval-bar { background: #2e3440; border: solid #ebcb8b; }
.theme-nord #parallel-bar { background: #2e3440; border: solid #88c0d0; }
.theme-dracula #approval-bar { background: #282a36; border: solid #ffb86c; }
.theme-dracula #parallel-bar { background: #282a36; border: solid #bd93f9; }
.theme-monokai #approval-bar { background: #272822; border: solid #e6db74; }
.theme-monokai #parallel-bar { background: #272822; border: solid #a6e22e; }
.theme-tokyo-night #approval-bar { background: #1a1b26; border: solid #e0af68; }
.theme-tokyo-night #parallel-bar { background: #1a1b26; border: solid #7aa2f7; }
.theme-solarized-dark #approval-bar { background: #002b36; border: solid #b58900; }
.theme-solarized-dark #parallel-bar { background: #002b36; border: solid #268bd2; }
.theme-cyberpunk #approval-bar { background: #10121d; border: solid #ffee00; }
.theme-cyberpunk #parallel-bar { background: #10121d; border: solid #00f0ff; }
.theme-catppuccin-mocha #approval-bar { background: #181825; border: solid #f9e2af; }
.theme-catppuccin-mocha #parallel-bar { background: #181825; border: solid #cba6f7; }
.theme-gruvbox-dark #approval-bar { background: #282828; border: solid #fabd2f; }
.theme-gruvbox-dark #parallel-bar { background: #282828; border: solid #b8bb26; }
.theme-rose-pine #approval-bar { background: #1f1d2e; border: solid #f6c177; }
.theme-rose-pine #parallel-bar { background: #1f1d2e; border: solid #eb6f92; }
.theme-light #approval-bar { background: #ffffff; border: solid #9a6700; }
.theme-light #parallel-bar { background: #ffffff; border: solid #8250df; }

.dev-trace-text {
    color: #79c0ff;
    padding: 1 1;
    background: #06090e;
    border: solid #21262d;
    border-left: solid #f85149;
    margin: 1 0;
}

Collapsible {
    background: #0d1117;
    border: solid #21262d;
    margin: 1 0;
    padding: 0;
    height: auto;
}
Collapsible .collapsible-title {
    background: #0d1117;
    color: #58a6ff;
    padding: 0 1;
    text-style: bold;
}
Collapsible .collapsible-body {
    background: #0d1117;
    color: #e6edf3;
    padding: 1 1;
    overflow-y: auto;
    scrollbar-size: 1 1;
    scrollbar-color: #30363d #111418;
}

#input-area {
    height: auto;
    padding: 0 1 1 1;
    background: #0a0d12;
    border-top: solid #21262d;
    margin: 0;
}

#msg-input {
    background: #0a0d12;
    border: none;
    border-top: solid #21262d;
    color: #c9d1d9;
    margin: 0;
    padding: 0 1;
    width: 1fr;
}
#msg-input:focus {
    border: none;
    border-top: solid #388bfd;
    color: #ffffff;
    background: #0a0d12;
}

#input-action-bar {
    height: 1;
    margin: 1 0 0 0;
    overflow-x: auto;
}
.hide-action-bar #input-action-bar {
    display: none;
}
.btn-input-action {
    height: 1;
    min-width: 10;
    border: none;
    background: #161b22;
    color: #8b949e;
    margin-right: 1;
    padding: 0 1;
}
.btn-input-action:hover {
    background: #21262d;
    color: #e6edf3;
}
.btn-action-traces {
    color: #58a6ff;
    text-style: bold;
}
.btn-action-traces:hover {
    background: #1f6feb;
    color: #ffffff;
}
.dev-only-btn {
    display: none;
}
.dev-mode-enabled .dev-only-btn {
    display: block;
}

.btn-action-cancel {
    display: none;
    color: #f85149;
}
.is-thinking .btn-action-cancel {
    display: block;
}
.btn-action-cancel:hover {
    background: #da3633;
    color: #ffffff;
}

.btn-action-exit {
    color: #8b949e;
}
.btn-action-exit:hover {
    background: #da3633;
    color: #ffffff;
}

#suggestions {
    display: none;
    height: auto;
    max-height: 12;
    overflow-y: scroll;
    background: #0a0d12;
    border: none;
    border-top: solid #21262d;
    margin: 0;
    padding: 0 1;
    scrollbar-size-vertical: 1;
    scrollbar-color: #388bfd #161b22;
}
#suggestions.visible { display: block; }

.suggestion-item { color: #8b949e; padding: 0 1; }
.suggestion-item.highlighted {
    color: #ffffff;
    background: #1f6feb;
    text-style: bold;
}

.code-block {
    background: #161b22;
    color: #c9d1d9;
    padding: 1;
    margin: 0 0 1 0;
    border: tall #30363d;
}

.shell-escape-card {
    background: #0d1117;
    border: solid #21262d;
    padding: 0;
    margin: 0 0 1 0;
    height: auto;
    max-height: 20;
    overflow-y: auto;
}

.shell-card-header {
    background: #161b22;
    color: #c9d1d9;
    padding: 0 1;
    text-style: bold;
    border-bottom: solid #21262d;
}

.shell-card-body {
    padding: 1 1;
    height: auto;
    max-height: 18;
    overflow-y: auto;
}

.shell-output-text {
    color: #c9d1d9;
    text-style: none;
}

.spinner { color: #58a6ff; text-style: italic; padding: 0 0 1 0; }

.summary-box {
    background: #161b22;
    border: solid #1f6feb;
    color: #c9d1d9;
    padding: 1;
    margin: 0 0 1 0;
}

#welcome-screen {
    height: 1fr;
    align: center middle;
    content-align: center middle;
    text-align: center;
    background: #0d1117;
}
#welcome-screen.hidden { display: none; }

#messages-parent.has-welcome #messages { display: none; }

.welcome-logo {
    color: #58a6ff;
    text-style: bold;
    text-align: center;
    width: 100%;
    height: auto;
}
.welcome-version {
    color: #ffffff;
    text-style: bold;
    text-align: center;
    width: 100%;
    height: 1;
    margin: 1 0 0 0;
}
.welcome-dev-badge {
    text-align: center;
    width: 100%;
    height: 1;
    margin: 1 0 0 0;
}
.welcome-subtitle {
    color: #8b949e;
    text-align: center;
    width: 100%;
    height: 1;
    margin: 0 0 0 0;
}
.welcome-hint {
    color: #484f58;
    text-align: center;
    width: 100%;
    height: 1;
    margin: 2 0 0 0;
}
.welcome-separator {
    color: #30363d;
    text-align: center;
    width: 100%;
    height: 1;
    margin: 1 0 0 0;
}
.prompt-enhancement-inline {
    width: 100%;
    height: auto;
    padding: 0 1;
    margin: 0 0 1 0;
}

#approval-bar {
    display: none;
    height: auto;
    max-height: 4;
    overflow-y: auto;
    background: transparent;
    border: none;
    border-left: solid #f0883e;
    margin: 0 1 0 1;
    padding: 0 1;
}
#approval-bar.visible { display: block; }

#approval-bar .approval-label {
    color: #f0883e;
    text-style: bold;
    padding: 0;
    max-height: 2;
    overflow-y: auto;
}

#approval-bar .approval-buttons {
    layout: horizontal;
    height: 1;
}

#approval-bar Button {
    margin: 0 1 0 0;
    min-width: 8;
    max-height: 1;
}

.approve-btn { background: transparent; color: #3fb950; border: none; text-style: bold; }
.approve-btn:hover { background: #1a3a2a; }
.approve-btn:focus { border: none; }

.deny-btn { background: transparent; color: #f85149; border: none; text-style: bold; }
.deny-btn:hover { background: #3a1a1a; }
.deny-btn:focus { border: none; }

#parallel-bar {
    display: none;
    height: auto;
    max-height: 10;
    overflow-y: auto;
    background: #161b22;
    border: solid #d2a8ff;
    margin: 0 1 0 1;
    padding: 1;
}
#parallel-bar.visible { display: block; }
#parallel-bar .parallel-title {
    color: #d2a8ff;
    text-style: bold;
    padding: 0 0 1 0;
}
#parallel-bar .parallel-agent {
    padding: 0 0 0 1;
}
"""

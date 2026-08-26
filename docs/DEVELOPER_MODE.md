# SAGO Developer Mode & Telemetry Architecture

Developer Mode enables deep live telemetry, microsecond execution tracing, transparent reasoning inspection, and automatic project-specific session artifact persistence.

> **v0.1.14 — Default ON until beta:** `dev_mode` defaults to `true` on fresh installs (see `sago/config/sago.yaml`, `sago/config/loader.py`, `sago/tui/app.py`). Fresh `sago tui` shows Inspector without `/dev on`. **TODO: flip to false at 1.0**.

---

## 🛠️ Configuration & Activation

Developer Mode is **ON by default until v1.0** — no manual toggle needed. To explicitly control:

### 0. Default (v0.1.14 beta) — No Action Needed
Fresh install: `dev_mode: true` (`sago.yaml:64`, `loader.py SettingsConfig dev_mode: True # TODO: flip to false at 1.0`, `app.py developer_mode: True`, `settings.json dev_mode: True`). `DevTracer.is_enabled=True` on `on_mount`; Inspector (`F2`) shows events immediately. After 1.0, defaults will flip to `false` and require explicit enable.

### 1. User Configuration File (`~/.sago/config.json` or `~/.sago/settings.json`)
Manually add `"dev_mode": true` to your user configuration (or `false` to disable early):

```json
{
  "dev_mode": true
}
```

Or via YAML in `~/.sago/config.yaml`:
```yaml
settings:
  dev_mode: true
```

### 2. Environment Variable
```bash
export SAGO_DEV_MODE=1
# or
export DEV_MODE=true
# to force OFF (even with default ON):
export SAGO_DEV_MODE=0
```

---

## 🟢 Home Screen Visual Indicator

When Developer Mode is enabled:
- The SAGO TUI welcome home screen renders a green indicator dot badge directly beneath the header:
  ```text
  ● Dev Mode ON  ─ F2 Dev Traces Active
  ```
- Dev Traces shortcuts (`F2`) and the dedicated action bar button (`⚡ Dev Traces [F2]`) are active.

---

## 📁 Automatic Live Session Artifacts

When Developer Mode is enabled, SAGO **automatically and continuously** generates and updates complete session artifacts in the project-specific workspace folder:

```text
<project_root>/
└── .sago/
    └── data/
        └── <session_id>/
            ├── chat_export.md   # Complete Markdown conversation transcript with reasoning blocks
            ├── trace.md         # Formatted Mermaid interaction graph & hierarchy trace report
            └── trace.json       # Structured machine-readable microsecond telemetry stream
```

### Generated Files Breakdown:
1. **`chat_export.md`**:
   - Clean, comprehensive Markdown transcript of all turns (User, Assistant, Delegated Agents, System).
   - Injected specialist agent personas (`@nextjs-engineer`, `@azure-engineer`, `@spring-boot-engineer`).
   - Collapsible reasoning & architectural analysis (`<details><summary>Technical Reasoning</summary>...</details>`).
   - Formatted code blocks and tool input/output logs.

2. **`trace.md`**:
   - **Mermaid Flowchart**: Visual interaction map linking user prompts, routing decisions, tool dispatches, and LLM payloads.
   - **Call Hierarchy**: ASCII execution tree.
   - **Performance Table**: Latency and duration in milliseconds per operation.
   - Detailed event payloads with JSON inputs/outputs.

3. **`trace.json`**:
   - Complete event stream containing nodes, edges, timestamps, durations, and status codes.

---

## 🚪 Clean Session Exit & Resumption

When exiting or detaching a session, SAGO notifies the user of saved artifacts:

```text
Session saved: 4f8b2c9a (12 messages)
Resume: sago tui --resume 4f8b2c9a
Or: /load 4f8b2c9a

📁 [Dev Mode] Session artifacts generated:
   ↳ .sago/data/4f8b2c9a/chat_export.md
   ↳ .sago/data/4f8b2c9a/trace.md
   ↳ .sago/data/4f8b2c9a/trace.json
```

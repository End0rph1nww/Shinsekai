# Plugin Developer Guide

> **中文版完整文档**: [Shinsekai 插件开发规范](https://plugins.shinsekai.studio/docs/plugin)

## Part 1 — Overview

### What a plugin is

Plugins are ordinary Python packages under `plugins/<package>/`, loaded from
`data/config/plugins.yaml`, and executed **in-process** with the host. They are **not**
a security boundary: plugin code runs with full host-process privileges, and the
read-only SDK contexts exist to prevent *accidental misuse* of host internals, not to
contain malicious code — review third-party plugins before installing them.

### Two development layouts

|  | **Local development** | **Market release** |
| --- | --- | --- |
| Source location | `plugins/<package>/` inside the host repo | own GitHub repo, `plugin.py` at the repo root |
| `entry` | hand-written into `plugins.yaml` | inferred by registry CI; users install from the market |
| Best for | personal use, prototypes, shipping with the host | public distribution, market update pushes |
| Typical path | `plugins/my_plugin/plugin.py` | `my-plugin-repo/plugin.py` (flat repos infer an entry like `plugins.my_plugin_repo.plugin:...`) |

The plugin code itself is identical in both layouts; only the directory layout and the
distribution mechanism differ. See **Scaffolding and publishing** for the market
pipeline.

### How the host uses your code

1. **Load** the manifest and import each `entry` → `PluginBase` subclass. Before that
   the host puts the directory containing `plugins/` on `sys.path` (source checkout:
   the CWD; packaged build: the install root, plus `data/plugin_site_packages` where
   plugin dependencies are installed).
2. **Construct** plugins with `cls()` (no constructor arguments).
3. **Call** `initialize(register, plugin_root, host)` in **priority** order (lower
   `priority` runs first). `plugin_root` is a writable per-plugin data directory the
   host creates for you — `data/plugins/<plugin_id with "/" replaced by "_">/`. Keep
   plugin state, caches, and private config there, never in your source tree.
4. **Merge** everything you registered on `register` (`PluginCapabilityRegistry`, alias
   `PluginRegister`) into global factories, tool lists, and UI contribution lists — see
   `core/plugins/plugin_host.py` and `sdk/manager.py`. Tools apply in a fixed order:
   module-level `@tool` functions first, then `register_llm_tool` callbacks, then MCP
   tools from `data/config/mcp.yaml` (skipped when the optional `mcp` dependency is
   missing).
5. **Shut down**: on host exit, `shutdown()` is called on each plugin in **reverse**
   priority order (higher `priority` first). Exceptions are logged and ignored.

Plugin loading runs once per process (`ensure_plugins_loaded` is idempotent), so editing
`plugins.yaml` by hand requires a **restart** (unlike MCP save-and-apply). The desktop
app softens this: installing or updating a plugin in the Plugin Manager automatically
restarts the plugin service and waits for it to come back — the same path as the manual
**Reload** action — so no separate restart is needed there. The web UI still shows a
manual reload hint instead.

### Fault tolerance

One broken plugin does not take the host down:

| Failure point | Behavior |
| --- | --- |
| `entry` import error | logged, entry skipped |
| Class instantiation error | logged (`Skipping plugin class …`), class skipped |
| `initialize` raises | logs `initialize failed for <plugin_id>`, next plugin continues |
| Lifecycle hook raises | warning log, other hooks unaffected |
| `shutdown` raises | logged |

There is **no error popup** when a plugin fails to load — check the logs.

### `PluginBase` surface

| Member | Kind | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `plugin_id` | property | **yes** (abstract) | — | stable unique id, e.g. `com.example.myplugin` |
| `plugin_version` | property | no | `"0.1.0"` | semver string |
| `plugin_name` | property | no | derived from `plugin_id` | human-readable title in the plugin manager |
| `plugin_description` | property | no | `""` | short blurb; hidden on the card when empty |
| `plugin_author` | property | no | `""` | author/vendor; hidden when empty |
| `enabled` | property | no | `True` | return `False` to skip initialization entirely |
| `priority` | property | no | `100` | lower initializes earlier; shutdown runs in reverse |
| `initialize(register, plugin_root, host)` | method | **yes** (abstract) | — | register all capabilities here |
| `shutdown()` | method | no | no-op | called on host shutdown, reverse priority order |

### Registry surface at a glance

| Method                          | What it registers                                          |
| ------------------------------- | ---------------------------------------------------------- |
| `register_llm_adapter`          | LLM backend class → `LLMAdapterFactory`                    |
| `register_tts_adapter`          | TTS backend class → `TTSAdapterFactory`                    |
| `register_asr_adapter`          | ASR backend class → `ASRAdapterFactory`                    |
| `register_t2i_adapter`          | T2I backend class → `T2IAdapterFactory`                    |
| `register_llm_tool`             | Callback `(ToolManager) -> None` for imperative tools      |
| `register_message_handler`      | Optional `MessageHandler` / `UIOutputMessageHandler`       |
| `register_user_input_trigger`   | Hook `trigger(emit_user_text)` for alternate input sources |
| `register_user_input_processor` | `(str) -> str \| None` filter before `UserInputMessage`    |
| `register_settings_ui`          | Extra Settings sidebar page (PySide)                       |
| `register_tools_tab`            | Extra tab under **Settings → Tools** (PySide)              |
| `register_frontend_config_page` | React-renderable plugin config page (schema + load/save callbacks) |
| `register_frontend_page`        | Plugin-owned static frontend page embedded by iframe       |
| `register_chat_ui_widget`       | Chat window widget + placement hint                        |
| `register_dag_yaml`             | Workflow YAML path (convenience — delegates to `register_workflow`) |
| `register_workflow`             | Workflow with optional output contract/schema              |
| `register_output_contract_patch` | Patch an LLM output contract (fields, requirements, …)     |
| `register_before_compact_hook`  | Lifecycle hook before LLM history compaction summary       |
| `register_message_added_hook`   | Lifecycle hook after a message is appended to history      |
| `register_before_chat_hook`     | Lifecycle hook before an adapter chat request is sent      |
| `register_compact_hook`         | *Legacy* pre-compaction hook receiving the raw message list; prefer `register_before_compact_hook` |

**Host-only** (do **not** call from plugins): `set_settings_ui_plugin_context`,
`clear_settings_ui_plugin_context`. The host wraps `initialize` so
`SettingsUIContribution` / `ToolsTabContribution` / `FrontendConfigContribution` /
`FrontendPageContribution` / `ChatUIContribution` pick up `plugin_id` / `plugin_version`
when you leave those fields `None`.

Adapter registration stores the **class** (not an instance); registering the same
provider name again overwrites the earlier one, including built-ins.

---

### Lifecycle hooks

Lifecycle hooks are registered through `PluginCapabilityRegistry` during `initialize`.

```python
from sdk.hooks import BeforeChatContext, BeforeCompactContext, MessageAddedContext
from sdk.register import PluginCapabilityRegistry


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    def before_compact(context: BeforeCompactContext) -> None:
        print(len(context.older_messages))

    def message_added(context: MessageAddedContext) -> None:
        print(context.role, context.message)

    def before_chat(context: BeforeChatContext) -> None:
        context.messages.append({"role": "system", "content": "Temporary plugin context."})

    register.register_before_compact_hook(before_compact)
    register.register_message_added_hook(message_added)
    register.register_before_chat_hook(before_chat)
```

`before_compact` and `message_added` are observation hooks. They receive snapshots of
the host state; mutating the context does not modify the live conversation history.
`before_chat` may modify the request-local `messages`, `tools`, and `generation_kwargs`;
those changes are sent to the adapter but are not written back to `LLMManager.messages`.

Context fields:

| Context | Fields |
| --- | --- |
| `BeforeCompactContext` | `messages`, `older_messages`, `recent_messages` |
| `MessageAddedContext` | `role: str`, `message: dict`, `messages: list` |
| `BeforeChatContext` | `messages: list`, `tools: list \| None`, `generation_kwargs: dict`, `stream: bool` |

Hook exceptions are caught and logged (warning); they never interrupt other hooks or the
host.

---

## Part 2 — Details

### Manifest and `entry`

- **Path:** `data/config/plugins.yaml` — YAML **list** of dicts with at least `entry`,
  optional `enabled` (default `true`).
- **Explicit class (recommended):** `plugins.my_pkg.plugin:MyPkgPlugin`
- **Module + `Plugin` attribute:** `plugins.my_pkg.plugin` expects `Plugin = class`.
- **Other keys** in YAML become `PluginDescriptor.extra`; the host **does not** inject
  `extra` into `initialize` today — use `plugin_root` or files under `data/plugins/` for
  plugin state.
- Registry-installed entries may omit the `plugins.` prefix; the host's
  `normalize_manifest_entry` adds it automatically.
- A broken entry (import error, bad class) is logged and skipped; other plugins load
  normally.

### Market-release repository layout

Market plugins live in their own GitHub repository with the entry file at the repo root
(registry CI infers `entry` from it):

```text
shinsekai-plugin-example/
  plugin.py           # entry: the PluginBase subclass lives here
  requirements.txt    # optional; installed on install/update
  README.md           # features, configuration, dependency sources, risk notes
  logo.png            # optional market card icon
  plugin.json         # optional publish metadata (see Scaffolding and publishing)
  assets/             # other resources (logo may live here too)
  frontend/dist/      # if the plugin ships its own frontend page
```

- **Entry/name inference:** for a root-level `plugin.py`, registry CI lowercases the
  repo name and turns `-` into `_` when it builds the package segment in `entry` (for
  example, `Shinsekai-Plugin-Market` -> `plugins.shinsekai_plugin_market.plugin:...`).
  Use only letters, digits, `.`, `-`, and `_` in repo names so the inferred name is a
  valid Python package segment.
- **Install directory:** installed folder names come from the registry package/name/id
  metadata and are filename-sanitized by the client. Treat the `entry`, not the install
  folder name, as the stable import contract.
- Helper modules may live in subdirectories, but keep `plugin.py` at the repo root (or
  a first-level package directory), or CI entry inference may fail.
- **Logo:** `logo.png`, `logo.jpg`, `logo.jpeg`, or `logo.webp` at the repo root or in
  one of `assets/`, `asset/`, `static/`, `public/`, `resources/`, `res/`, `images/`,
  `img/`.

### UI contexts (read-only surfaces)

| Context                   | Where it appears                                              | What you get                                                                                                                                                                       |
| ------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PluginHostContext`       | `initialize(..., host=…)`                                     | UI language, voice language, font size, theme tint, **selected LLM/TTS labels** (no secrets), `project_data_dir`, `huggingface_cache_dir`. **No** `ConfigManager`, **no** API keys, **no** global save API. |
| `PluginSettingsUIContext` | `SettingsUIContribution.build` / `ToolsTabContribution.build` | `host` snapshot + `template_dir_path`, `history_dir`, `character_names`, `background_names`.                                                                                       |
| `ChatUIContext`           | `ChatUIContribution.build`                                    | Safe chat state reads, queued UI updates, `on_*` event subscriptions, `submit_user_message` when the host bound it.                                                                |

Prefer these over raw Qt signals on internal windows. `ChatUIContext` is also reachable
at runtime via `sdk.chat_ui_context.try_get_chat_ui_context()` (returns `None` before
the chat window exists) or `get_chat_ui_context()` (raises `RuntimeError` instead).

`PluginHostContext` fields (frozen dataclass; the defaults shown apply when no config
manager is available):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `ui_language` | `str` | `"zh_CN"` | UI language (`zh_CN` / `en` / `ja`) |
| `voice_language` | `str` | `"ja"` | voice language |
| `base_font_size_px` | `int` | `56` | base font size |
| `theme_color` | `str` | `"rgba(50,50,50,200)"` | theme tint |
| `selected_llm_provider` | `str` | `""` | selected LLM provider label — no secrets |
| `tts_provider` | `str` | `""` | selected TTS provider |
| `live_room_id` | `str` | `""` | live-stream room id |
| `project_data_dir` | `Path` | `data` | project data directory |
| `huggingface_cache_dir` | `Path` | `data/cache/huggingface` | put model downloads here |

`ChatUIContext` members beyond the examples below — state reads: `notification_hint()`,
`input_draft()`, `choice_options()`, `is_dialog_visible()`, `is_choice_panel_visible()`,
`dialog_text()`, `background_image_path()`, `base_font_size_px()`; thread-safe UI
updates: `set_notification_hint`, `set_busy_bar(text, duration_seconds=3.0)`,
`hide_busy_bar()`, `set_input_draft`, `clear_input_draft`, `set_choice_options`,
`set_dialog_html`, `submit_user_message`. Each of the 28 `on_*` event subscriptions
returns a **disconnect** callable — keep it and call it when your widget goes away:

`on_message_submitted(str)`, `on_reroll_requested()`, `on_open_chat_history_dialog()`,
`on_change_voice_language(str)`, `on_close_window()`, `on_clear_chat_history()`,
`on_skip_speech_signal()`, `on_llm_reply_finished()`, `on_pause_asr_signal()`,
`on_copy_chat_history_to_clipboard()`, `on_revert_chat_history(int)`,
`on_option_selected(str)`, `on_llm_response_received(object)`,
`on_background_image_changed(str)`, `on_notification_changed(str)`,
`on_display_words_changed(str)`, `on_numeric_info_changed(str)`,
`on_user_input_started()`, `on_user_input_ended()`,
`on_mic_transcription_update(str, bool)`, `on_mic_asr_state_changed(bool)`,
`on_mic_asr_pause_requested()`, `on_mic_asr_resume_requested()`,
`on_mic_send_final_transcription()`, `on_cg_display_changed(bool)`,
`on_dialog_typing_finished()`, `on_dialog_area_clicked()`,
`on_sprite_frame_updated(object)`

### Runtime workflows

Runtime workflows are declared as YAML and loaded through `core.runtime.workflow`. The
host runs exactly one workflow at a time:

- If the user passes `--workflow path/to/workflow.yaml`, only that YAML is loaded.
- If no workflow is selected, the host loads `assets/system/workflow/default.yaml`. In
  headless mode (`--headless`) the default is `assets/system/workflow/headless.yaml`,
  which omits UIWorker and avoids pygame/Qt window dependencies.
- Plugin workflow YAML files are selectable candidates; they are not merged into the
  default workflow automatically. Plugin workflow YAML files registered via
  `register_dag_yaml` or `register_workflow` are collected as `WorkflowContribution`
  objects and are selectable candidates for the workflow runner.

A workflow YAML has three top-level sections:

```yaml
nodes:
  - name: rule
    type: plugins.my_plugin.workflow.RuleNode
    params:
      accepted: "yes"
  - name: router
    type: plugins.my_plugin.workflow.RouterNode
    params:
      rule_node: rule
edges:
  - src: router
    src_port: accepted
    dst: sink
    dst_port: in
exports:
  chat.input:
    node: router
    port: in
    direction: input
```

- `nodes` instantiate classes by dotted import path. The `params` dict under each node
  maps directly to the node class constructor kwargs.
- `edges` connect an output port to an input port with a shared queue. The builder
  validates topology: **cycles, fan-in (two upstreams into one input port), and fan-out
  (one output port to two downstreams) are all rejected**.
- `exports` expose queues or node handles to the host.

`DagNode` is passive by default. Its sync lifecycle hooks (`start` / `stop`) and async
lifecycle hooks (`astart` / `astop`) do nothing unless your subclass overrides them.
Queue-driven nodes should own their execution loop in lifecycle hooks. Passive helper
nodes should expose normal Python methods and be called by another node or by the host.

To reference another node from YAML, pass its name as a constructor parameter and
resolve it in `configure(nodes)`:

```python
from sdk.graph import DagNode, Port


class RuleNode(DagNode):
    def inputs(self):
        return {}

    def outputs(self):
        return {}

    def accepts(self, value: str) -> bool:
        return value == "yes"


class RouterNode(DagNode):
    def __init__(self, name: str, rule_node: str):
        super().__init__(name)
        self.rule_node_name = rule_node
        self.rule = None

    def inputs(self):
        return {"in": Port("in")}

    def outputs(self):
        return {"accepted": Port("accepted"), "rejected": Port("rejected")}

    def configure(self, nodes):
        self.rule = nodes[self.rule_node_name]

    def to_config(self):
        # Required for YAML round-trips: subclasses with extra constructor
        # parameters must override to_config(), or save/load loses them.
        return {"rule_node": self.rule_node_name}
```

Important boundary: `edges` only wire queues. A passive node is not executed just
because it appears in YAML. Something must call its methods, or it must implement its
own lifecycle.

Other `DagNode` members: `from_config(name, params)` (classmethod the YAML loader uses;
the default builds `cls(name=name, **params)` — override it when the mapping is
non-trivial), and `inq(port_name)` / `outq(port_name)` to fetch the queue bound to a
port (both raise `RuntimeError` for unbound ports). In `exports`, `direction` selects
what gets exposed: `input` / `output` expose the port's bound queue, `node` exposes the
node handle itself; when omitted, it defaults to `node` if no `port` is given and
`input` otherwise.

### Output contract patching

Plugins can customise the LLM output template (the JSON dialog format) without replacing
the entire workflow. Use `OutputContractPatch` to add fields, modify field descriptions,
tweak requirement text, or append new requirements — all targeting the default dialog
contract `"default.dialog.v1"`.

**Key types** (from `sdk.types`; fields verified against source):

| Type | Purpose |
|---|---|
| `OutputFieldSpec` | One field in the LLM JSON output (`key`, `type="string"`, `description=""`, `required=False`, `aliases=()`) |
| `RequirementSpec` | One stable, patchable requirement (`id`, `text`, `order=100.0`, `enabled=True`) |
| `FieldPatch` | Partial override for a field: `description`, `required`, `type`, `enum` — `None` (and empty-string `description`) mean "leave unchanged" |
| `RequirementPatch` | Patch operation: `mode` is `"append"`, `"prepend"`, `"replace"`, or `"remove"`; `text` carries the patch payload |
| `OutputContractPatch` | Bundled patch targeting a named contract (`target_contract`), with `priority` ordering |
| `ChatOutputContract` | Complete declarative contract: `id`, `json_schema`, `requirements=()`, `target_export="llm.output"`, `stream_mode="json_object"` (`"json_object" \| "json_lines" \| "json_array"`) — attach to `WorkflowContribution` |
| `WorkflowContribution` | `id`, `name`, `yaml_path`, `description=""`, plus optional `output_contract` (use `register_workflow` to register) |

> Note: `OutputFieldSpec` has **no** `example` field, `FieldPatch` has **no** `examples`
> field, and `ChatOutputContract` has **no** `example` field. Earlier revisions of this
> guide listed them in error.

**Example: tightening speech rules**

```python
from sdk.register import PluginCapabilityRegistry
from sdk.types import (
    FieldPatch,
    OutputContractPatch,
    OutputFieldSpec,
    RequirementPatch,
    RequirementSpec,
)

DEFAULT_DIALOG = "default.dialog.v1"


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    # Add an optional "camera" field to the JSON output
    register.register_output_contract_patch(
        OutputContractPatch(
            id="my_plugin.camera_direction",
            target_contract=DEFAULT_DIALOG,
            priority=50.0,
            add_fields=(
                OutputFieldSpec(
                    key="camera",
                    type="string",
                    description="Camera direction hint for visual novel rendering, e.g. close_up.",
                    required=False,
                ),
            ),
            field_patches={
                "speech": FieldPatch(
                    description="Speech may include parenthesized vocal tags like (cough) or (laugh).",
                ),
            },
            requirement_patches={
                "r_speech": RequirementPatch(
                    mode="append",
                    text="Allow concise parenthesized tags such as (cough), (laugh), or (sigh).",
                ),
            },
            add_requirements=(
                RequirementSpec(
                    id="my_plugin.emotion_tag_balance",
                    text="Do not overuse parenthesized vocal tags - at most 1 per 3 lines.",
                    order=71,
                ),
            ),
        )
    )
```

**How patches apply:**

1. Patches are sorted by `priority` (lower first, higher wins on conflict).
2. `remove_fields` runs first (core fields `character_name`, `speech`, `sprite` are
   **protected**).
3. `field_patches` modify existing fields — `description` replaces when non-empty;
   `enum` values are appended to the description text.
4. `add_fields` inserts new fields and generates corresponding JSON example lines in the
   prompt.
5. Requirement patches (`requirement_patches`) target stable requirement IDs like
   `r_speech`, `r_format`, `r_cname`, etc.
6. `add_requirements` inserts new requirement entries; they participate in the same
   priority-ordered sort.

**Stable requirement IDs** (for `requirement_patches`):

| ID | Content |
|---|---|
| `r_format` | JSON array format rule |
| `r_cname` | Character name assignment |
| `r_sprite` | Sprite/asset ID rule |
| `r_non_sprite` | Non-sprite entities (NARR, CHOICE, STAT) |
| `r_scene` | Scene background (when real bg selected) |
| `r_bgm` | Background music (when real bg selected) |
| `r_speech` | Speech text language/quality rule |
| `r_array` | Output must be a JSON array |
| `r_speech_max_chars` | Max characters per speech line |
| `r_dialog_max_items` | Max dialog items per response |
| `r_narration` | Narration formatting |
| `r_choice_pos` | Choice placement rules |
| `r_choice_format` | Choice JSON format |
| `r_choice_balance` | Choice balance guidance |
| `r_stats` | Stat display format |
| `r_cg` | CG/illustration display |
| `r_translate` | Translation field (when LLM translation enabled) |
| `r_effect` | Emotion effect field |
| `r_cot` | Chain-of-thought (when enabled) |

### Logging

Plugins should use the SDK logging facade instead of configuring Python logging handlers
directly:

```python
from sdk.logging import get_logger, log_context, stopwatch

logger = get_logger(__name__, plugin_id="example.my-plugin")

logger.info("Plugin initialized", extra={"event": "plugin.initialized"})

with log_context(task_id="task-123"):
    logger.info("Background work started", extra={"event": "plugin.task.started"})

# Timing helper (context manager + decorator); logs at INFO when elapsed >= threshold seconds
with stopwatch("my_plugin.index_build", threshold=0.5):
    build_index()
```

The host owns log levels, files, rotation, formatting, and redaction
(`configure_logging` / `shutdown_logging` are host-only). Plugins must not call
`logging.basicConfig()`, add handlers, or write API keys, user messages, prompts, tool
arguments, or model responses to logs. Prefer stable `event` names and summary fields
such as character counts, item counts, and durations. `new_log_id(prefix="")` generates
correlation ids; recognised context fields are `session_id`, `turn_id`, `request_id`,
`task_id`, `plugin_id`.

### Exceptions

`sdk.exception` gives plugins the host's exception classification and user-facing
formatting:

```python
from sdk.exception import classify_exception, format_llm_exception_message

try:
    result = call_remote_api()
except Exception as exc:
    info = classify_exception(exc)   # ExceptionInfo | None
    friendly = format_llm_exception_message(exc, fallback_message="Request failed.")
```

- `classify_exception` first checks for **missing dependencies** (via a module → pip
  package map, e.g. `PIL` → `Pillow`, `cv2` → `opencv-python`) and returns a
  `RuntimeDependencyError`; then for **HTTP client errors** across the httpx /
  httpcore / urllib / openai / anthropic exception families, returning an
  `HttpClientError` (error type, timeout flag, status code, URL). Anything else →
  `None`.
- `format_llm_exception_message(exc, *, fallback_message)` turns 401/402/403/429,
  timeouts, 5xx, … into an actionable message for users.
- `install_main_exception_hook` and the other handler/dialog APIs are host-only.

Inside LLM tools, prefer returning structured errors (e.g. `{"error": "..."}`) over
raising — the model can read a structured error and explain it to the user.

### Adapter classes: schemas and "extra" kwargs

#### Where adapters show up, and who owns the parameters

Registering an adapter only adds a **class** to the host factories. **Users** choose the
backend and fill in secrets/options in the **Settings** window. Those values are **not**
stored in `plugins.yaml` or in your package tree by default.

| Kind    | Where users pick it (Settings UI) | Persisted to disk (typical) | Your responsibility as the plugin author |
| ------- | -------------------------------- | --------------------------- | ---------------------------------------- |
| **LLM** | **API settings** tab — "LLM provider" combo (`llm_provider`). Labels are **case-sensitive** and must match your `register_llm_adapter("Exact Name", …)`. Same tab: API key, base URL, model id, streaming/sampling. | `data/config/api.yaml` (`ApiConfig`): shared LLM fields plus `llm_extra_configs[<llm_provider>]` — populated from your adapter's `get_config_schema()` via dynamic form widgets in `ui/settings_ui/tabs/api_tab.py`. | Implement `get_config_schema()` (optional) and an `__init__` that accepts kwargs the host will pass (see `ConfigManager.merged_llm_factory_kwargs`). Do **not** expect to read API keys inside `PluginBase.initialize`; they are injected only when the adapter instance is constructed at runtime. |
| **TTS** | **API settings** tab — TTS engine combo (internal value is a **lowercase** slug, e.g. `gpt-sovits`). Shared fields (SoVITS path/URL, etc.) live on the same page. | `data/config/api.yaml`: `tts_provider` / shared TTS columns plus `tts_extra_configs[<slug>]` from `get_config_schema()`. | Register with the **same** slug the combo uses (`register_tts_adapter("my-engine", …)` → factory lowercases). Match ctor parameters to `merged_tts_factory_kwargs`. |
| **ASR** | **System**-side provider choice (`asr_provider`: Vosk / Whisper-class plugins, etc.). Extra per-backend fields appear under **API settings** when that ASR class exposes `get_config_schema()`. | `data/config/system_config.yaml` for global mic/Whisper options (`asr_provider`, model size, device, …) + `data/config/api.yaml` → `asr_extra_configs[<normalized_slug>]` for schema-driven extras. | `register_asr_adapter` slug must match the normalized key the host uses when creating the adapter (`asr/asr_adapter.py`). Base ctor signature is fixed: `__init__(self, language: str, callback: TranscriptionCallback)` where `TranscriptionCallback = Callable[[str, bool], None]`. |
| **T2I** | **API settings** — Comfy-style URL, workflow paths, node IDs, etc. The dynamic "extra" panel is currently wired to the built-in Comfy adapter's schema in `api_tab.py`. | `data/config/api.yaml`: `t2i_*` fields plus `t2i_extra_configs` (default engine key `"comfyui"` in the UI today). | `register_t2i_adapter` keys are **lowercased**. For non-Comfy engines, users may need to edit `t2i_extra_configs[<your_engine>]` manually until the Settings UI grows a provider switch; ctor should still accept kwargs from `merged_t2i_factory_kwargs`. |

**Summary:** Adapter tuning is **centralized** in `api.yaml` / `system_config.yaml`,
edited through **Settings** and `ConfigManager`. You expose **fields** via
`get_config_schema()` and **parameter names** on `__init__`; you normally **do not**
ship a parallel config format for the same secrets. Optional plugin-specific data
(licenses, experimental flags) can still go under `plugin_root` or a page you add with
`register_settings_ui`.

- `get_config_schema()` — Optional classmethod; per-provider fields rendered on the API
  settings page. Metadata keys: `type` (str/int/float/bool), `label`, `default`,
  `secret`, `min`, `max`, `step`, `choices` (list of strings → dropdown). Empty `{}`
  adds no extra widgets.
- **Factory merge** — Host builds adapters with `merged_*_factory_kwargs`: **base**
  kwargs from `api.yaml` / `system_config.yaml` plus `llm_extra_configs` /
  `tts_extra_configs` / `asr_extra_configs` / `t2i_extra_configs`, filtered by
  `config.adapter_extra_kwargs.filter_kwargs_for_ctor` (or full dict if `__init__` has
  `**kwargs`).
- **Subclass** `sdk/adapters` ABCs and register the **class**, not an instance.
- `LLMAdapter.__init__(**kwargs)` tolerates unknown keys (it only sets
  `user_template = ""`; the host calls `set_user_template()` separately). `TTSAdapter`
  declares **no** base `__init__` — its constructor contract is entirely between your
  subclass and `merged_tts_factory_kwargs`.
- LLM adapters may also override `get_unsupported_chat_params(provider) -> set[str]` to
  strip sampling params a backend rejects (e.g. penalty parameters on Gemini's
  OpenAI-compatible bridge).

---

## `PluginCapabilityRegistry` — one example per `register_`*

### `register_llm_adapter(provider, adapter_cls)`

**Provider string** must match the **exact** LLM provider name the UI saves (e.g.
`"Deepseek"`, `"ChatGPT"`).

```python
from sdk.adapters.llm import LLMAdapter
from sdk.register import PluginCapabilityRegistry


class EchoLLMAdapter(LLMAdapter):
    """Minimal demo: echo the last user message (ignores real API keys)."""

    def chat(self, messages: list, stream: bool = False, **kwargs):
        for m in reversed(messages or []):
            if isinstance(m, dict) and m.get("role") == "user":
                return m.get("content") or ""
        return "…"


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    register.register_llm_adapter("MyEchoLLM", EchoLLMAdapter)
```

Shippable adapters should honor `api_key`, `base_url`, `model`, streaming, and tool
loops like the built-ins in `llm/llm_adapter.py`.

---

### `register_tts_adapter(provider, adapter_cls)`

**Provider** is resolved with `.lower()` (e.g. `"my-tts"`).

```python
from sdk.adapters.tts import TTSAdapter
from sdk.register import PluginCapabilityRegistry


class SilenceTTSAdapter(TTSAdapter):
    def generate_speech(self, text, file_path=None, **kwargs):
        return None

    def switch_model(self, model_info):
        return None


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    register.register_tts_adapter("my-silent-tts", SilenceTTSAdapter)
```

Align your real `__init__` signature with what `merged_tts_factory_kwargs` supplies.

---

### `register_asr_adapter(provider_slug, adapter_cls)`

**Slug** must match the normalized ASR provider in settings (`asr/asr_adapter.py`).
**Base signature:** `__init__(self, language: str, callback: TranscriptionCallback)`.
All five abstract methods are required.

```python
from sdk.adapters.asr import ASRAdapter
from sdk.register import PluginCapabilityRegistry


class NoopAsrAdapter(ASRAdapter):
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def get_status(self) -> str:
        return "idle"

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    register.register_asr_adapter("my_noop_asr", NoopAsrAdapter)
```

---

### `register_t2i_adapter(provider, adapter_cls)`

**Provider** is stored **lowercased**.

```python
from typing import Any, Dict, Optional

from sdk.adapters.t2i import T2IAdapter
from sdk.register import PluginCapabilityRegistry


class StubT2IAdapter(T2IAdapter):
    def generate_image(
        self, prompt: str, file_path: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        return None

    def switch_model(self, model_info: Dict[str, Any]) -> None:
        return None


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    register.register_t2i_adapter("my_stub_t2i", StubT2IAdapter)
```

---

### `register_llm_tool(registrar)`

**Prefer** module-level `@tool` from `sdk.tool_registry` (the host runs
`apply_registered_tools` **before** these callbacks). Use `register_llm_tool` when you
need **dynamic** registration based on `plugin_root` or config.

```python
from llm.tools.tool_manager import ToolManager
from sdk.register import PluginCapabilityRegistry


def _register_extra_tools(tm: ToolManager) -> None:
    def roll_report(sides: int = 6) -> str:
        """Pretend dice; returns a short English string for the LLM."""
        return f"Rolled {sides}-sided die (stub)."

    tm.register_function(roll_report, name="roll_report", description="Stub dice roll.")


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    register.register_llm_tool(_register_extra_tools)
```

The `@tool` decorator's full parameter set:

```python
@tool(
    name="example_lookup",     # defaults to the function name
    description="…",           # defaults to the docstring
    group="example",           # tool group, defaults to "default"
    risk="low",                # "low" | "medium" | "high", defaults to "low"
)
def example_lookup(query: str) -> dict: ...
```

Remember the decorator only runs when its module is imported — import your tool module
once inside `initialize()` if the tools live in a separate file.

---

### Slow model loading tools: `ToolNotReady`

When your `@tool` depends on a model that loads **slowly** (downloading weights, warming
up GPU), don't block the LLM thread — raise `ToolNotReady`. The host's `ToolExecutor`
catches it, converts it to a structured loading response, and sets a **cooldown** so the
LLM won't hammer the tool.

```python
import threading

from sdk.tool_registry import ToolNotReady, tool

_model = None
_loading = False


@tool(name="my_vision_tool", group="vision",
      description="Describe what's on screen using a local model.")
def my_vision_tool(question: str) -> dict:
    global _model, _loading

    if _model is None:
        if not _loading:
            _loading = True
            threading.Thread(target=_download_and_load_model, daemon=True).start()
        raise ToolNotReady(
            "The vision model is downloading/loading (first run takes 2-10 minutes). "
            "Tell the user to wait; do not call this tool again."
        )

    return {"answer": _model.infer(question)}
```

**What happens when you raise `ToolNotReady`:**

1. `ToolExecutor` catches the exception → returns `{"status": "loading", "message":
   "..."}` to the LLM.
2. `ToolExecutor` sets a **group-level cooldown** (default: 300 s for `"memory"`, 600 s
   for `"vision"`, 120 s for other groups).
3. While the group is on cooldown, **any** tool in the same group returns a cooldown
   message immediately — the function body is never called.

**Signalling readiness** — when your background load completes, notify the host to clear
the cooldown and surface a chat notification:

```python
from sdk.tool_registry import notify_tool_ready

notify_tool_ready("vision", "Vision model loaded; the tool is ready.")
```

**Customising cooldown per group:**

```python
from llm.tools.tool_executor import tool_executor

tool_executor.set_group_cooldown("my_group", 180.0)  # 3 minutes
```

**Tool description notes** — tell the LLM what to expect:

```python
@tool(
    name="my_vision_tool",
    group="vision",
    description=(
        "Analyse the screen. "
        "NOTE: first call may return status:'loading' (model downloading, 2-10 min). "
        "If you get status:'loading', follow the message - do NOT retry any tool in the same group."
    ),
)
```

---

### `register_message_handler(tts_handler=..., ui_handler=...)`

Extend the TTS pipeline (`MessageHandler` for `LLMDialogMessage`) and/or UI output
(`UIOutputMessageHandler` for `TTSOutputMessage`). First handler with `can_handle` wins.
Import the ABCs and message models from the SDK (`sdk.handlers`, `sdk.messages`) rather
than host-internal modules.

Message models (`sdk.messages`, Pydantic; the aliases keep parsed LLM JSON compatible):

| Model | Queue | Fields (alias) |
| --- | --- | --- |
| `UserInputMessage` | user input | `text` |
| `LLMDialogMessage` | TTS | `name` (`character_name`), `text` (`speech`), `asset_id` (`sprite`; `"-1"` = leave unchanged), `translate`, `effect` |
| `TTSOutputMessage` | UI output | same minus `translate`, plus `audio_path`, `is_system_message`, `is_final_segment`, `timeout` |

```python
from sdk.handlers import MessageHandler
from sdk.messages import LLMDialogMessage
from sdk.register import PluginCapabilityRegistry


class LogDialogHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return bool((msg.effect or "").strip())

    def handle(self, msg: LLMDialogMessage) -> None:
        # Replace with real side effects (assets, logging, etc.).
        print(f"[plugin] effect={msg.effect!r} text={msg.text!r}")


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    register.register_message_handler(tts_handler=LogDialogHandler())
```

Handlers also have optional `pre_process` / `post_process` / `init()` hooks; `init()`
runs once after the TTS worker builds its dispatcher.

---

### `register_user_input_trigger(trigger)`

Receive `emit_user_text: Callable[[str], None]` — call it when your custom source has
text (hotkey bridge, serial port, etc.). Usually stash `emit_user_text` and invoke it
from your wiring.

```python
from collections.abc import Callable

from sdk.register import PluginCapabilityRegistry


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    def trigger(emit_user_text: Callable[[str], None]) -> None:
        self._emit_user_text = emit_user_text  # save on plugin instance

    register.register_user_input_trigger(trigger)
```

`plugin_host.wire_user_input_plugins` passes the same `emit_user_text` used by the chat
input path.

---

### `register_user_input_processor(processor)`

Return **new string** to continue the pipeline, or `None` to **drop** the message. A
processor that raises also drops that message (logged).

```python
from sdk.register import PluginCapabilityRegistry


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    def strip_or_abort(raw: str) -> str | None:
        text = (raw or "").strip()
        return text if text else None

    register.register_user_input_processor(strip_or_abort)
```

---

### `register_settings_ui(contribution)`

```python
from sdk.plugin_host_context import PluginSettingsUIContext
from sdk.register import PluginCapabilityRegistry
from sdk.types import SettingsUIContribution


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    def build_page(ctx: PluginSettingsUIContext):
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f"Characters loaded: {len(ctx.character_names)}"))
        return w

    register.register_settings_ui(
        SettingsUIContribution(
            page_id="my_plugin.settings",
            nav_label="My plugin",
            build=build_page,
            order=120.0,
        )
    )
```

---

### `register_tools_tab(contribution)`

Same `PluginSettingsUIContext` builder as settings pages; appears under **Settings →
Tools**.

```python
from sdk.plugin_host_context import PluginSettingsUIContext
from sdk.register import PluginCapabilityRegistry
from sdk.types import ToolsTabContribution


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    def build_tools(ctx: PluginSettingsUIContext):
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f"Template dir: {ctx.template_dir_path}"))
        return w

    register.register_tools_tab(
        ToolsTabContribution(
            tab_id="my_plugin.tools",
            title="My tool",
            build=build_tools,
            order=80.0,
        )
    )
```

---

### `register_frontend_config_page(contribution)`

Use this when the React settings frontend should render your plugin page. Keep the
existing Qt `register_settings_ui` / `register_tools_tab` page if you still support the
PySide settings window.

```python
from dataclasses import asdict
from pathlib import Path

from sdk.types import FrontendConfigAction, FrontendConfigContribution


def initialize(self, register, plugin_root: Path, host) -> None:
    def load_values():
        return asdict(load_config(plugin_root / "config.json"))

    def save_values(values):
        save_config(plugin_root / "config.json", MyConfig(enabled=bool(values.get("enabled"))))

    register.register_frontend_config_page(
        FrontendConfigContribution(
            page_id="my_plugin.settings",
            title="My plugin",
            kind="settings",
            description="Configure the example plugin.",
            restart_hint="Reload the plugin after changing these values.",
            schema=[
                {
                    "id": "main",
                    "title": "Main",
                    "fields": [
                        {
                            "key": "enabled",
                            "label": "Enabled",
                            "type": "boolean",
                            "defaultValue": False,
                        }
                    ],
                }
            ],
            i18n={
                "zh_CN": {
                    "title": "我的插件",
                    "groups": {
                        "main": {
                            "title": "主要",
                            "fields": {
                                "enabled": {"label": "启用"},
                            },
                        }
                    },
                },
                "ja": {
                    "title": "マイプラグイン",
                    "groups": {
                        "main": {
                            "title": "メイン",
                            "fields": {
                                "enabled": {"label": "有効"},
                            },
                        }
                    },
                },
            },
            load_values=load_values,
            save_values=save_values,
            actions=[
                FrontendConfigAction(
                    id="test",
                    label="Test connection",
                    variant="primary",       # "primary" | "ghost" | "danger"
                    confirm="",              # non-empty → confirm dialog before running
                    run=lambda values: {"ok": True},
                )
            ],
            order=120.0,
        )
    )
```

The schema must be JSON-safe. Supported field types match the React
`PluginConfigFieldType`: `boolean`, `integer`, `json`, `number`, `password`, `select`,
`text`, `textarea`, and `url`.

The optional `i18n` map is keyed by frontend language (`zh_CN`, `en`, `ja`). It can
override page `title`, `description`, `restartHint`, group `title` / `description`, and
field `label` / `description` / `placeholder`. For select fields, use `options` keyed by
option `value`, for example `{"options": {"chromium": "Chromium (Playwright)"}}`.

`actions` (`FrontendConfigAction`) render buttons next to Save: `run(values)` receives
the current form values and may return a dict that is forwarded to the frontend;
`confirm` (non-empty) shows a confirmation dialog first; `variant` picks the button
style.

---

### `register_frontend_page(contribution)`

Use this when a plugin needs its own richer frontend than the schema renderer can
provide. Ship a built static page in the plugin directory, usually
`plugins/<package>/frontend/dist/index.html`, and register that file as the entry. The
host serves files from the entry directory and embeds the page in an iframe.

If you also register a `FrontendConfigContribution` with the same `page_id` and `kind`,
the page payload includes that schema and current values. The iframe can read
`/api/plugins/<plugin_id>/ui` and save to
`/api/plugins/<plugin_id>/ui/<page_id>/config`.

```python
from pathlib import Path

from sdk.types import FrontendConfigContribution, FrontendPageContribution


def initialize(self, register, plugin_root: Path, host) -> None:
    page_id = "my_plugin.tools"

    register.register_frontend_config_page(
        FrontendConfigContribution(
            page_id=page_id,
            title="My tool",
            kind="tools",
            schema=[...],
            load_values=load_values,
            save_values=save_values,
        )
    )
    register.register_frontend_page(
        FrontendPageContribution(
            page_id=page_id,
            title="My tool",
            kind="tools",
            entry=(Path(__file__).parent / "frontend" / "dist" / "index.html").as_posix(),
            order=80.0,
        )
    )
```

This keeps downloaded plugins self-contained: after install and app restart, the host
discovers the contribution from the plugin's Python entry point and serves the bundled
frontend files without rebuilding the main React app.

---

### `register_chat_ui_widget(contribution)`

`placement` is a host-defined hint (`"toolbar"`, `"overlay"`, `"input_row"`, …).

```python
from sdk.chat_ui_context import ChatUIContext
from sdk.register import PluginCapabilityRegistry
from sdk.types import ChatUIContribution


def initialize(self, register: PluginCapabilityRegistry, plugin_root, host) -> None:
    def build_widget(ctx: ChatUIContext):
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        w = QWidget()
        lay = QVBoxLayout(w)
        hint = QLabel(ctx.notification_hint() or "-")
        lay.addWidget(hint)
        _disconnect = ctx.on_notification_changed(lambda t: hint.setText(t or "-"))
        w.destroyed.connect(_disconnect)
        return w

    register.register_chat_ui_widget(
        ChatUIContribution(
            widget_id="my_plugin.notify_echo",
            placement="toolbar",
            build=build_widget,
            order=10.0,
        )
    )
```

---

## Worked example: manifest + settings + `@tool`

`data/config/plugins.yaml`

```yaml
- entry: plugins.example_demo.plugin:ExampleDemoPlugin
  enabled: true
```

`plugins/example_demo/__init__.py`

```python
"""example_demo plugin package."""
```

`plugins/example_demo/plugin.py`

```python
from __future__ import annotations

from pathlib import Path

from sdk.plugin import PluginBase
from sdk.plugin_host_context import PluginHostContext, PluginSettingsUIContext
from sdk.register import PluginCapabilityRegistry
from sdk.tool_registry import tool
from sdk.types import SettingsUIContribution


@tool(name="demo_ping", description="Return a fixed ping string for testing.")
def demo_ping() -> str:
    return "pong"


class ExampleDemoPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "com.example.demo"

    @property
    def plugin_version(self) -> str:
        return "0.1.0"

    @property
    def plugin_name(self) -> str:
        return "Demo (example)"

    @property
    def priority(self) -> int:
        return 100

    def initialize(
        self,
        register: PluginCapabilityRegistry,
        plugin_root: Path,
        host: PluginHostContext,
    ) -> None:
        _ = plugin_root

        def build_settings(ctx: PluginSettingsUIContext):
            from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

            w = QWidget()
            layout = QVBoxLayout(w)
            layout.addWidget(QLabel(f"UI language: {ctx.host.ui_language}"))
            layout.addWidget(QLabel(f"Loaded characters: {len(ctx.character_names)}"))
            return w

        register.register_settings_ui(
            SettingsUIContribution(
                page_id="example_demo.settings",
                nav_label="Demo plugin",
                build=build_settings,
                order=500.0,
            )
        )
```

Restart the app after adding the YAML row. The model can call `demo_ping` when tools are
enabled for your template.

---

## Scaffolding and publishing

From the repo root:

```bash
python -m sdk.cli create my_plugin_name
# options: --root PATH  --plugin-id com.you.my_plugin_name  --display-name "My Plugin"  --minimal
```

The package name must match `^[a-z][a-z0-9_]*$`. This generates
`plugins/<package>/{__init__.py, plugin.py, README.md}`. Add the printed `entry` to
`data/config/plugins.yaml`, restart, and iterate.

To list a plugin in the in-app catalog, publish a row to
[Shinsekai-Plugin-Registry](https://github.com/RachelForster/Shinsekai-Plugin-Registry):

```bash
python -m sdk.cli registry-snippet --name "my_plugin_name" --author "You" \
  --repo owner/repo --description "..." --entry "my_plugin_name.plugin:MyPkgPlugin"
```

Note the registry `entry` conventionally **omits** the `plugins.` prefix; the desktop
client adds it on install via `normalize_manifest_entry`.

To merge directly into a local clone of the registry instead of copy-pasting:

```bash
python -m sdk.cli registry-append --registry /path/to/Shinsekai-Plugin-Registry \
  --name "my_plugin_name" --author "You" --repo owner/repo \
  --description "..." --entry "my_plugin_name.plugin:MyPkgPlugin" \
  [--replace] [--dry-run] [--commit] [--message "registry: add my_plugin_name"]
```

Rows are deduplicated by repo slug (lowercase; pass `--replace` to overwrite) and sorted
by name.

For chat-UI theme packs there is a separate helper — `python -m sdk.chat_ui_theme` —
with module-level APIs `validate_manifest`, `validate_theme_dir`, `pack_theme`, and
`safe_extract` (`sdk/chat_ui_theme.py`).

Alternatively, submit through the plugin market at <https://plugins.shinsekai.studio> —
it generates a normalized JSON payload and opens a prefilled `Publish Plugin` issue
(`PLUGIN_PUBLISH.yml`) on the registry; CI infers the `entry` automatically from your
repository's root-level `plugin.py`, so market submissions don't need `--entry` at all.
Submission constraints: `display_name` / `desc` / `author` / `repo` required, `desc` ≤
200 chars, `repo` must be `https://github.com/{owner}/{repo}`, at most 5 `tags`;
optional `lowest_shinsekai_version` and `social_link`. You may also ship a `plugin.json`
(or `shinsekai.plugin.json`) in the repo root carrying these fields — when fields are
missing, the local submission helper (`scan_local_plugin`) falls back to your README's
first `#` heading (display name), the first paragraph after it (description), the git
remote (repo), and the directory name.

### Market pipeline, versioning, and trust levels

```text
write plugin → submit issue → CI opens PR → maintainer merges → R2 packaging → market install
```

Registry CI clones your repo, infers the `entry` (the `plugin.py` closest to the repo
root, AST-parsed for a `PluginBase` subclass — class names ending in `Plugin` win),
then opens a review PR. Before distribution the pipeline runs a static scan (credential
leaks, dangerous calls) plus a ClamAV virus scan, and packages the source to R2 object
storage with a SHA256 checksum.

Version resolution per repackage: **Latest Release → newest tag → default branch HEAD**
(fallback version `v0.0.0`). Two gotchas:

- `plugin_version` only controls what the market and client **display**; it does not
  pick the commit CI packages. Bump it **and** tag a new Release for every release.
- Once a repo has used a Release/Tag, pushes to the default branch alone no longer
  trigger repackaging.

| Trust level | Meaning |
| --- | --- |
| `community` | default; passed basic CI checks — **not** a security audit |
| `verified` | maintainer manually reviewed a specific commit + version (request via a `Verification Request` issue) |
| `verified_update_pending` | a verified plugin published newer code; re-review pending |
| `blocked` | banned from the market |

### Plugin dependencies

Ship a `requirements.txt` next to your plugin. It is installed when the user **installs
or updates** the plugin (not on every launch). Details worth knowing:

- **Precheck pruning** — already-satisfied lines are skipped; only missing/unsatisfied
  ones go to pip. Files using special syntax (`-e`, `--find-links`, …) are passed
  through whole.
- **PyTorch routing** — `torch` / `torchvision` / `torchaudio` install from the PyTorch
  wheel index, with the CUDA channel picked from `nvidia-smi` (≥ 12.4 → `cu124`, ≥ 12 →
  `cu121`, ≥ 11.8 → `cu118`, otherwise CPU wheels).
- **Install target** — source checkouts install into the current Python environment;
  packaged builds run the bundled runtime Python with
  `pip install --target data/plugin_site_packages`.
- **Result codes** — `pip_ok`, `pip_skip_no_requirements`, `pip_failed`,
  `pip_conflict`, `pip_timeout` (overall timeout 900 s), `pip_exception`.
- **Mirrors** — China mirrors (Tsinghua → USTC → HIT) are preferred when region
  settings say so, with official PyPI as fallback. Any of `PIP_INDEX_URL` /
  `PIP_EXTRA_INDEX_URL` / `PIP_NO_INDEX` / `PIP_CONFIG_FILE` in the environment
  disables mirror injection entirely; `SHINSEKAI_PIP_INDEX_URL(S)`,
  `SHINSEKAI_RUNTIME_SOURCE`, and `SHINSEKAI_MIRROR_REGION` override the choice. A
  requirements file that sets its own `-i` / `--index-url` / `--no-index` is left
  untouched.

Document download size, model caches, and hardware requirements in your README for
heavy dependencies; put model downloads in `host.huggingface_cache_dir` or
`plugin_root`, never in your source tree.

---

## Testing plugins

Keep plugin-specific tests with the plugin, not in the host repository's top-level
`test/` tree. The Shinsekai CI only checks code that is tracked by the main repository;
optional or locally installed packages under `plugins/` may be absent on GitHub Actions,
so tests such as `test/unit/test_<plugin_name>.py` must not import
`plugins.<plugin_name>`.

Use this split:

- **Plugin business logic:** test it in the plugin's own repository, or in the plugin
  package beside the code, for example `plugins/my_plugin/tests/`.
- **Host/plugin contract:** test it in this repository with fake plugins or fixtures
  under `test/fixtures/`, not with a real optional plugin package.
- **SDK behavior:** test shared helpers in the main repository when the code lives in
  `sdk/`, `core/plugins/`, or another tracked host module.

A plugin test suite can depend on the host SDK by installing or checking out Shinsekai
in CI, then running the plugin's own tests:

```bash
python -m pip install -e /path/to/Shinsekai
python -m pytest
```

For a plugin repository, a typical layout is:

```text
my_plugin/
  pyproject.toml
  my_plugin/
    __init__.py
    plugin.py
    normalizer.py
  tests/
    test_normalizer.py
    test_plugin_registration.py
```

If you need to verify host discovery or registration behavior in Shinsekai's main CI,
create a tiny fake plugin fixture that is committed with the tests. Do not rely on a
downloaded, ignored, or user-local plugin directory.

---

## Part 3 — Wrap-up

### Before you ship

- Stable `plugin_id` / semver `plugin_version` (bump it on every release; the market
  reads it for display).
- Document the exact `entry` string and any **provider keys** users must select in
  Settings.
- Optional `requirements.txt`; note GPU / external binaries if needed.
- Restart required after `plugins.yaml` changes.
- Prefer `@tool` + `PluginSettingsUIContext` / `ChatUIContext` over reaching into host
  internals.
- Tag a GitHub Release (or at least a tag like `v0.1.0`) — the registry CI resolves
  Latest Release → newest tag → default branch HEAD, in that order, and only repackages
  when the resolved commit changes.
- Never commit tokens, cookies, `.env` files, account configs, caches, virtualenvs, or
  build artifacts; don't perform unrelated system modifications at install time.
- Say in the README **why** the plugin needs each network request, file access, or
  external command — the market's static scan and reviewers look for exactly that.

### Official example plugins

| Repository | Demonstrates |
| --- | --- |
| [Shinsekai-Whisper-Asr](https://github.com/RachelForster/Shinsekai-Whisper-Asr) | ASR adapter (faster-whisper / RealtimeSTT) |
| [Shinsekai-bilibili-live](https://github.com/RachelForster/Shinsekai-bilibili-live) | user-input trigger (Bilibili danmaku → chat input) |
| [Shinsekai-Playwright-Browser](https://github.com/RachelForster/Shinsekai-Playwright-Browser) | LLM tools + browser automation + bundled frontend page |
| [Shinsekai-Moondream-Vision](https://github.com/RachelForster/Shinsekai-Moondream-Vision) | vision tools + the slow-loading-model pattern |
| [Shinsekai-ChatUI-Customize](https://github.com/RachelForster/Shinsekai-ChatUI-Customize) | chat-UI theme customization |

### FAQ

**Changed `plugins.yaml` but nothing happened?** Restart the host process (on the
desktop app, the Plugin Manager's Reload action restarts the plugin service for you).
Only MCP config is save-and-apply.

**Plugin didn't load, and there was no error popup?** Load failures only go to the
logs. Look for `initialize failed for <plugin_id>` or an import error; check the
`entry` spelling, the class name, and the `PluginBase` inheritance.

**Can't read the API key inside `initialize`?** By design. Secrets are injected only
when an adapter instance is constructed at runtime; the `host` snapshot never carries
them.

**Adapter constructor got unexpected parameters?** The host merges shared config fields
with your schema's extras (`merged_*_factory_kwargs`) and filters them against your
`__init__` signature; with `**kwargs` you receive everything — ignore unknown keys.

**Market update not detected?** CI only reacts to Release/Tag changes once a repo has
used one — pushes to the default branch alone don't trigger repackaging. Tag a new
Release for each version.

### Source map

| Topic                        | Location                                                     |
| ---------------------------- | ------------------------------------------------------------ |
| Plugin base                  | `sdk/plugin.py`                                              |
| Registry                     | `sdk/register.py`                                            |
| Contribution types           | `sdk/types.py` (also: `OutputFieldSpec`, `RequirementSpec`, `FieldPatch`, `RequirementPatch`, `OutputContractPatch`, `ChatOutputContract`, `WorkflowContribution`, `FrontendConfigAction`) |
| Host snapshot / settings ctx | `sdk/plugin_host_context.py`                                 |
| Chat UI ctx                  | `sdk/chat_ui_context.py`                                     |
| Adapter ABCs                 | `sdk/adapters/*.py`                                          |
| Messages / handler ABCs      | `sdk/messages.py` / `sdk/handlers.py`                        |
| Tool registry                | `sdk/tool_registry.py`                                       |
| Hooks                        | `sdk/hooks.py`                                               |
| DAG                          | `sdk/graph.py`                                               |
| Chat-UI theme packs          | `sdk/chat_ui_theme.py`                                       |
| Logging facade               | `sdk/logging/`                                               |
| Exceptions                   | `sdk/exception/`                                             |
| Plugin manager               | `sdk/manager.py`                                             |
| Host wiring                  | `core/plugins/plugin_host.py`                                |
| Requirements install         | `core/plugins/plugin_requirements_install.py`, `pip_index_config.py` |
| Publisher metadata/validation | `core/plugins/publisher/`                                   |
| Extra ctor kwargs            | `config/adapter_extra_kwargs.py`, `config/config_manager.py` |
| CLI                          | `sdk/cli/`                                                   |

This guide stays aligned with `PluginCapabilityRegistry` in `sdk/register.py`; if APIs
drift, treat that file as the source of truth.

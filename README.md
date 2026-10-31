# model-sunset-scanner

Find OpenAI and Anthropic models (and endpoints) that are **already shut down or scheduled for shutdown** in:

- **n8n** workflow exports (`.json`), including nodes that save **no model name at all** because n8n strips parameters left at their default
- **Make** scenario blueprints (`.json`)
- **any code or text** (`.py`, `.js`, `.ts`, `.env`, `.yaml`, `.md`, …), file by file or a whole directory

For each finding it prints the shutdown date, the official replacement, and the request parameters that need to change (where the provider documents them).

Rules come only from the providers' official deprecation pages (see the [rule table](#rules)). **By default only `verified` rules are reported.** Rules that rest on our own inference (undated aliases such as `gpt-4o`) are listed separately and reported only with `--include-unverified`.

Offline, read-only: the scanner makes no network calls and never modifies your files.

## Install

Python 3.9+ and PyYAML.

```bash
git clone https://github.com/paopao-studio-ai/model-sunset-scanner model-sunset-scanner
cd model-sunset-scanner
pip install -r requirements.txt
```

## Usage

```bash
python3 model_sunset_scan.py PATH [PATH ...] [--md report.md] [--json report.json]
                             [--today YYYY-MM-DD] [--include-unverified] [--rules models.yaml]
```

- Without `--md` / `--json` the Markdown report is printed to stdout.
- `--today` sets the reference date that decides `already_shut_down` vs `scheduled` (default: today).
- Exit code is `1` if anything is reported, `0` otherwise, so you can use it in CI.
- The input type is detected from the file content, not the file name.

### 1. n8n workflow export

In n8n: *Workflow menu → Download* (or `n8n export:workflow --all --separate --output=./flows/`), then:

```bash
python3 model_sunset_scan.py examples/n8n_workflow.json
python3 model_sunset_scan.py ./flows/            # a whole directory
```

Both a bare workflow (`{"nodes": [...]}`) and the wrapped form (`{"workflow": {"nodes": [...]}}`) are accepted. What it checks:

- explicit `model` / `modelId` / `modelName` values, including resource-locator objects (`{"__rl": true, "value": "gpt-4o-2024-08-06"}`) and expression literals (`={{ 'gpt-4o-2024-08-06' }}`). Fully dynamic expressions (`={{ $json.model }}`) are listed as info because they cannot be resolved statically.
- **omitted models** on nodes where n8n falls back to a default: OpenAI Chat Model, Anthropic Chat Model (per `typeVersion`), OpenAI (vendor node: audio, image), legacy OpenAI node, OpenAI Assistant, OpenRouter Chat Model, OpenAI LLM. Each such finding links to the line in the n8n source that defines the default. Some defaults changed between n8n releases without a `typeVersion` bump; the report says so when that applies.
- models that n8n **hardcodes** (e.g. `whisper-1` for the OpenAI node's transcribe/translate operations).
- Assistants API usage (OpenAI node `resource: assistant` before v2, the old OpenAI Assistant node, HTTP calls to `/v1/assistants` or `/v1/threads`) and `/v1/audio/translations`.
- HTTP Request nodes that call `api.openai.com` / `api.anthropic.com`, and Code / Function nodes.
- sampling options (`temperature`, `topP`, `maxTokens`, …) set on the same node that the replacement model handles differently.
- Mentions in sticky notes and prompts are listed under *Info only* and are not counted.

### 2. Make blueprint

In Make: *scenario → ⋯ → Export Blueprint*, then:

```bash
python3 model_sunset_scan.py examples/make_blueprint.json
```

Modules are walked recursively (including router branches). Values in `model`, `model_id`, `modelId` or `engine` fields, or values that look like a bare model ID, are reported; model names inside free text are listed as info only.

### 3. Code / any text

```bash
python3 model_sunset_scan.py examples/app.py
python3 model_sunset_scan.py path/to/your/repo/
```

Every line is checked for model IDs. `.git`, `node_modules`, `__pycache__`, `.venv`, `dist` and `build` are skipped. Text mode cannot tell a real call from a comment or a string in a test fixture; see [Known limitations](#known-limitations).

### Example output

Running `python3 model_sunset_scan.py examples/ --today 2026-10-31` on the three synthetic files in `examples/` reports 8 findings from verified rules (3 already shut down, 5 scheduled), for example:

| File | Node | Model | Source | Shutdown | Status | Replacement |
|---|---|---|---|---|---|---|
| n8n_workflow.json | Image: Generate | `dall-e-3` | default (model omitted) | 2026-05-12 | already_shut_down | gpt-image-2, gpt-image-1, or gpt-image-1-mini |
| n8n_workflow.json | Writer (Claude) | `claude-sonnet-4-5-20250929` | explicit | 2026-11-30 | scheduled | claude-sonnet-5-5 |
| n8n_workflow.json | OpenAI Chat Model (default) | `gpt-5-mini` | default (model omitted) | 2026-12-11 | scheduled | gpt-5.6-terra |
| n8n_workflow.json | OpenAI Chat Model (pinned) | `gpt-4o-2024-08-06` | explicit | 2027-01-14 | scheduled | gpt-6-luna |
| n8n_workflow.json | Transcribe audio | `whisper-1` | hardcoded by n8n | 2027-02-26 | scheduled | gpt-live-transcribe or gpt-transcribe |

The `gpt-4o-mini` node in the same workflow and the `gpt-4o` line in `app.py` are **not** reported by default: they match only unverified alias rules and appear under "Not reported … UNVERIFIED rules".

## Rules

All rules live in [`models.yaml`](models.yaml). Every entry has the provider, model IDs, shutdown date, official replacement, `status`, `verified_on` and `source_url`; some also list `params_to_change` with a verbatim quote and a link to the doc it comes from.

- **verified**: the model ID and the shutdown date both appear verbatim on the provider's official deprecations page, checked on the `verified_on` date.
- **unverified**: an alias or family inference that is not stated on an official page. Never reported unless you pass `--include-unverified`, and then marked `[UNVERIFIED rule]` in the report.
- A dated ID that is not listed itself but matches an alias/family entry (e.g. `gpt-4o-realtime-2099-01-01` → `gpt-4o-realtime`) is also treated as unverified.

Official sources (checked 2026-10-31):

- OpenAI: <https://developers.openai.com/api/docs/deprecations>
- Anthropic: <https://platform.claude.com/docs/en/about-claude/model-deprecations>

Dates change. If a provider updates its page, edit `models.yaml` with the new source and date (or open a PR).

### Verified rules (reported by default)

72 rule groups. Sorted by shutdown date, newest first.

| Model / API | Shutdown date | Replacement (official) | Official source | Verified on | Status |
|---|---|---|---|---|---|
| `gpt-5.3-codex` | 2027-04-01 | gpt-6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5.4-nano`, `gpt-5.4-nano-2026-03-17` | 2027-04-01 | gpt-6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5.1`, `gpt-5.1-2025-11-13` | 2027-04-01 | gpt-6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-mini-transcribe-2025-12-15`, `gpt-4o-transcribe-diarize` | 2027-02-26 | gpt-live-transcribe or gpt-transcribe | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `/v1/audio/translations` | 2027-02-26 | v1/realtime/translations | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-realtime`, `gpt-realtime-2025-08-28`, `gpt-4o-realtime` | 2027-01-20 | gpt-realtime-2.1 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-audio`, `gpt-audio-2025-08-28`, `gpt-4o-audio`, `gpt-audio-mini`, `gpt-audio-mini-2025-12-15`, `gpt-4o-mini-audio` | 2027-01-20 | gpt-audio-1.5 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-realtime-mini`, `gpt-realtime-mini-2025-12-15`, `gpt-4o-mini-realtime` | 2027-01-20 | gpt-realtime-2.1-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-mini-transcribe-2025-03-20` | 2027-01-20 | gpt-4o-mini-transcribe-2025-12-15 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-2024-08-06`, `gpt-4o-2024-11-20` | 2027-01-14 | gpt-6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-mini-2024-07-18` | 2027-01-14 | gpt-6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4.1-2025-04-14` | 2027-01-14 | gpt-6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4.1-mini-2025-04-14` | 2027-01-14 | gpt-6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`, `gpt-4o-mini-tts-2025-03-20`, `gpt-4o-mini-tts-2025-12-15` | 2027-01-06 | gpt-realtime-2.1-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5`, `gpt-5-2025-08-07` | 2026-12-11 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5-mini`, `gpt-5-mini-2025-08-07` | 2026-12-11 | gpt-5.6-terra | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5-nano`, `gpt-5-nano-2025-08-07` | 2026-12-11 | gpt-5.6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5-pro`, `gpt-5-pro-2025-10-06` | 2026-12-11 | gpt-5.6-sol (reasoning.mode: pro) | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `o3`, `o3-2025-04-16` | 2026-12-11 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `o3-pro`, `o3-pro-2025-06-10` | 2026-12-11 | gpt-5.6-sol (reasoning.mode: pro) | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-image-1-mini`, `gpt-image-1.5`, `gpt-image-1.5-2025-12-16`, `chatgpt-image-latest` | 2026-12-01 | gpt-image-2.5-sunburst or gpt-image-2.5-flare | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-sonnet-4-5-20250929` | 2026-11-30 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `gpt-3.5-turbo-0125`, `gpt-3.5-turbo`, `gpt-3.5-turbo-completions` | 2026-10-23 | gpt-5.6-terra | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4-0613`, `gpt-4`, `gpt-4-0613-completions`, `gpt-4-completions` | 2026-10-23 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4-1106-preview` | 2026-10-23 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4-turbo`, `gpt-4-turbo-2024-04-09`, `gpt-4-turbo-completions` | 2026-10-23 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4.1-nano`, `gpt-4.1-nano-2025-04-14` | 2026-10-23 | gpt-5.6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-2024-05-13` | 2026-10-23 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-image-1` | 2026-10-23 | gpt-image-2.5-sunburst or gpt-image-2.5-flare | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `o1`, `o1-2024-12-17`, `o3-mini`, `o3-mini-2025-01-31` | 2026-10-23 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `o1-pro`, `o1-pro-2025-03-19` | 2026-10-23 | gpt-5.6-sol (reasoning.mode: pro) | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `o4-mini`, `o4-mini-2025-04-16`, `ft-o4-mini-2025-04-16` | 2026-10-23 | gpt-5.6-terra | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5.4-cyber` | 2026-10-01 | The most capable cyber model available to you. | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-3.5-turbo-instruct`, `babbage-002`, `davinci-002`, `gpt-3.5-turbo-1106` | 2026-09-28 | gpt-5.6-terra | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `sora-2`, `sora-2-pro`, `sora-2-2025-10-06`, `sora-2-2025-12-08`, `sora-2-pro-2025-10-06` | 2026-09-24 | — | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `Assistants API` | 2026-08-26 | Responses API and Conversations API | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5.2-chat-latest`, `gpt-5.3-chat-latest` | 2026-08-10 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-opus-4-1-20250805` | 2026-08-05 | claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `computer-use-preview`, `computer-use-preview-2025-03-11`, `gpt-4o-mini-search-preview`, `gpt-4o-mini-search-preview-2025-03-11`, `gpt-4o-search-preview`, `gpt-4o-search-preview-2025-03-11`, `gpt-5.1-codex-mini` | 2026-07-23 | gpt-5.6-terra | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-5-chat-latest`, `gpt-5-codex`, `gpt-5.1-chat-latest`, `gpt-5.1-codex`, `gpt-5.1-codex-max`, `o3-deep-research`, `o3-deep-research-2025-06-26`, `o4-mini-deep-research`, `o4-mini-deep-research-2025-06-26`, `gpt-5.2-codex` | 2026-07-23 | gpt-5.6-sol | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-audio-mini-2025-10-06` | 2026-07-23 | gpt-audio-1.5 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-realtime-mini-2025-10-06` | 2026-07-23 | gpt-realtime-2.1-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-sonnet-4-20250514` | 2026-06-15 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `claude-opus-4-20250514` | 2026-06-15 | claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `dall-e-2`, `dall-e-3` | 2026-05-12 | gpt-image-2, gpt-image-1, or gpt-image-1-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-realtime-preview`, `gpt-4o-realtime-preview-2025-06-03`, `gpt-4o-realtime-preview-2024-12-17` | 2026-05-07 | gpt-realtime-1.5 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-mini-realtime-preview` | 2026-05-07 | gpt-realtime-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-audio-preview` | 2026-05-07 | gpt-audio-1.5 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-mini-audio-preview` | 2026-05-07 | gpt-audio-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-3-haiku-20240307` | 2026-04-20 | claude-haiku-4-5-20251001 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `gpt-4-0314`, `gpt-4-0125-preview`, `gpt-4-turbo-preview` | 2026-03-26 | gpt-5 or gpt-4.1* | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-3-5-haiku-20241022` | 2026-02-19 | claude-haiku-4-5-20251001 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `claude-3-7-sonnet-20250219` | 2026-02-19 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `chatgpt-4o-latest` | 2026-02-17 | gpt-5.1-chat-latest | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `codex-mini-latest` | 2026-02-12 | gpt-5-codex-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-3-opus-20240229` | 2026-01-05 | claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `claude-3-5-sonnet-20240620`, `claude-3-5-sonnet-20241022` | 2025-10-28 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `text-moderation-007`, `text-moderation-stable`, `text-moderation-latest` | 2025-10-27 | omni-moderation | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `o1-mini` | 2025-10-27 | o4-mini | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-realtime-preview-2024-10-01` | 2025-10-10 | gpt-realtime-1.5 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4o-audio-preview-2024-10-01` | 2025-10-10 | gpt-audio-1.5 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `o1-preview` | 2025-07-28 | o3 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-2.0`, `claude-2.1` | 2025-07-21 | claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `claude-3-sonnet-20240229` | 2025-07-21 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `gpt-4.5-preview` | 2025-07-14 | gpt-4.1 | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4-32k`, `gpt-4-32k-0613`, `gpt-4-32k-0314` | 2025-06-06 | gpt-4o | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-4-vision-preview`, `gpt-4-1106-vision-preview` | 2024-12-06 | gpt-4o | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `claude-1.0`, `claude-1.1`, `claude-1.2`, `claude-1.3`, `claude-instant-1.0`, `claude-instant-1.1`, `claude-instant-1.2` | 2024-11-06 | claude-haiku-4-5-20251001 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | 2026-10-31 | verified |
| `gpt-3.5-turbo-0613`, `gpt-3.5-turbo-16k-0613` | 2024-09-13 | gpt-3.5-turbo | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `gpt-3.5-turbo-0301` | 2024-09-13 | gpt-3.5-turbo | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `text-ada-001`, `text-babbage-001`, `text-curie-001`, `text-davinci-001`, `text-davinci-002`, `text-davinci-003` | 2024-01-04 | gpt-3.5-turbo-instruct | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |
| `text-davinci-edit-001`, `code-davinci-edit-001` | 2024-01-04 | gpt-4o | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | 2026-10-31 | verified |

### Unverified rules (reported only with `--include-unverified`)

10 rule groups. The official tables list dated snapshots (and, for OpenAI, family headings) but not these undated aliases. Mapping an alias such as `gpt-4o` or `claude-sonnet-4-5` to the retiring snapshot is **our inference**, not an official statement, so these rules are off by default. In particular, this tool does **not** claim that the undated `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` or `gpt-4.1-mini` aliases will be shut down.

| Model / API | Shutdown date | Replacement (official) | Official source | Verified on | Status |
|---|---|---|---|---|---|
| `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini` | 2027-01-14 | gpt-6-luna | [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-sonnet-4-5` | 2026-11-30 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-opus-4-1` | 2026-08-05 | claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-sonnet-4-0`, `claude-opus-4-0` | 2026-06-15 | claude-sonnet-5-5 / claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-3-7-sonnet-latest` | 2026-02-19 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-3-5-haiku-latest` | 2026-02-19 | claude-haiku-4-5-20251001 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-3-opus-latest` | 2026-01-05 | claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-3-5-sonnet-latest` | 2025-10-28 | claude-sonnet-5-5 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-2` | 2025-07-21 | claude-opus-4-8 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |
| `claude-instant-1` | 2024-11-06 | claude-haiku-4-5-20251001 | [Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) | — | **UNVERIFIED** (not reported by default) |

### Out of scope

Azure OpenAI, AWS Bedrock, Google Vertex AI and OpenRouter publish their own retirement schedules for same-named models. Those schedules are **not** covered. Findings for models called through a router prefix such as `openai/…` carry a note saying the router's own date applies.

## Known limitations

- **Example strings cause false positives.** In code and text mode, and in n8n Code / Set nodes, a model ID inside a sample payload, a test fixture or a demo string is reported as if it were used. In our dev evaluation, both false positives were exactly this case: a "Set input data" node whose sample JSON contained `gpt-4o`.
- **Self-test numbers.** Measured on public n8n workflow files from public GitHub template collections, scored per (node, model) pair, reference date 2026-10-31:

  | Set | Rules | Files | Labelled positives | TP | FP | FN | Precision | Recall |
  |---|---|---|---|---|---|---|---|---|
  | Dev (seen during development, **not blind**) | all (`--include-unverified`) | 68 | 102 | 102 | 2 | 0 | 0.981 | 1.000 |
  | Dev | verified only (default) | 68 | 64 | 64 | 0 | 0 | 1.000 | 1.000 |
  | Holdout (random, seed 20261031, labelled after the scanner was frozen) | all (`--include-unverified`) | 25 | 25 | 25 | 0 | 0 | 1.000 | 1.000 |
  | Holdout | verified only (default) | 25 | 11 | 11 | 0 | 0 | 1.000 | 1.000 |

  The holdout is small (25 positives with all rules, 11 with verified rules only), so these numbers are not a guarantee of production accuracy.
- **Same-source bias in the gold labels.** The labels were written by the same person who wrote the scanner, using the same reading of n8n's defaults. Errors in that shared understanding would not show up as false positives or false negatives. Independent labelling has not been done.
- **n8n defaults depend on the n8n version.** For a node saved without a model, the reported model is the default in current n8n source (pinned commit linked in each finding). Older n8n releases used different defaults for the same `typeVersion` (e.g. OpenAI Chat Model: `gpt-4o-mini` → `gpt-4.1-mini` → `gpt-5-mini`); the report lists these alternatives.
- Dynamic expressions, credentials-level settings and models chosen at run time cannot be resolved statically.
- Fine-tuned models (`ft:…`) are matched to their base model's rule; the provider may handle fine-tunes differently.
- Only OpenAI and Anthropic rules are included.

## Development

```bash
pip install -r requirements.txt pytest
python3 -m pytest -q
```

## License

MIT, see [LICENSE](LICENSE). Not affiliated with OpenAI, Anthropic, n8n or Make.

---

Need help migrating? https://paopao-studio.pages.dev/

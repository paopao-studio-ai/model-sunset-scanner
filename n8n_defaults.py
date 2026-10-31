"""Default models applied by n8n when the `model` parameter is omitted from saved workflow JSON
(n8n strips parameters equal to their default on save/export).
Evidence: n8n-io/n8n @ 50bdfb2ea8b431a84ce56419d8b39129a5186353 (HEAD on 2026-10-31)."""
SHA = "50bdfb2ea8b431a84ce56419d8b39129a5186353"
GH = f"https://github.com/n8n-io/n8n/blob/{SHA}/"
LC = "packages/@n8n/nodes-langchain/nodes/"

def _v(tv):
    try: return float(tv)
    except (TypeError, ValueError): return 1.0

def lmChatOpenAi(tv, params):
    ev = [GH + LC + "llms/LMChatOpenAi/LmChatOpenAi.node.ts#L201", GH + LC + "llms/LMChatOpenAi/LmChatOpenAi.node.ts#L213"]
    hist = ("n8n changed this default without bumping typeVersion: up to PR#15975 (2025-06-05) it was gpt-4o-mini, "
            "then gpt-4.1-mini (resource locator), and since PR#24342 (merged 2026-01-15) gpt-5-mini for all versions. "
            "The model actually used depends on the n8n version that runs the workflow.")
    return {"model": "gpt-5-mini", "alt_models_older_n8n": ["gpt-4.1-mini", "gpt-4o-mini"], "evidence": ev,
            "prs": ["https://github.com/n8n-io/n8n/pull/15975", "https://github.com/n8n-io/n8n/pull/24342"], "note": hist}

def lmChatAnthropic(tv, params):
    f = GH + LC + "llms/LMChatAnthropic/LmChatAnthropic.node.ts"
    v = _v(tv)
    if v < 1.1: m, l = "claude-2", 87
    elif v < 1.2: m, l = "claude-3-sonnet-20240229", 183
    elif v < 1.3: m, l = "claude-3-5-sonnet-20240620", 192
    elif v < 1.4: m, l = "claude-sonnet-4-5-20250929", 206
    elif v < 1.6: m, l = "claude-sonnet-4-6", 243 if v < 1.5 else 280
    else: m, l = "claude-sonnet-5", 317
    note = None
    if 1.3 <= v < 1.4:
        note = ("The v1.3 default changed across n8n releases without a typeVersion bump: claude-3-7-sonnet (PR#13543) -> "
                "claude-sonnet-4-20250514 (PR#15609) -> claude-sonnet-4-5-20250929 (PR#20924).")
    return {"model": m, "evidence": [f"{f}#L{l}"], "note": note,
            "alt_models_older_n8n": ["claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219"] if 1.3 <= v < 1.4 else []}

def lmOpenAi(tv, params):
    return {"model": "gpt-3.5-turbo-instruct", "evidence": [GH + LC + "llms/LMOpenAi/LmOpenAi.node.ts#L89"]}

def openAiAssistant(tv, params):
    return {"model": "gpt-3.5-turbo-1106", "evidence": [GH + LC + "agents/OpenAiAssistant/OpenAiAssistant.node.ts#L173"]}

def lmChatOpenRouter(tv, params):
    return {"model": "openai/gpt-4.1-mini", "evidence": [GH + LC + "llms/LmChatOpenRouter/LmChatOpenRouter.node.ts#L187"],
            "note": "Routed via OpenRouter; OpenRouter's own retirement schedule is not verified"}

def openAiVendor(tv, params):
    """@n8n/n8n-nodes-langchain.openAi (v1: 1–1.8, v2: 2–2.3)."""
    v = _v(tv); r = params.get("resource", "text"); op = params.get("operation")
    base = GH + LC + "vendors/OpenAi/" + ("v2" if v >= 2 else "v1") + "/actions/"
    if r == "audio":
        op = op or "generate"
        if op in ("transcribe", "translate"):
            return {"model": "whisper-1", "hardcoded": True, "endpoint": "/v1/audio/translations" if op == "translate" else None,
                    "evidence": [base + f"audio/{op}.operation.ts#L{51 if op=='translate' else 59}"],
                    "note": "Hardcoded in n8n (const model = 'whisper-1'); it cannot be changed in the node. Replace the node with an HTTP Request or wait for an n8n update."}
        if op == "generate":
            return {"model": "tts-1", "evidence": [base + "audio/generate.operation.ts#L16"]}
    if r == "image":
        op = op or "generate"
        if op == "generate":
            if v >= 2.2: return {"model": "gpt-image-1-mini", "evidence": [base + "image/generate.operation.ts#L43"]}
            return {"model": "dall-e-3", "evidence": [base + "image/generate.operation.ts#L" + ("19" if v >= 2 else "16")]}
        if op == "edit":
            return {"model": "gpt-image-1", "evidence": [base + "image/edit.operation.ts#L" + ("42" if v >= 2.3 else "22")]}
        if op == "analyze":
            if v < 1.4: return {"model": "gpt-4-vision-preview", "hardcoded": True,
                                "evidence": [GH + LC + "vendors/OpenAi/v1/actions/image/analyze.operation.ts#L132"]}
            return {"model": "gpt-4o", "evidence": [base + "image/analyze.operation.ts#L" + ("135" if v >= 2 else "134")],
                    "note": "Code fallback used only when modelId is missing; the resource-locator default is empty, so the model is usually saved explicitly"}
    return None  # text/message/assistant etc: modelId default '' -> always explicit

def legacyOpenAi(tv, params):
    """n8n-nodes-base.openAi (legacy)."""
    r = params.get("resource", "text"); op = params.get("operation")
    p = GH + "packages/nodes-base/nodes/OpenAi/"
    if r == "chat": return {"model": "gpt-3.5-turbo", "evidence": [p + "ChatDescription.ts#L94"]}
    if r == "image": return {"model": "dall-e-2", "evidence": [p + "ImageDescription.ts#L73"]}
    if r == "text":
        if (op or "complete") == "complete": return {"model": "gpt-3.5-turbo-instruct", "evidence": [p + "TextDescription.ts#L119"]}
        if op == "edit": return {"model": "text-davinci-edit-001", "evidence": [p + "TextDescription.ts#L175"]}
    return None

# node type -> (resolver, parameter name holding the model)
DEFAULTS = {
    "@n8n/n8n-nodes-langchain.lmChatOpenAi": (lmChatOpenAi, "model"),
    "@n8n/n8n-nodes-langchain.lmChatAnthropic": (lmChatAnthropic, "model"),
    "@n8n/n8n-nodes-langchain.lmOpenAi": (lmOpenAi, "model"),
    "@n8n/n8n-nodes-langchain.openAiAssistant": (openAiAssistant, "model"),
    "@n8n/n8n-nodes-langchain.lmChatOpenRouter": (lmChatOpenRouter, "model"),
    "@n8n/n8n-nodes-langchain.openAi": (openAiVendor, None),
    "n8n-nodes-base.openAi": (legacyOpenAi, "model"),
}

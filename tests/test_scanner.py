import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import model_sunset_scan as S

RULES = S.Rules()                              # default: verified rules only
RULES_ALL = S.Rules(include_unverified=True)   # verified + unverified
TODAY = "2026-10-31"
LC = "@n8n/n8n-nodes-langchain."

def wf(*nodes):
    return {"nodes": [dict(name=n.get("name", f"n{i}"), type=n["type"], typeVersion=n.get("tv", 1), parameters=n.get("p", {})) for i, n in enumerate(nodes)]}

def scan_obj(tmp_path, obj, name="w.json", rules=RULES):
    f = tmp_path / name
    f.write_text(obj if isinstance(obj, str) else json.dumps(obj))
    return S.scan([str(f)], today=TODAY, rules=rules)

def models(res): return sorted(h["model"] for h in res["hits"])

# --- look-alike names ---------------------------------------------------------
def test_lookalike_tokens():
    assert S.tokens_in_text("use gpt-4o-realtime-preview here") == ["gpt-4o-realtime-preview"]
    assert S.tokens_in_text("gpt-4.1-nano") == ["gpt-4.1-nano"]
    assert "gpt-4o" not in S.tokens_in_text("gpt-4o-mini")
    assert S.tokens_in_text("x gpt-4o, y") == ["gpt-4o"]

def test_lookalike_rules_differ():
    a = RULES.lookup("gpt-4.1")[0]; b = RULES.lookup("gpt-4.1-nano")[0]
    assert a["shutdown_date"] == "2027-01-14" and b["shutdown_date"] == "2026-10-23"
    assert RULES.lookup("gpt-4o")[0] is not RULES.lookup("gpt-4o-realtime-preview")[0]

def test_unknown_model_not_hit():
    assert RULES.lookup("gpt-6-luna") is None
    assert RULES.lookup("claude-sonnet-5-5") is None

# --- dated suffixes -------------------------------------------------------------
def test_dated_snapshot_exact():
    e, mid, how, _ = RULES.lookup("gpt-4o-2024-08-06")
    assert e["shutdown_date"] == "2027-01-14" and how == "exact" and e["status"] == "verified"

def test_claude_dated():
    assert RULES.lookup("claude-sonnet-4-5-20250929")[0]["shutdown_date"] == "2026-11-30"

def test_prefixes_and_finetune():
    assert RULES.lookup("openai/gpt-4o-mini")[3] == "openai"
    assert RULES.lookup("ft:gpt-4o-mini-2024-07-18:acme::abc")[2] == "fine-tune"

# --- n8n: explicit, __rl, expressions ------------------------------------------
def test_rl_value(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatOpenAi", "tv": 1.2, "p": {"model": {"__rl": True, "mode": "list", "value": "gpt-4.1-mini"}}}), rules=RULES_ALL)
    assert models(r) == ["gpt-4.1-mini"] and r["hits"][0]["source"] == "explicit-resourceLocator"

def test_expression_literal(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatOpenAi", "tv": 1, "p": {"model": "={{ 'gpt-4o' }}"}}), rules=RULES_ALL)
    assert models(r) == ["gpt-4o"]

def test_expression_dynamic_goes_info(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatOpenAi", "tv": 1, "p": {"model": "={{ $json.model }}"}}))
    assert r["hits"] == [] and any("dynamic" in i["why"] for i in r["info"])

def test_empty_modelid_not_hit(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "openAi", "tv": 1.8, "p": {"modelId": {"__rl": True, "value": ""}}}))
    assert r["hits"] == []

# --- default omission per typeVersion --------------------------------------------
def test_openai_default(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatOpenAi", "tv": 1, "p": {"options": {}}}))
    h = r["hits"][0]
    assert h["model"] == "gpt-5-mini" and h["source"] == "default" and h["evidence"][0].startswith("https://github.com/n8n-io/n8n/blob/")

@pytest.mark.parametrize("tv,model", [(1, "claude-2"), (1.1, "claude-3-sonnet-20240229"), (1.2, "claude-3-5-sonnet-20240620"),
                                      (1.3, "claude-sonnet-4-5-20250929")])
def test_anthropic_default_by_version(tmp_path, tv, model):
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatAnthropic", "tv": tv, "p": {}}), rules=RULES_ALL)
    assert models(r) == [model]
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatAnthropic", "tv": tv, "p": {}}))
    if model == "claude-2":  # undated alias -> unverified rule, not reported by default
        assert r["hits"] == [] and [h["model"] for h in r["unverified"]] == ["claude-2"]
    else:
        assert models(r) == [model]

def test_anthropic_16_default_not_retiring(tmp_path):
    # v1.6 default is claude-sonnet-5 which has no retirement rule
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatAnthropic", "tv": 1.6, "p": {}}))
    assert r["hits"] == []

def test_anthropic_sampling_params_flagged(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "lmChatAnthropic", "tv": 1.3, "p": {"model": {"__rl": True, "value": "claude-sonnet-4-5-20250929"}, "options": {"temperature": 0.5}}}))
    assert "temperature" in r["hits"][0]["node_param_findings"]

def test_hardcoded_whisper(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "openAi", "tv": 1.8, "p": {"resource": "audio", "operation": "transcribe"}}))
    assert models(r) == ["whisper-1"] and r["hits"][0]["source"] == "hardcoded"

def test_vendor_image_default_by_version(tmp_path):
    assert models(scan_obj(tmp_path, wf({"type": LC + "openAi", "tv": 1.7, "p": {"resource": "image"}}))) == ["dall-e-3"]

def test_legacy_openai_chat_default(tmp_path):
    assert models(scan_obj(tmp_path, wf({"type": "n8n-nodes-base.openAi", "tv": 1, "p": {"resource": "chat"}}))) == ["gpt-3.5-turbo"]

def test_assistants_api(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "openAi", "tv": 1.7, "p": {"resource": "assistant"}}))
    assert models(r) == ["Assistants API"] and r["hits"][0]["status"] == "already_shut_down"

# --- HTTP Request & Code ----------------------------------------------------------
def test_http_jsonbody(tmp_path):
    body = '={ "model": "gpt-4o-mini", "messages": [] }'
    r = scan_obj(tmp_path, wf({"type": "n8n-nodes-base.httpRequest", "tv": 4.2, "p": {"url": "https://api.openai.com/v1/chat/completions", "jsonBody": body}}), rules=RULES_ALL)
    assert models(r) == ["gpt-4o-mini"] and r["hits"][0]["source"] == "http-request"

def test_http_body_params(tmp_path):
    r = scan_obj(tmp_path, wf({"type": "n8n-nodes-base.httpRequest", "tv": 3, "p": {"url": "https://api.anthropic.com/v1/messages",
        "bodyParameters": {"parameters": [{"name": "model", "value": "claude-3-7-sonnet-20250219"}]}}}))
    assert models(r) == ["claude-3-7-sonnet-20250219"]

def test_http_translations_endpoint(tmp_path):
    r = scan_obj(tmp_path, wf({"type": "n8n-nodes-base.httpRequest", "tv": 4.2, "p": {"url": "https://api.openai.com/v1/audio/translations"}}))
    assert any(h["model"] == "/v1/audio/translations" for h in r["hits"])

def test_http_other_host_prose_ignored(tmp_path):
    r = scan_obj(tmp_path, wf({"type": "n8n-nodes-base.httpRequest", "tv": 4.2, "p": {"url": "https://example.com", "jsonBody": "compare with gpt-4o please"}}))
    assert r["hits"] == []

def test_code_node(tmp_path):
    code = "const cfg = { model: 'claude-3-5-haiku-20241022' };\nreturn [{json: cfg}];"
    r = scan_obj(tmp_path, wf({"type": "n8n-nodes-base.code", "tv": 2, "p": {"jsCode": code}}))
    assert models(r) == ["claude-3-5-haiku-20241022"] and r["hits"][0]["source"] == "code-string"

# --- sticky notes & prompts -> info only ------------------------------------------
def test_sticky_note_info_only(tmp_path):
    r = scan_obj(tmp_path, wf({"type": "n8n-nodes-base.stickyNote", "p": {"content": "This uses gpt-4o-mini"}}))
    assert r["hits"] == [] and r["info"]

def test_prompt_mention_info_only(tmp_path):
    r = scan_obj(tmp_path, wf({"type": LC + "agent", "tv": 1.8, "p": {"options": {"systemMessage": "You are smarter than gpt-4o and claude-2."}}}))
    assert r["hits"] == []

# --- Make blueprint & text ------------------------------------------------------------
def test_make_blueprint(tmp_path):
    bp = {"name": "x", "flow": [{"id": 1, "module": "openai-gpt-3:CreateCompletion", "version": 1,
           "mapper": {"model": "gpt-4o-2024-11-20", "messages": [{"content": "mention gpt-4 in text"}]}},
          {"id": 2, "module": "builtin:BasicRouter", "routes": [{"flow": [{"id": 3, "module": "anthropic-claude:createMessage",
           "mapper": {"model": "claude-sonnet-4-5"}}]}]}]}
    r = scan_obj(tmp_path, bp, "bp.json", rules=RULES_ALL)
    assert models(r) == ["claude-sonnet-4-5", "gpt-4o-2024-11-20"]
    r = scan_obj(tmp_path, bp, "bp.json")  # default: the undated alias is not reported
    assert models(r) == ["gpt-4o-2024-11-20"] and [h["model"] for h in r["unverified"]] == ["claude-sonnet-4-5"]

def test_text_repo_file(tmp_path):
    txt = 'client.chat.completions.create(model="gpt-4o", max_tokens=10)\n# gpt-4o-realtime-preview\n'
    r = scan_obj(tmp_path, txt, "app.py", rules=RULES_ALL)
    assert sorted(set(models(r))) == ["gpt-4o", "gpt-4o-realtime-preview"]
    r = scan_obj(tmp_path, txt, "app.py")
    assert models(r) == ["gpt-4o-realtime-preview"]

def test_cli_exit_code(tmp_path):
    f = tmp_path / "a.txt"; f.write_text("model: gpt-6-luna\n")
    assert S.main([str(f), "--today", TODAY]) == 0
    f.write_text("model: gpt-4o-2024-08-06\n")
    assert S.main([str(f), "--today", TODAY]) == 1

# --- verified-only default ------------------------------------------------------------
def test_default_rules_verified_only():
    assert S.Rules().include_unverified is False

def test_unverified_alias_not_reported_by_default(tmp_path):
    w = wf({"type": LC + "lmChatOpenAi", "tv": 1.2, "p": {"model": {"__rl": True, "value": "gpt-4o-mini"}}})
    r = scan_obj(tmp_path, w)
    assert r["hits"] == [] and [h["model"] for h in r["unverified"]] == ["gpt-4o-mini"]
    assert r["include_unverified"] is False
    r = scan_obj(tmp_path, w, rules=RULES_ALL)
    assert models(r) == ["gpt-4o-mini"] and r["hits"][0]["rule_status"] == "unverified" and r["unverified"] == []

def test_scan_override_include_unverified(tmp_path):
    f = tmp_path / "a.txt"; f.write_text('model="claude-sonnet-4-5"\n')
    assert S.scan([str(f)], today=TODAY, rules=RULES)["hits"] == []
    assert models(S.scan([str(f)], today=TODAY, rules=RULES, include_unverified=True)) == ["claude-sonnet-4-5"]

def test_verified_hit_carries_verified_on(tmp_path):
    r = scan_obj(tmp_path, 'model = "claude-sonnet-4-5-20250929"\n', "x.py")
    h = r["hits"][0]
    assert h["rule_status"] == "verified" and h["verified_on"] == "2026-10-31" and h["rule_source"].startswith("https://")

def test_date_suffix_family_match_is_unverified(tmp_path):
    # dated ID not listed itself, matched through an alias entry -> inference, never verified
    r = scan_obj(tmp_path, 'model = "claude-3-5-sonnet-latest-2025-01-01"\n', "x.py", rules=RULES_ALL)
    assert all(h["rule_status"] == "unverified" for h in r["hits"])

def test_cli_include_unverified_flag(tmp_path, capsys):
    f = tmp_path / "a.txt"; f.write_text("model: gpt-4o\n")
    assert S.main([str(f), "--today", TODAY]) == 0
    out = capsys.readouterr().out
    assert "Not reported: 1 match" in out and "--include-unverified" in out
    assert S.main([str(f), "--today", TODAY, "--include-unverified"]) == 1
    assert "UNVERIFIED rule" in capsys.readouterr().out

def test_rules_file_has_sources_and_dates():
    import yaml
    d = yaml.safe_load(open(S.MODELS_YAML, encoding="utf-8"))
    for e in d["entries"]:
        assert e["status"] in ("verified", "unverified")
        assert e["source_url"].startswith("https://")
        assert len(e["shutdown_date"]) == 10
        if e["status"] == "verified":
            assert e["verified_on"] == d["meta"]["verified_on"]
        else:
            assert e["verified_on"] is None

# --- bundled examples ----------------------------------------------------------------------
EX = os.path.join(os.path.dirname(__file__), "..", "examples")

def test_example_n8n_workflow():
    r = S.scan([os.path.join(EX, "n8n_workflow.json")], today=TODAY, rules=RULES)
    got = sorted((h["node_name"], h["model"]) for h in r["hits"])
    assert got == [("Image: Generate", "dall-e-3"), ("OpenAI Chat Model (default)", "gpt-5-mini"),
                   ("OpenAI Chat Model (pinned)", "gpt-4o-2024-08-06"), ("Transcribe audio", "whisper-1"),
                   ("Writer (Claude)", "claude-sonnet-4-5-20250929")]
    assert [h["model"] for h in r["unverified"]] == ["gpt-4o-mini"]
    assert any(i["node_name"] == "Note" for i in r["info"])

def test_example_make_blueprint():
    r = S.scan([os.path.join(EX, "make_blueprint.json")], today=TODAY, rules=RULES)
    assert models(r) == ["gpt-4-turbo"]

def test_example_text():
    r = S.scan([os.path.join(EX, "app.py")], today=TODAY, rules=RULES)
    assert models(r) == ["claude-3-5-haiku-20241022", "whisper-1"]

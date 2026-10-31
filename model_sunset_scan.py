#!/usr/bin/env python3
"""model-sunset-scanner: find retiring / retired OpenAI and Anthropic models in n8n workflow exports,
Make blueprints, or any code / text. Rules come only from models.yaml (official deprecation pages).

By default only rules with status "verified" are reported. Matches against "unverified" rules
(e.g. undated aliases such as gpt-4o) are listed separately and only reported with --include-unverified.

usage: python3 model_sunset_scan.py PATH [PATH...] [--json out.json] [--md out.md]
                                     [--today YYYY-MM-DD] [--include-unverified] [--rules models.yaml]
exit code: 1 if anything is reported, 0 otherwise.
"""
import argparse, datetime, json, os, re, sys
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n8n_defaults import DEFAULTS, GH
GH_ASSIST = GH + "packages/@n8n/nodes-langchain/nodes/vendors/OpenAi/v1/actions/assistant/create.operation.ts#L277"

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_YAML = os.path.join(HERE, "models.yaml")
DATE_SFX = re.compile(r"^(?P<base>.+?)-(?P<date>\d{4}-\d{2}-\d{2})$")
# a model-ish token; boundaries exclude [\w.-] so 'gpt-4o' never matches inside 'gpt-4o-realtime' or 'gpt-4.1-nano'
TOKEN = re.compile(r"(?<![\w.\-/:])(?:ft:)?(?:openai/|anthropic/|models/)?"
                   r"((?:gpt|chatgpt|claude|dall-e|tts|whisper|text-moderation|text-davinci|text-curie|text-babbage|text-ada|"
                   r"computer-use|codex|code-davinci|sora|davinci|babbage)-[A-Za-z0-9.\-]*[A-Za-z0-9]"
                   r"|o[134](?:-(?:mini|pro|preview|deep-research)(?:-deep-research)?)?(?:-\d{4}-\d{2}-\d{2})?)(?![\w\-])")
O_SERIES = re.compile(r"^o[134]")
API_HOSTS = ("api.openai.com", "api.anthropic.com")

class Rules:
    def __init__(self, path=MODELS_YAML, include_unverified=False):
        self.include_unverified = include_unverified
        with open(path, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        self.idx = {}
        for e in d["entries"]:
            for m in e["models"]:
                self.idx.setdefault(m.lower(), e)

    def lookup(self, raw):
        """return (entry, matched_id, how) or None. how: exact|date-suffix-family|fine-tune|route"""
        s = raw.strip().strip("'\"").lower()
        how = "exact"; route = None
        if s.startswith("ft:"):
            s = s[3:].split(":")[0]; how = "fine-tune"
        for p in ("openai/", "anthropic/", "models/"):
            if s.startswith(p):
                route = p[:-1]; s = s[len(p):]
        if s in self.idx:
            return self.idx[s], s, how, route
        m = DATE_SFX.match(s)
        if m and m.group("base") in self.idx and self.idx[m.group("base")]["kind"] in ("family", "alias-inferred"):
            return self.idx[m.group("base")], s, "date-suffix->family (inferred)", route
        return None

def status_of(date, today):
    if not date: return "unknown"
    return "already_shut_down" if date <= today else "scheduled"

def mk_hit(rules, raw, ctx, today, source, extra=None):
    r = rules.lookup(raw)
    if not r: return None
    e, mid, how, route = r
    mid = next((m for m in e["models"] if m.lower() == mid), mid)
    h = {**ctx, "model": mid, "raw": raw, "match": how, "source": source,
         "shutdown_date": e["shutdown_date"], "status": status_of(e["shutdown_date"], today),
         "replacement": e["replacement"], "provider": e["provider"],
         # a dated ID matched only via its family/alias entry is an inference -> never counts as verified
         "rule_status": "unverified" if how.startswith("date-suffix") else e["status"],
         "verified_on": e.get("verified_on"),
         "params_to_change": [p["param"] + ": " + p["change"] for p in e["params_to_change"]],
         "rule_source": e["source_url"]}
    if route in ("openai", "anthropic"):
        h["note"] = "Called through a third-party router (e.g. OpenRouter); that platform's own retirement date applies and is not verified"
    if e.get("note"): h["rule_note"] = e["note"]
    if extra: h.update(extra)
    return h

def tokens_in_text(s):
    out = []
    for m in TOKEN.finditer(s):
        tok = m.group(0)
        if O_SERIES.match(m.group(1)):
            # o-series only when quoted or a full value, to avoid matching random 'o3' words
            st, en = m.start(), m.end()
            if not (s.strip() == tok or (st > 0 and en < len(s) and s[st-1] in "'\"`" and s[en] in "'\"`")):
                continue
        out.append(tok)
    return out

def expr_literals(v):
    """n8n expression '={{ ... }}' or '=literal'. Return (text_to_scan, is_dynamic)."""
    if isinstance(v, str) and v.startswith("="):
        body = v[1:]
        dyn = "{{" in body and re.search(r"\$\w|\bitem\b|\$\(", body) is not None
        return body, dyn
    return v, False

def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj

def rl_value(v):
    if isinstance(v, dict) and (v.get("__rl") or "value" in v):
        return v.get("value"), True
    return v, False

def scan_n8n(wf, rules, today, fname):
    hits, info = [], []
    for ni, node in enumerate(wf.get("nodes", [])):
        ntype = node.get("type", ""); tv = node.get("typeVersion"); name = node.get("name")
        params = node.get("parameters", {}) or {}
        ctx = {"file": fname, "node_name": name, "node_type": ntype, "type_version": tv}
        if ntype == "n8n-nodes-base.stickyNote":
            for t in tokens_in_text(str(params.get("content", ""))):
                if rules.lookup(t): info.append({**ctx, "path": f"nodes[{ni}].parameters.content", "model": t, "why": "only mentioned in a sticky note; does not affect execution"})
            continue
        seen_paths = set()
        # 1) explicit model params / resource locators
        explicit = False
        for key in ("model", "modelId", "modelName"):
            if key in params:
                val, is_rl = rl_value(params[key])
                txt, dyn = expr_literals(val)
                p = f"nodes[{ni}].parameters.{key}" + (".value" if is_rl else "")
                seen_paths.add(f"{key}.value" if is_rl else key)
                if val in (None, ""):
                    continue
                explicit = True
                if dyn and not tokens_in_text(str(txt)):
                    info.append({**ctx, "path": p, "value": val, "why": "model is chosen by a dynamic expression and cannot be resolved statically"}); continue
                toks = [str(txt).strip()] if rules.lookup(str(txt).strip()) else tokens_in_text(str(txt))
                for t in toks:
                    h = mk_hit(rules, t, {**ctx, "path": p}, today, "explicit" + ("-expression" if str(val).startswith("=") else "") + ("-resourceLocator" if is_rl else ""))
                    if h: hits.append(h)
        # 2) default-model inference when omitted
        if ntype in DEFAULTS and not explicit:
            fn, _ = DEFAULTS[ntype]
            d = fn(tv, params)
            if d:
                extra = {"evidence": d["evidence"]}
                for k in ("note", "prs", "alt_models_older_n8n", "hardcoded", "endpoint"):
                    if d.get(k): extra["default_" + k] = d[k]
                h = mk_hit(rules, d["model"], {**ctx, "path": f"nodes[{ni}].parameters.model (omitted -> n8n default)"}, today,
                           "hardcoded" if d.get("hardcoded") else "default", extra)
                if h: hits.append(h)
                if d.get("endpoint"):
                    h2 = mk_hit(rules, d["endpoint"], {**ctx, "path": f"nodes[{ni}] (operation=translate)"}, today, "hardcoded-endpoint")
                    if h2: hits.append(h2)
        # vendor openAi audio translate/transcribe ignore explicit (hardcoded)
        if ntype == "@n8n/n8n-nodes-langchain.openAi" and params.get("resource") == "audio" and params.get("operation") in ("transcribe", "translate") and explicit:
            pass
        # 2b) Assistants API (shut down 2026-08-26): OpenAI vendor node v1 resource=assistant, and the old OpenAI Assistant node
        if (ntype == "@n8n/n8n-nodes-langchain.openAi" and params.get("resource") == "assistant" and (tv or 1) < 2) \
                or ntype == "@n8n/n8n-nodes-langchain.openAiAssistant":
            h = mk_hit(rules, "Assistants API", {**ctx, "path": f"nodes[{ni}].parameters.resource"}, today, "node-uses-endpoint",
                       {"evidence": [GH_ASSIST]})
            if h: hits.append(h)
        # 3) Anthropic sampling params
        if ntype.endswith("lmChatAnthropic"):
            opts = params.get("options", {}) or {}
            bad = [k for k in ("temperature", "topK", "topP") if k in opts]
            for h in hits:
                if h["node_name"] == name and bad:
                    h["node_param_findings"] = f"options explicitly set {bad}; newer Claude models (4.7+ / Sonnet 5+) reject these, remove them when migrating"
        if ntype.endswith("lmChatOpenAi"):
            opts = params.get("options", {}) or {}
            bad = [k for k in ("temperature", "topP", "maxTokens") if k in opts]
            for h in hits:
                if h["node_name"] == name and bad and h.get("replacement", "").startswith("gpt-6"):
                    h["node_param_findings"] = f"options explicitly set {bad}; on gpt-6-luna remove temperature/top_p when reasoning effort is not none, and use max_completion_tokens instead of max_tokens"
        # 4) HTTP Request to OpenAI/Anthropic, Code nodes, and any other string param
        is_http = ntype == "n8n-nodes-base.httpRequest"
        url = str(params.get("url", ""))
        http_ai = is_http and any(hh in url for hh in API_HOSTS)
        for p, v in walk(params):
            if p in seen_paths or p.split(".")[0] in ("model", "modelId", "modelName") or not isinstance(v, str):
                continue
            txt, dyn = expr_literals(v)
            src = "code-string" if ntype in ("n8n-nodes-base.code", "n8n-nodes-base.function", "n8n-nodes-base.functionItem") \
                else ("http-request" if is_http else "string-param")
            if is_http and re.search(r"/v1/(threads|assistants)\b", txt) and "api.openai.com" in url + txt and "Assistants API" not in [h["model"] for h in hits if h["node_name"] == name]:
                h = mk_hit(rules, "Assistants API", {**ctx, "path": f"nodes[{ni}].parameters.{p}"}, today, "http-request-endpoint")
                if h: hits.append(h)
            if is_http and "/v1/audio/translations" in txt and "api.openai.com" in url + txt:
                h = mk_hit(rules, "/v1/audio/translations", {**ctx, "path": f"nodes[{ni}].parameters.{p}"}, today, "http-request-endpoint")
                if h: hits.append(h)
            for t in tokens_in_text(txt):
                if src == "string-param" and not looks_like_model_value(txt, t):
                    if rules.lookup(t): info.append({**ctx, "path": f"nodes[{ni}].parameters.{p}", "model": t, "why": "mentioned in prompt/text, not used as a model parameter"})
                    continue
                if is_http and not http_ai and not re.search(r'"?model"?\s*[:=]', txt):
                    continue
                h = mk_hit(rules, t, {**ctx, "path": f"nodes[{ni}].parameters.{p}"}, today, src)
                if h: hits.append(h)
    return hits, info

def looks_like_model_value(txt, tok):
    s = txt.strip().strip("'\"")
    if s.lower() == tok.lower() or s.lower().endswith("/" + tok.lower()): return True
    # a complete quoted id inside a non-prose value, e.g. ["openai/gpt-4.1", "mistralai/x"]
    if re.search(r'["\'`]' + re.escape(tok) + r'["\'`]', txt) and len(re.findall(r"[A-Za-z]{3,}\s+[A-Za-z]{3,}", txt)) < 3: return True
    return re.search(r'["\']?model["\']?\s*[:=]\s*["\']?' + re.escape(tok), txt) is not None

def scan_make(bp, rules, today, fname):
    hits, info = [], []
    def rec(flow, base):
        for i, mod in enumerate(flow or []):
            name = (mod.get("metadata", {}) or {}).get("designer", {}).get("name") or mod.get("module")
            ctx = {"file": fname, "node_name": name or f"module {mod.get('id')}", "node_type": mod.get("module"), "type_version": mod.get("version")}
            for sect in ("mapper", "parameters"):
                for p, v in walk(mod.get(sect, {}) or {}):
                    if not isinstance(v, str): continue
                    leaf = p.split(".")[-1].split("[")[0]
                    for t in tokens_in_text(v):
                        explicit = leaf in ("model", "model_id", "modelId", "engine") or looks_like_model_value(v, t)
                        if not explicit:
                            if rules.lookup(t): info.append({**ctx, "path": f"{base}[{i}].{sect}.{p}", "model": t, "why": "mentioned in text, not a model field"})
                            continue
                        h = mk_hit(rules, t, {**ctx, "path": f"{base}[{i}].{sect}.{p}"}, today, "make-" + leaf)
                        if h: hits.append(h)
            for r_i, route in enumerate(mod.get("routes", []) or []):
                rec(route.get("flow"), f"{base}[{i}].routes[{r_i}].flow")
    rec(bp.get("flow"), "flow")
    return hits, info

def scan_text(text, rules, today, fname):
    hits, info = [], []
    for ln, line in enumerate(text.splitlines(), 1):
        for t in tokens_in_text(line):
            ctx = {"file": fname, "node_name": None, "node_type": "text", "type_version": None, "path": f"line {ln}"}
            h = mk_hit(rules, t, ctx, today, "text")
            if h: h["line_text"] = line.strip()[:200]; hits.append(h)
    return hits, info

def detect_and_scan(path, rules, today):
    raw = open(path, encoding="utf-8", errors="replace").read()
    if path.endswith(".json"):
        try:
            d = json.loads(raw)
        except Exception:
            return ("text",) + scan_text(raw, rules, today, path)
        if isinstance(d, dict) and isinstance(d.get("nodes"), list):
            return ("n8n",) + scan_n8n(d, rules, today, path)
        if isinstance(d, dict) and isinstance(d.get("workflow"), dict) and isinstance(d["workflow"].get("nodes"), list):
            return ("n8n",) + scan_n8n(d["workflow"], rules, today, path)
        if isinstance(d, dict) and isinstance(d.get("flow"), list):
            return ("make",) + scan_make(d, rules, today, path)
        if isinstance(d, dict) and isinstance(d.get("blueprint"), dict):
            return ("make",) + scan_make(d["blueprint"], rules, today, path)
    return ("text",) + scan_text(raw, rules, today, path)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
TEXT_EXT = {".json", ".js", ".ts", ".py", ".yaml", ".yml", ".env", ".toml", ".md", ".txt", ".mjs", ".cjs", ".tsx", ".jsx", ".go", ".rb", ".java", ".cs", ".php", ".ini", ".cfg"}

def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in sorted(files):
                    if os.path.splitext(f)[1].lower() in TEXT_EXT or f.startswith(".env"):
                        yield os.path.join(root, f)
        else:
            yield p

def scan(paths, today=None, rules=None, include_unverified=None):
    """Scan files/dirs. Hits from unverified rules go to res["unverified"] unless include_unverified is True
    (defaults to rules.include_unverified)."""
    today = today or datetime.date.today().isoformat()
    rules = rules or Rules()
    inc = rules.include_unverified if include_unverified is None else include_unverified
    res = {"scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "today": today,
           "include_unverified": inc, "files": [], "hits": [], "unverified": [], "info": []}
    for f in iter_files(paths):
        kind, hits, info = detect_and_scan(f, rules, today)
        rep = [h for h in hits if inc or h["rule_status"] == "verified"]
        res["files"].append({"file": f, "kind": kind, "hits": len(rep)})
        res["hits"] += rep; res["info"] += info
        if not inc:
            res["unverified"] += [h for h in hits if h["rule_status"] != "verified"]
    return res

def to_md(res):
    hits = res["hits"]
    L = ["# Model sunset scan report", "",
         f"- Scanned (UTC): {res['scanned_at']}  Reference date: {res['today']}",
         f"- Files: {len(res['files'])}  Findings: {len(hits)}  "
         f"(already shut down {sum(h['status'] == 'already_shut_down' for h in hits)} / scheduled {sum(h['status'] == 'scheduled' for h in hits)})",
         "- Rules: " + ("verified + unverified (--include-unverified)" if res.get("include_unverified") else "verified only"), ""]
    if hits:
        L += ["| File | Node | Type | Path | Model | Source | Shutdown | Status | Replacement | Params to change |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for h in sorted(hits, key=lambda x: (x["shutdown_date"] or "9", x["file"])):
            pc = "<br>".join(h["params_to_change"]) + (("<br>**Node**: " + h["node_param_findings"]) if h.get("node_param_findings") else "")
            src = h["source"] + (f" ({h['match']})" if h["match"] != "exact" else "") + (" [UNVERIFIED rule]" if h["rule_status"] != "verified" else "")
            L.append(f"| {os.path.basename(h['file'])} | {h['node_name'] or ''} | {h['node_type']} v{h['type_version'] or ''} | `{h['path']}` | `{h['model']}` | {src} | {h['shutdown_date']} | {h['status']} | {h['replacement']} | {pc} |")
        ev = [h for h in hits if h.get("evidence")]
        if ev:
            L += ["", "## Evidence for inferred n8n defaults (n8n source)", ""]
            for h in ev:
                L.append(f"- {h['node_name']} ({h['node_type']} v{h['type_version']}): {', '.join(h['evidence'])}" + (f" - {h['default_note']}" if h.get("default_note") else ""))
    if res.get("unverified"):
        L += ["", f"## Not reported: {len(res['unverified'])} match(es) against UNVERIFIED rules", "",
              "These rules are alias/family inferences that are not confirmed on an official page. Re-run with --include-unverified to report them.", ""]
        for h in res["unverified"][:200]:
            L.append(f"- {os.path.basename(h['file'])} / {h.get('node_name') or ''} `{h['path']}`: `{h['model']}` (inferred shutdown {h['shutdown_date']})")
    if res["info"]:
        L += ["", "## Info only (not counted)", ""]
        for i in res["info"][:200]:
            L.append(f"- {os.path.basename(i['file'])} / {i.get('node_name')} `{i['path']}`: {i.get('model') or i.get('value')} - {i['why']}")
    return "\n".join(L) + "\n"

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+"); ap.add_argument("--json"); ap.add_argument("--md")
    ap.add_argument("--today", help="reference date YYYY-MM-DD (default: today)"); ap.add_argument("--rules", default=MODELS_YAML)
    ap.add_argument("--include-unverified", action="store_true",
                    help="also report matches against unverified (alias/family-inferred) rules")
    a = ap.parse_args(argv)
    res = scan(a.paths, a.today, Rules(a.rules, include_unverified=a.include_unverified))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh: json.dump(res, fh, ensure_ascii=False, indent=2)
    md = to_md(res)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh: fh.write(md)
    if not a.json and not a.md: print(md)
    else: print(f"files={len(res['files'])} hits={len(res['hits'])} unverified_not_reported={len(res['unverified'])} info={len(res['info'])}")
    return 1 if res["hits"] else 0

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# yard_bench.py —— ci-yard 公域免费分钟面 LLM 联测负载（自 ci-control/.github/scripts/llm_bench.py sha fb4f55ff 移植扩样）
# 矩阵：6 场景 × 6 模型 × 温度 2 档（0.2/0.7；kimi k3/k2.7-code 按原律锁 1.0）
# DeepSeek 谷段闸：谷价窗（北京 00:30-08:30 = UTC 16:30-00:30）内跑 pro 重型题，窗外只跑 flash 轻题
# 缺密 provider 不跑、记「缺密跳过」行；产出 bench/results-YYYYMMDD.jsonl + bench/latest.md
# 每班一行摘要回写 ci-control bridge/llm-usage.jsonl（GH_TOKEN=CI_OPS App token，跨仓直推）
import os, json, time, base64, datetime, requests

GH = "https://api.github.com"
_T = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")   # 暖侧 ci-warm 面用仓内 GITHUB_TOKEN
H = {"Authorization": f"Bearer {_T}", "Accept": "application/vnd.github+json"}
BENCH_REPO = os.environ.get("BENCH_REPO") or "chepin-ai/ci-yard"    # 产出落仓（暖侧=chepin-bi/ci-warm）
YARD_PUSH = os.environ.get("YARD_PUSH", "1") != "0"                  # 0=只写本地 bench/，由 workflow git push 回仓
YARD_LEDGER = os.environ.get("YARD_LEDGER", "1") != "0"              # 0=不回写 ci-control 用量台账（暖侧无权面）
keys = json.loads(os.environ.get("SHARED_KEYS") or "{}")
now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime("%FT%TZ")
today = now.strftime("%Y-%m-%d")
REPS = int(os.environ.get("YARD_REPS") or "2")          # 每格重复次数（默认 2，公域分钟可上调）
TEMPS = [0.2, 0.7]                                       # 配置维度：温度两档
KIMI_LOCK1 = {"kimi-k3", "kimi-k2.7-code"}               # 原律：这两型只认 temperature=1

# ── DeepSeek 谷段闸 ──
m_utc = now.hour * 60 + now.minute
VALLEY = (m_utc >= 16 * 60 + 30) or (m_utc < 30)         # UTC 16:30-00:30 = 北京 00:30-08:30

# ── 实档取样（拿不到用兜底文案，保证确定性判分仍可跑）──
def gf(repo, path):
    try:
        r = requests.get(f"{GH}/repos/{repo}/contents/{path}", headers=H, timeout=15)
        if r.status_code != 200:
            return None, None
        j = r.json()
        return base64.b64decode(j["content"]).decode("utf-8", "replace"), j["sha"]
    except Exception:
        return None, None

duty_txt, _ = gf("chepin-ai/vci-usrm", "weave/duty/duty.log")
duty_tail = duty_txt.strip().split("\n")[-3:] if duty_txt else ["（无档）"]
audit_txt, _ = gf("chepin-ai/ci-control", "bridge/audit-trail.json")
f0 = "（无 findings）"
if audit_txt:
    try:
        fj = json.loads(audit_txt)
        if fj.get("findings"):
            f0 = json.dumps(fj["findings"][0], ensure_ascii=False)[:200]
    except Exception:
        pass

LONG_DOC = (
    "联邦调度台本班记录：runner 分钟为真瓶颈，私仓额度耗尽后联测迁往公仓免费分钟面。"
    "谷价窗内 DeepSeek pro 跑重型题，窗外只跑 flash 轻题；分类法闸要求所有 md 带 CLASSIFY 头。"
    "跨仓写一律走 CI_OPS App token 直推，密钥值永不落日志。"
) * 6

DIFF_SNIP = (
    "--- a/bridge/route.py\n+++ b/bridge/route.py\n"
    "@@ def pick(providers):\n"
    "-    return providers[0]\n"
    "+    alive = [p for p in providers if p.get('ok')]\n"
    "+    return alive[0] if alive else None\n"
)

CLAUSE_A = "第十七条：联测任务应在谷价窗口内调度重型模型，窗口外仅允许轻量模型。"
CLAUSE_B = "实施细则第九条：重型模型联测不受时段限制，任何班次均可调度。"

# ── 场景电池：6 类（3 类值守系 + 3 类新增），weight 标轻/重 ──
TASKS = [
 {"id": "duty-summary", "kind": "值守摘要", "weight": "light",
  "sys": "你是联邦值守摘要员。用不超过 50 字中文概括。",
  "prompt": "概括这三行值守日志：\n" + "\n".join(duty_tail),
  "check": lambda t: 5 < len(t) <= 120},
 {"id": "attribution", "kind": "归因初判", "weight": "light",
  "sys": "你是故障归因员。给一句归因+一句建议动作，不超过 80 字。",
  "prompt": "对这条 finding 给归因初判：" + f0,
  "check": lambda t: len(t) > 10},
 {"id": "lobby-draft", "kind": "公文起草", "weight": "light",
  "sys": "你是大厅文书。起草一条 dtag 开头的大厅帖，不超过 80 字。",
  "prompt": "为本班审计结果起草大厅帖（findings 见上）。",
  "check": lambda t: ("dtag" in t) or len(t) <= 150},
 {"id": "code-diff-review", "kind": "代码修复差评审", "weight": "heavy",
  "sys": "你是代码评审员。只输出 JSON（键 verdict，值 approve/block；键 reason，一句话）。",
  "prompt": "评审这个修复 diff，若引入空列表外的新风险给 block：\n" + DIFF_SNIP,
  "check": lambda t: json.loads(t)["verdict"] in ("approve", "block")},
 {"id": "legis-consistency", "kind": "立法条文一致性比对", "weight": "heavy",
  "sys": "你是条文一致性比对员。只输出 JSON（键 consistent，布尔值；键 note，一句话）。",
  "prompt": f"比对两条文是否一致：\nA：{CLAUSE_A}\nB：{CLAUSE_B}",
  "check": lambda t: json.loads(t)["consistent"] is False},
 {"id": "long-doc-summary", "kind": "长文档摘要", "weight": "heavy",
  "sys": "你是长文档摘要员。用不超过 80 字中文概括，保留关键实体。",
  "prompt": "概括以下文档：\n" + LONG_DOC,
  "check": lambda t: len(t) <= 200 and ("谷价" in t or "runner" in t)},
]

# ── 模型面：6 型（按 provider 缺密整组跳过）──
PROVIDER_DEFS = [
 ("kimi", "https://api.moonshot.cn/v1", "API_KIMI_KEY_1",
  ["kimi-k3", "kimi-k2.7-code", "moonshot-v1-8k"]),
 ("deepseek", "https://api.deepseek.com/v1", "API_DEEPSEEK_KEY_1",
  ["deepseek-v4-flash", "deepseek-v4-pro"]),
 ("longcat", "https://api.longcat.chat/openai", "API_LONGCAT_KEY_1",
  ["LongCat-2.0"]),
]

# 成本估算单价（USD/tok，沿用 llm-bench 旧律 deepseek=2.7e-7；pro 按输出价粗估；余置 0 仅计 tok）
RATE = {"deepseek-v4-flash": 2.7e-7, "deepseek-v4-pro": 1.1e-6}

def eff_temp(model, tier):
    return 1.0 if model in KIMI_LOCK1 else tier

def chat(base, key, model, sys_, prompt, temp):
    body = {"model": model,
            "messages": [{"role": "system", "content": sys_}, {"role": "user", "content": prompt}],
            "temperature": temp, "max_tokens": 400}
    t0 = time.time()
    r = requests.post(base.rstrip("/") + "/chat/completions", json=body,
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      timeout=90)
    dt = time.time() - t0
    if r.status_code != 200:
        return None, dt, f"HTTP {r.status_code} {r.text[:80]}"
    j = r.json()
    _msg = j["choices"][0]["message"]
    out = _msg.get("content") or ("[tool_calls] " + json.dumps(_msg.get("tool_calls"), ensure_ascii=False)[:600]
                                  if _msg.get("tool_calls") else "")
    return out, dt, j.get("usage", {})

def clean(t):
    return t.strip().strip("`").replace("```json", "").replace("```", "").strip()

results = []
for pname, base, keyname, models in PROVIDER_DEFS:
    key = keys.get(keyname)
    if not key:
        results.append({"p": pname, "skipped": f"缺密跳过：{keyname} 未种入 ci-yard"})
        continue
    for mdl in models:
        seen_temps = set()
        for tier in TEMPS:
            tp = eff_temp(mdl, tier)
            if tp in seen_temps:
                continue                                  # kimi 锁 1.0：两档塌缩为一档
            seen_temps.add(tp)
            for task in TASKS:
                # 谷段闸（仅 deepseek）
                if pname == "deepseek":
                    if mdl.endswith("-pro") and not VALLEY:
                        results.append({"p": pname, "m": mdl, "t": task["id"], "temp": tp,
                                        "skipped": "谷段闸：窗外 pro 停跑"})
                        continue
                    if task["weight"] == "heavy" and not VALLEY:
                        results.append({"p": pname, "m": mdl, "t": task["id"], "temp": tp,
                                        "skipped": "谷段闸：窗外只跑轻题"})
                        continue
                    if mdl.endswith("-pro") and task["weight"] != "heavy":
                        continue                          # pro 只跑重型题，不浪费
                reps = []
                for _ in range(REPS):
                    try:
                        out, dt, usage = chat(base, key, mdl, task["sys"], task["prompt"], tp)
                        if out is None:
                            reps.append({"ok": False, "err": str(usage)[:80], "s": -1})
                            continue
                        ok = False
                        try:
                            ok = bool(task["check"](clean(out)))
                        except Exception:
                            ok = False
                        reps.append({"ok": ok, "s": round(dt, 1),
                                     "tok": usage.get("total_tokens") if isinstance(usage, dict) else None})
                        time.sleep(0.3)
                    except Exception as e:
                        reps.append({"ok": False, "err": str(e)[:80], "s": -1})
                oks = sum(1 for r in reps if r["ok"])
                good = [r["s"] for r in reps if r["s"] > 0]
                tok = sum(r.get("tok") or 0 for r in reps)
                results.append({"p": pname, "m": mdl, "t": task["id"], "kind": task["kind"],
                                "temp": tp, "pass": f"{oks}/{REPS}", "ok": oks * 2 > REPS,
                                "s": round(sum(good) / max(1, len(good)), 1), "tok": tok,
                                "cost_usd": round(tok * RATE.get(mdl, 0.0), 8), "reps": reps})

# ── 落盘：本地 bench/ + 推仓 ──
os.makedirs("bench", exist_ok=True)
jl_path = f"bench/results-{now:%Y%m%d}.jsonl"
lines_j = [json.dumps({"ts": ts, "valley": VALLEY, **r}, ensure_ascii=False) for r in results]
open(jl_path, "a", encoding="utf-8").write("\n".join(lines_j) + "\n")

run_rows = [r for r in results if "pass" in r]
skip_rows = [r for r in results if "skipped" in r]
tot_tok = sum(r.get("tok") or 0 for r in run_rows)
tot_cost = round(sum(r.get("cost_usd") or 0.0 for r in run_rows), 6)

doc = [f"CLASSIFY: L1",
       f"# yard LLM 联测（{ts}，谷段闸={'窗内' if VALLEY else '窗外'}）", "",
       "| provider | model | 场景 | 温度 | 命中 | 均秒 | tok | 成本$ |",
       "|---|---|---|---|---|---|---|---|"]
for r in run_rows:
    doc.append(f"| {r['p']} | {r['m']} | {r['t']} | {r['temp']} | {r['pass']} | {r['s']} | {r['tok']} | {r['cost_usd']} |")
doc += ["", "## 跳过行（缺密/谷段闸）"]
for r in skip_rows:
    doc.append(f"- {r['p']}" + (f"/{r.get('m','')}" if r.get("m") else "") +
               (f" {r.get('t','')}" if r.get("t") else "") + f"：{r['skipped']}")
agg = {}
for r in run_rows:
    a = agg.setdefault(f"{r['p']}/{r['m']}@{r['temp']}", [0, 0])
    a[1] += 1
    a[0] += 1 if r["ok"] else 0
doc += ["", "## 模型×温度命中率"]
for k, (p_, n_) in sorted(agg.items()):
    doc.append(f"- {k}: {p_}/{n_}")
doc += ["", f"合计 tok={tot_tok} 估算成本$={tot_cost}"]
md = "\n".join(doc)
open("bench/latest.md", "w", encoding="utf-8").write(md + "\n")

def pf(repo, path, raw, msg):
    b = {"message": msg, "content": base64.b64encode(raw.encode()).decode()}
    _, sha = gf(repo, path)
    if sha:
        b["sha"] = sha
    rr = requests.put(f"{GH}/repos/{repo}/contents/{path}", headers=H, json=b, timeout=20)
    return rr.status_code

s1 = s2 = "skip(local)"
if YARD_PUSH:
    old_jl, _ = gf(BENCH_REPO, jl_path)                   # 同日多班：追加而非覆盖
    s1 = pf(BENCH_REPO, jl_path, ((old_jl or "").rstrip("\n") + "\n" + "\n".join(lines_j) + "\n").lstrip("\n"),
            "yard bench results [skip ci]")
    s2 = pf(BENCH_REPO, "bench/latest.md", md + "\n", "yard bench latest [skip ci]")

# ── 每班一行摘要回写 ci-control 用量台账（跨仓 App token 直推；暖侧 YARD_LEDGER=0 跳过）──
old, _ = (gf("chepin-ai/ci-control", "bridge/llm-usage.jsonl") if YARD_LEDGER else (None, None))
entry = json.dumps({"ts": ts, "src": "ci-yard/yard-llm-bench", "valley": VALLEY,
                    "cells": len(run_rows), "skipped": len(skip_rows),
                    "tok": tot_tok, "cost_usd": tot_cost}, ensure_ascii=False)
s3 = "skip(ledger off)"
if YARD_LEDGER:
    newlog = ((old or "").rstrip("\n") + "\n" + entry + "\n").lstrip("\n")
    s3 = pf("chepin-ai/ci-control", "bridge/llm-usage.jsonl", newlog, "yard 班用量摘要 [skip ci]")

print("yard bench done:", json.dumps({"valley": VALLEY, "cells": len(run_rows),
      "skipped": len(skip_rows), "tok": tot_tok, "cost": tot_cost,
      "push": [s1, s2, s3], "agg": agg}, ensure_ascii=False))

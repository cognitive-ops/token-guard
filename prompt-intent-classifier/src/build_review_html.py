"""Run the deployment model over the full dataset and emit a self-contained HTML
review tool — browse/filter/search predictions vs Sonnet labels on train + test.

Output: data/review.html  (gitignored — contains prompt text). Open in a browser.
"""

import json
import os
import sys

import numpy as np
import torch
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from train_coarse_mt import COARSE, F2C
from train_ft import MultiTask, load_joined
from transformers import AutoTokenizer

MODEL = os.environ.get("REVIEW_MODEL", "data/model_coarse_mt_xlm-roberta-base.pt")
OUT = "data/review.html"
FINE = taxonomy.INTENTS
BEH = taxonomy.BEHAVIORS
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def main():
    # raw rows with prompt + prev + labels (aligned with load_joined order)
    items = {json.loads(l)["prompt_id"]: json.loads(l) for l in open("data/label_items.jsonl")}
    meta = [json.loads(l) for l in open("data/labeled.jsonl")]
    rows = load_joined()
    assert len(meta) == len(rows)

    y = np.array([r["intent"] for r in rows])
    idx = np.arange(len(rows))
    tr, te = train_test_split(idx, test_size=0.2, random_state=0, stratify=y)
    split = np.array(["train"] * len(rows), dtype=object)
    split[te] = "test"

    b = torch.load(MODEL, map_location=DEVICE)
    tok = AutoTokenizer.from_pretrained(b["base"])
    model = MultiTask(b["base"], len(b["intents"]), len(b["behaviors"]))
    model.load_state_dict(b["state_dict"])
    model.to(DEVICE).eval()
    coarse_labels = b["intents"]
    beh_labels = b["behaviors"]
    # display label order must match how r["behaviors"] was built (taxonomy order)
    assert beh_labels == BEH, f"behavior label/order mismatch: {beh_labels} vs {BEH}"

    records = []
    BS = 64
    with torch.no_grad():
        for s in range(0, len(rows), BS):
            chunk = rows[s : s + BS]
            enc = tok(
                [r["text"] for r in chunk],
                truncation=True,
                max_length=256,
                padding=True,
                return_tensors="pt",
            ).to(DEVICE)
            li, lb = model(**enc)
            p = torch.softmax(li, 1)
            conf, top = p.max(1)
            bprob = torch.sigmoid(lb)
            for k, r in enumerate(chunk):
                gi = s + k
                m = meta[gi]
                it = items.get(m["prompt_id"], {})
                prior = it.get("prior_prompts") or []
                pred_intent = coarse_labels[int(top[k])]
                true_coarse = COARSE[F2C[r["intent"]]]
                full_prompt = m.get("prompt") or ""
                full_prev = prior[-1] if prior else ""
                prompt = full_prompt[:4000] + ("  …[truncated]" if len(full_prompt) > 4000 else "")
                prev = full_prev[:400] + ("…" if len(full_prev) > 400 else "")
                tb = [beh_labels[j] for j in range(len(beh_labels)) if r["behaviors"][j]]
                pb = [beh_labels[j] for j in range(len(beh_labels)) if bprob[k, j] >= 0.5]
                records.append(
                    {
                        "split": split[gi],
                        "user": (m.get("user_email") or "?").split("@")[0],
                        "prompt": prompt,
                        "prev": prev,
                        "fine": FINE[r["intent"]],
                        "true": true_coarse,
                        "pred": pred_intent,
                        "conf": round(float(conf[k]), 2),
                        "ok": pred_intent == true_coarse,
                        "tb": tb,
                        "pb": pb,
                        "bok": sorted(tb) == sorted(pb),  # behaviors exact-match
                    }
                )

    n = len(records)
    test_recs = [r for r in records if r["split"] == "test"]
    test_acc = sum(r["ok"] for r in test_recs) / max(1, len(test_recs))
    train_acc = sum(r["ok"] for r in records if r["split"] == "train") / max(1, n - len(test_recs))
    # escape </ so a prompt containing "</script>" can't terminate the embedded <script>
    data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")

    page = (
        TEMPLATE.replace("__DATA__", data_json)
        .replace("__N__", str(n))
        .replace("__NTEST__", str(len(test_recs)))
        .replace("__TESTACC__", f"{100 * test_acc:.1f}")
        .replace("__TRAINACC__", f"{100 * train_acc:.1f}")
        .replace("__INTENTS__", json.dumps(coarse_labels))
        .replace("__MODEL__", os.path.basename(MODEL))
    )
    open(OUT, "w").write(page)
    print(
        f"wrote {OUT}  ({n} rows; test acc {100 * test_acc:.1f}%, train acc {100 * train_acc:.1f}%)"
    )


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Prompt Intent — Model Review</title>
<style>
 body{font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1419;color:#e6edf3}
 header{position:sticky;top:0;background:#161b22;border-bottom:2px solid #017AFF;padding:12px 16px;z-index:5}
 h1{margin:0 0 6px;font-size:18px;color:#3399ff}
 .sum{color:#8a93a2;font-size:12px;margin-bottom:8px}
 .sum b{color:#e6edf3}
 .ctl{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
 select,input{background:#0d1117;color:#e6edf3;border:1px solid #2a3441;border-radius:6px;padding:6px 8px;font-size:13px}
 input[type=text]{min-width:280px}
 table{border-collapse:collapse;width:100%}
 th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #1c2531;vertical-align:top}
 th{position:sticky;top:96px;background:#11161d;color:#8a93a2;font-size:11px;text-transform:uppercase;cursor:pointer}
 tr:hover{background:#141b24}
 .ok{color:#3fb950}.bad{color:#f85149;font-weight:600}
 .pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;border:1px solid #2a3441;margin:1px}
 .b-true{color:#58a6ff;border-color:#1f6feb}.b-pred{color:#d29922;border-color:#9e6a03}
 .prompt{max-width:640px;white-space:pre-wrap;word-break:break-word}
 .prev{color:#6e7681;font-size:11px;border-left:2px solid #2a3441;padding-left:6px;margin-bottom:3px}
 .muted{color:#6e7681}.tag{font-size:11px;color:#8a93a2}
 #count{color:#8a93a2;margin-left:auto}
 .conf{font-variant-numeric:tabular-nums}
 button{background:#0d1117;color:#e6edf3;border:1px solid #2a3441;border-radius:6px;padding:6px 10px;cursor:pointer}
</style></head><body>
<header>
 <h1>Prompt Intent &amp; Behavior — Model Review <span class="tag">model: __MODEL__</span></h1>
 <div class="sum"><b>__N__</b> prompts · test set <b>__NTEST__</b> · test accuracy <b>__TESTACC__%</b> · train accuracy <b>__TRAINACC__%</b> · showing coarse intent (true vs predicted) &amp; behaviors (<span class="b-true">true</span>/<span class="b-pred">pred</span>)</div>
 <div class="ctl">
  <select id="fsplit"><option value="">all sets</option><option value="test">test only</option><option value="train">train only</option></select>
  <select id="ftrue"><option value="">true intent: any</option></select>
  <select id="fpred"><option value="">pred intent: any</option></select>
  <select id="fok"><option value="">correct + wrong</option><option value="1">correct only</option><option value="0">wrong only</option></select>
  <select id="fbeh"><option value="">any behavior</option></select>
  <input id="q" type="text" placeholder="search prompt text…">
  <span id="count"></span>
 </div>
</header>
<table><thead><tr>
 <th data-k="split">set</th><th data-k="user">user</th><th data-k="true">true→pred</th>
 <th data-k="conf">conf</th><th>behaviors (true / pred)</th><th class="prompt">prompt</th>
</tr></thead><tbody id="tb"></tbody></table>
<div style="padding:12px 16px"><button id="more">show more ▼</button></div>
<script>
const DATA=__DATA__, INTENTS=__INTENTS__, BEH_ALL=["well-specified","underspecified","stuck-looping","verifies-output","scope-expansion"];
const tb=document.getElementById('tb');
for(const id of ['ftrue','fpred']){const s=document.getElementById(id);for(const i of INTENTS){const o=document.createElement('option');o.value=i;o.text=id[1]==='t'?'true: '+i:'pred: '+i;s.add(o);}}
{const s=document.getElementById('fbeh');for(const b of BEH_ALL){const o=document.createElement('option');o.value=b;o.text=b;s.add(o);}}
let sortK='conf',sortAsc=true,shown=200;
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function filtered(){
 const sp=fsplit.value,tt=ftrue.value,pp=fpred.value,ok=fok.value,bh=fbeh.value,q=qel.value.toLowerCase();
 let r=DATA.filter(d=>(!sp||d.split===sp)&&(!tt||d.true===tt)&&(!pp||d.pred===pp)&&(ok===''||(d.ok?'1':'0')===ok)&&(!bh||d.tb.includes(bh)||d.pb.includes(bh))&&(!q||d.prompt.toLowerCase().includes(q)||d.prev.toLowerCase().includes(q)));
 r.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(x<y)return sortAsc?-1:1;if(x>y)return sortAsc?1:-1;return 0;});
 return r;
}
function beh(list,cls){return list.map(b=>`<span class="pill ${cls}">${b}</span>`).join('')||'<span class="muted">—</span>';}
function render(){
 const r=filtered();document.getElementById('count').textContent=r.length+' rows';
 tb.innerHTML=r.slice(0,shown).map(d=>`<tr>
  <td class="tag">${d.split}</td><td class="muted">${esc(d.user)}</td>
  <td class="${d.ok?'ok':'bad'}">${d.true} → ${d.pred}${d.ok?' ✓':' ✗'}<div class="tag">fine: ${d.fine}</div></td>
  <td class="conf">${d.conf}</td>
  <td><span class="${d.bok?'ok':'bad'}" title="behaviors exact-match">${d.bok?'✓':'✗'}</span> ${beh(d.tb,'b-true')}<br><span style="visibility:hidden">✓</span> ${beh(d.pb,'b-pred')}</td>
  <td class="prompt">${d.prev?`<div class="prev">${esc(d.prev)}</div>`:''}${esc(d.prompt)}</td>
 </tr>`).join('');
 document.getElementById('more').style.display=r.length>shown?'inline-block':'none';
}
const qel=document.getElementById('q');
for(const id of ['fsplit','ftrue','fpred','fok','fbeh'])document.getElementById(id).onchange=()=>{shown=200;render()};
qel.oninput=()=>{shown=200;render()};
document.getElementById('more').onclick=()=>{shown+=400;render()};
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortAsc=(sortK===k)?!sortAsc:true;sortK=k;render()});
render();
</script></body></html>"""


if __name__ == "__main__":
    main()

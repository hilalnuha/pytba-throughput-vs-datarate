"""
Compares the closed-form transport models of pytba.py with the ns-3 runs in
validation_ns3.jsonl and writes validation_ns3_summary.csv and the LaTeX rows of
Table 5 (ns3_rows.tex).

For the ns-3 point-to-point link the payload ceiling is C * 1460/1502
(2-byte PPP header), so the models are capped by (1-p) * C * 1460/1502.
"""
import csv
import json
from collections import defaultdict

import pytba as tb

runs = defaultdict(list)
with open("validation_ns3.jsonl") as f:
    for d in map(json.loads, f):
        runs[(d["grid"], d["variant"], d["C_mbps"], d["rtt_ms"], d["p"])].append(d["goodput_mbps"])

ORDER = {"100m": 0, "1g": 1, "e6": 2}
VORD = {"Reno": 0, "CUBIC": 1, "BBR": 2}
rows = []
for (grid, v, c, r, p), g in sorted(runs.items(), key=lambda kv: (ORDER[kv[0][0]], VORD[kv[0][1]], kv[0][4])):
    C, rtt = c * 1e6, r * 1e-3
    bound = tb.delivery_upper_bound(p, C * tb.MSS / (tb.MTU + 2))
    if v == "Reno":
        model, name = min(tb.pftk(p, rtt), bound), "PFTK, Eq. (11)"
    elif v == "CUBIC":
        model, name = min(tb.cubic(p, rtt), bound), "CUBIC, Eq. (17)"
    else:
        model, name = bound, "Bound, Eq. (12)"
    sim = sum(g) / len(g)
    rows.append(dict(grid=grid, variant=v, C=c, rtt=r, p=p, n=len(g),
                     sim=sim, smin=min(g), smax=max(g), model=model / 1e6,
                     dev=(model / 1e6 - sim) / sim * 100, model_name=name))

with open("validation_ns3_summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)


def fmt_p(p):
    if p in (1e-2, 1e-3, 1e-4, 1e-5):
        return f"$10^{{{int(round(__import__('math').log10(p)))}}}$"
    m, e = f"{p:.2e}".split("e")
    return f"${m}\\times10^{{{int(e)}}}$"


lines = []
prev = None
for r in rows:
    scen = (r["C"], r["rtt"])
    lab = f"{r['C']:g} Mb/s, {r['rtt']:g} ms" if scen != prev else ""
    if r["grid"] == "e6" and scen != prev:
        lab = "E6: 1000 Mb/s, 20 ms"
    if scen != prev and prev is not None:
        lines.append("\\hline")
    prev = scen
    lines.append(f"{lab} & {r['variant']} & {fmt_p(r['p'])} & {r['model']:.2f} & "
                 f"{r['sim']:.2f} & {r['smin']:.2f}--{r['smax']:.2f} & {r['dev']:+.0f}\\% \\\\"
                 if r["n"] > 1 else
                 f"{lab} & {r['variant']} & {fmt_p(r['p'])} & {r['model']:.2f} & "
                 f"{r['sim']:.2f} & --- & {r['dev']:+.0f}\\% \\\\")
open("ns3_rows.tex", "w").write("\n".join(lines) + "\n")
for r in rows:
    print(f"{r['grid']:4s} {r['variant']:5s} p={r['p']:.2e} model={r['model']:8.2f} "
          f"ns3={r['sim']:8.2f} [{r['smin']:.2f}, {r['smax']:.2f}] n={r['n']} dev={r['dev']:+.1f}%")

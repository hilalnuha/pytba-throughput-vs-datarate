"""
Regenerates every figure and number of the paper "Throughput vs Data Rate".

    python3 run_experiments.py          # writes figures/*.png and results.json

Experiments
  E1  physical layer   : Shannon vs Nyquist (16-QAM), per-lane efficiency of Ethernet PHYs
  E2  data link layer  : Ethernet goodput vs payload size under bit errors, MTU cap
  E3  transport layer  : PFTK / Mathis TCP throughput vs loss on 1000BASE-T
  E4  application layer: effective throughput of finite objects, IW = 10 (RFC 6928)
  E5  transport layer  : Reno, CUBIC and the delivery upper bound over five media,
                         at deployment RTTs and at 50 ms, plus the saturation boundary
  E6  worked example   : one 1000BASE-T path carried through all layers
"""
import json
import math
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pytba as tb

os.makedirs("figures", exist_ok=True)
plt.rcParams.update({"font.size": 11, "font.family": "serif",
                     "axes.grid": True, "grid.alpha": 0.35, "figure.dpi": 300})
R = {}  # results collected for the paper


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join("figures", name))
    plt.close(fig)


# ---------------------------------------------------------------------------
# E1a  Shannon vs Nyquist
# ---------------------------------------------------------------------------
B = np.linspace(0.1e6, 20e6, 400)
fig, ax = plt.subplots(figsize=(6.4, 4.2))
for snr in (0, 10, 20, 30):
    ax.plot(B / 1e6, tb.shannon(B, snr) / 1e6, label=f"Shannon capacity, SNR = {snr} dB")
ax.plot(B / 1e6, tb.nyquist_passband(B, 16) / 1e6, "k--", label="Nyquist limit, 16-QAM (passband)")
ax.set_xlabel("Bandwidth $B$ (MHz)")
ax.set_ylabel("Data rate (Mb/s)")
ax.legend(fontsize=9)
save(fig, "fig1_phy.png")
R["E1"] = dict(
    shannon_5MHz_20dB=float(tb.shannon(5e6, 20) / 1e6),
    nyquist16qam_5MHz=float(tb.nyquist_passband(5e6, 16) / 1e6),
    eta_shannon_20dB=float(math.log2(1 + 100)),
)

# ---------------------------------------------------------------------------
# E1b  Ethernet PHYs per lane
# ---------------------------------------------------------------------------
rows = tb.phy_table()
R["E1_phys"] = rows
fig, ax = plt.subplots(figsize=(6.4, 4.4))
bl = np.logspace(0, 3.5, 50)
for eta, ls in ((1, ":"), (2, "--"), (4, "-."), (6.25, "-")):
    ax.loglog(bl, eta * bl, ls, color="gray", lw=1)
    ax.annotate(f"$\\eta$ = {eta:g} b/s/Hz", (1.3, eta * 1.3 * 1.2),
                fontsize=8, color="gray", rotation=27)
for r in rows:
    ax.loglog(r["b_sig"], r["r_lane"], "o", color="tab:red", zorder=5)
    dx, dy = {"10BASE-T": (1.15, 0.75), "100BASE-TX": (1.15, 0.72),
              "1000BASE-T": (0.22, 1.35), "2.5GBASE-T": (1.15, 0.72),
              "10GBASE-T": (1.15, 0.72), "40GBASE-T": (0.25, 1.3)}[r["name"]]
    ax.annotate(r["name"], (r["b_sig"], r["r_lane"]),
                xytext=(r["b_sig"] * dx, r["r_lane"] * dy), fontsize=9)
ax.set_xlabel("Signal bandwidth per lane $f_s/2$ (MHz)")
ax.set_ylabel("Data rate per lane (Mb/s)")
ax.set_xlim(1, 4000)
ax.set_ylim(1, 40000)
save(fig, "fig2_phy_lanes.png")

# ---------------------------------------------------------------------------
# E2  link goodput vs payload
# ---------------------------------------------------------------------------
Rl = 1e9
L = np.arange(16, 4000, 1) * 8.0
fig, ax = plt.subplots(figsize=(6.4, 4.2))
R["E2"] = {}
for ber in (1e-6, 1e-5, 1e-4):
    S = tb.link_goodput(L, Rl, ber)
    ax.plot(L / 8, S / 1e6, label=f"BER = {ber:g}")
    Lstar = tb.optimal_payload_bits(ber)
    Lnum = L[np.argmax(S)]
    Luse = min(Lstar, tb.MTU * 8)
    ax.plot(Luse / 8, tb.link_goodput(Luse, Rl, ber) / 1e6, "ko", ms=4)
    R["E2"][f"{ber:g}"] = dict(Lstar_bytes=Lstar / 8, Lnum_bytes=float(Lnum / 8),
                               L_used=Luse / 8,
                               S_at_used=float(tb.link_goodput(Luse, Rl, ber) / 1e6),
                               S_at_1500=float(tb.link_goodput(1500 * 8, Rl, ber) / 1e6))
for ber in (1e-10, 1e-12):
    R["E2"][f"{ber:g}"] = dict(Lstar_bytes=tb.optimal_payload_bits(ber) / 8,
                               S_at_1500=float(tb.link_goodput(1500 * 8, Rl, ber) / 1e6))
ax.axvline(1500, color="k", ls="--", lw=1, label="Ethernet MTU (1500 bytes)")
ax.set_xlabel("Payload size $L$ (bytes)")
ax.set_ylabel("Link goodput $S$ (Mb/s)")
ax.legend(fontsize=9)
save(fig, "fig3_link.png")

# ---------------------------------------------------------------------------
# E3  TCP throughput vs loss on 1000BASE-T
# ---------------------------------------------------------------------------
C = 1e9
ceil_eth = tb.ETA_ETH * C
p = np.logspace(-8, -1, 400)
pm = p[p <= 1e-2]
fig, ax = plt.subplots(figsize=(6.4, 4.2))
R["E3"] = dict(ceiling_mbps=ceil_eth / 1e6)
for rtt, col in ((1e-3, "tab:blue"), (10e-3, "tab:orange"), (50e-3, "tab:green")):
    ax.loglog(p, np.minimum(tb.pftk(p, rtt), ceil_eth) / 1e6, color=col,
              label=f"PFTK, RTT = {rtt*1e3:g} ms")
    ax.loglog(pm, np.minimum(tb.mathis(pm, rtt), ceil_eth) / 1e6, "--", color=col, lw=1)
    R["E3"][f"rtt{rtt*1e3:g}"] = dict(
        pftk_p1e2=float(tb.pftk(1e-2, rtt) / 1e6),
        mathis_p1e2=float(tb.mathis(1e-2, rtt) / 1e6),
        pstar=float(tb.reno_saturation_loss(rtt, ceil_eth)),
        bdp_KiB=C * rtt / 8 / 1024)
ax.axhline(ceil_eth / 1e6, color="k", ls=":", lw=1.3,
           label="TCP payload ceiling of 1000BASE-T (949.3 Mb/s)")
ax.plot([], [], "k--", lw=1, label="Mathis (dashed, $p \\leq 10^{-2}$)")
ax.set_xlabel("Packet loss probability $p$")
ax.set_ylabel("TCP throughput (Mb/s)")
ax.legend(fontsize=8.5, loc="lower left")
save(fig, "fig4_tcp.png")

# ---------------------------------------------------------------------------
# E4  application-layer effective throughput
# ---------------------------------------------------------------------------
rtt = 50e-3
sizes = np.logspace(3, 9, 300)
fig, ax = plt.subplots(figsize=(6.4, 4.2))
R["E4"] = {}
for Cm, col in ((10e6, "tab:blue"), (100e6, "tab:orange"), (1e9, "tab:green")):
    te = [tb.effective_throughput(F, Cm, rtt) for F in sizes]
    ax.loglog(sizes / 1e3, np.array(te) / 1e6, color=col,
              label=f"Data rate {Cm/1e6:g} Mb/s, IW = 10")
    ax.axhline(tb.ETA_ETH * Cm / 1e6, color=col, ls=":", lw=1)
    for F in (10e3, 100e3, 1e6, 10e6, 100e6, 1e9):
        t, k = tb.transfer_time(F, Cm, rtt)
        R["E4"][f"C{Cm/1e6:g}_F{F/1e3:g}kB"] = dict(T=8 * F / t / 1e6, rounds=k, t=t)
te1 = [tb.effective_throughput(F, 100e6, rtt, iw=1) for F in sizes]
ax.loglog(sizes / 1e3, np.array(te1) / 1e6, "--", color="tab:orange", lw=1,
          label="Data rate 100 Mb/s, IW = 1")
R["E4"]["C100_F100kB_IW1"] = 8 * 100e3 / tb.transfer_time(100e3, 100e6, rtt, iw=1)[0] / 1e6
ax.set_xlabel("Object size (kB)")
ax.set_ylabel("Effective throughput (Mb/s)")
ax.legend(fontsize=8.5, loc="upper left")
save(fig, "fig5_app.png")

# ---------------------------------------------------------------------------
# E5  TCP variants over five media
# ---------------------------------------------------------------------------
P5 = 1e-5
media = [
    # name, data rate, payload ceiling, deployment RTT
    ("ADSL (G.992.1)", 8e6, 8e6 * 48 / 53 * tb.ETA_IP, 30e-3),
    ("STM-1 (G.707)", 155.52e6, 149.76e6 * tb.ETA_IP, 20e-3),
    ("100BASE-TX", 100e6, 100e6 * tb.ETA_ETH, 0.5e-3),
    ("1000BASE-T", 1e9, 1e9 * tb.ETA_ETH, 0.5e-3),
    ("10GBASE-T", 10e9, 10e9 * tb.ETA_ETH, 0.5e-3),
]
R["E5"] = []
for name, Cm, ceil, rtt_d in media:
    for rtt in (rtt_d, 50e-3):
        R["E5"].append(dict(
            medium=name, C=Cm / 1e6, ceiling=ceil / 1e6, rtt_ms=rtt * 1e3,
            reno=float(min(tb.pftk(P5, rtt), tb.delivery_upper_bound(P5, ceil)) / 1e6),
            cubic=float(min(tb.cubic(P5, rtt), tb.delivery_upper_bound(P5, ceil)) / 1e6),
            bound=float(tb.delivery_upper_bound(P5, ceil) / 1e6),
            pstar=float(tb.reno_saturation_loss(rtt, ceil))))

fig, ax = plt.subplots(figsize=(6.4, 4.3))
rtts = np.logspace(-4, 0, 200)
for name, Cm, ceil, rtt_d in media:
    line, = ax.loglog(rtts * 1e3, tb.reno_saturation_loss(rtts, ceil), label=name)
    ax.plot(rtt_d * 1e3, tb.reno_saturation_loss(rtt_d, ceil), "o", color=line.get_color())
ax.axhline(P5, color="k", ls="--", lw=1, label="$p = 10^{-5}$")
ax.set_xlabel("Round-trip time (ms)")
ax.set_ylabel("Saturation loss $p^*$")
ax.set_ylim(1e-12, 1)
ax.legend(fontsize=8.5, loc="lower left")
save(fig, "fig6_saturation.png")

# ---------------------------------------------------------------------------
# E6  worked example: one 1000BASE-T path through all layers
# ---------------------------------------------------------------------------
ber = 1e-10
rtt = 20e-3
F = 10e6
phy = [r for r in rows if r["name"] == "1000BASE-T"][0]
p_link = tb.frame_loss(ber, (tb.MTU + tb.ETH_EXPOSED) * 8)
link_gp = 1e9 * tb.MTU / tb.ETH_WIRE * (1 - p_link)
tcp_ceiling = 1e9 * tb.ETA_ETH
reno = min(tb.pftk(p_link, rtt), tb.delivery_upper_bound(p_link, tcp_ceiling))
cub = min(tb.cubic(p_link, rtt), tb.delivery_upper_bound(p_link, tcp_ceiling))
t_obj, k_obj = tb.transfer_time(F, 1e9, rtt)
R["E6"] = dict(
    lanes=phy["lanes"], r_lane=phy["r_lane"], b_sig=phy["b_sig"], eta=phy["eta"],
    snr_min=phy["snr_min"], ber=ber, p_link=p_link,
    link_goodput=link_gp / 1e6, tcp_ceiling=tcp_ceiling / 1e6,
    reno=reno / 1e6, cubic=cub / 1e6, rtt_ms=rtt * 1e3,
    F_MB=F / 1e6, t_obj=t_obj, rounds=k_obj, app=8 * F / t_obj / 1e6,
    losses_expected=math.ceil(F / tb.MSS) * p_link)

with open("results.json", "w") as f:
    json.dump(R, f, indent=1, default=float)

# ---------------------------------------------------------------------------
# console summary
# ---------------------------------------------------------------------------
print(json.dumps(R["E1"], indent=1))
for r in rows:
    print(f"{r['name']:11s} lanes={r['lanes']} fs={r['mbd']:5d} MBd Bsig={r['b_sig']:7.1f} "
          f"Rlane={r['r_lane']:7.1f} eta={r['eta']:.2f} SNRmin={r['snr_min']:.2f} dB "
          f"occ={r['occupancy']:.2f}")
print(json.dumps(R["E2"], indent=1))
print(json.dumps(R["E3"], indent=1))
for k, v in R["E4"].items():
    print(k, v)
for r in R["E5"]:
    print(f"{r['medium']:15s} C={r['C']:8.2f} ceil={r['ceiling']:8.2f} RTT={r['rtt_ms']:5.1f} "
          f"reno={r['reno']:8.2f} cubic={r['cubic']:8.2f} bound={r['bound']:8.2f} p*={r['pstar']:.2e}")
print(json.dumps(R["E6"], indent=1))

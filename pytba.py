"""
PyTBA - Python Throughput-Bandwidth Analyzer
Closed-form models used in the tutorial paper "Throughput vs Data Rate"
(Nuha, Novoseltsev, Iddi, Jurnal INFOTEL).

Every function returns rates in bit/s unless stated otherwise.
All models are standard results from the literature; references are given
in each docstring. Nothing here is a new model: the package collects them in
one place so that every number in the paper can be regenerated.
"""
import math

import numpy as np

# ----------------------------------------------------------------------------
# Common constants
# ----------------------------------------------------------------------------
MSS = 1460                 # TCP payload per segment [byte]
IP_TCP_HDR = 40            # IPv4 + TCP headers without options [byte]
MTU = MSS + IP_TCP_HDR     # 1500 byte
ETH_EXPOSED = 26           # preamble/SFD 8 + MAC header 14 + FCS 4 [byte]
ETH_IFG = 12               # inter-frame gap [byte]
ETH_WIRE = MTU + ETH_EXPOSED + ETH_IFG   # 1538 byte on the wire per full frame

ETA_ETH = MSS / ETH_WIRE   # TCP payload fraction of an Ethernet wire frame
ETA_IP = MSS / MTU         # TCP payload fraction of an IP packet (link framing excluded)


# ----------------------------------------------------------------------------
# Section 2.1 definitions
# ----------------------------------------------------------------------------
def data_rate(n_tx_bits, T):
    """R = N_tx / T  (Eq. 2)."""
    return n_tx_bits / T


def throughput(n_packets, packet_bits, T_obs):
    """Thr = n_p * L_p / T_obs  (Eq. 3)."""
    return n_packets * packet_bits / T_obs


def goodput(n_payload_bits, T_obs):
    """G = N_payload / T_obs  (Eq. 4)."""
    return n_payload_bits / T_obs


# ----------------------------------------------------------------------------
# E1: physical layer
# ----------------------------------------------------------------------------
def shannon(B, snr_db):
    """Shannon capacity C = B log2(1 + SNR) [Shannon 1948]."""
    return B * np.log2(1 + 10 ** (np.asarray(snr_db) / 10))


def nyquist_passband(B, M):
    """Maximum bit rate of M-ary QAM in a passband of width B with ideal
    Nyquist pulses: symbol rate B, so R = B log2 M."""
    return B * np.log2(M)


def nyquist_baseband(B, M):
    """Maximum bit rate of M-level PAM in a baseband channel of width B:
    symbol rate 2B, so R = 2B log2 M [Nyquist 1928]."""
    return 2 * B * np.log2(M)


def min_snr_db(eta):
    """SNR needed by Shannon for spectral efficiency eta [b/s/Hz]."""
    return 10 * np.log10(2 ** np.asarray(eta) - 1)


# Twisted-pair Ethernet PHYs (IEEE 802.3 clauses cited in the paper).
# name, standard, minimum cable, cable rating [MHz], lanes per direction,
# symbol rate per lane [MBd], data rate [Mb/s]
PHYS = [
    ("10BASE-T",   "802.3i",  "Cat3",  16,   1,   20,    10),
    ("100BASE-TX", "802.3u",  "Cat5",  100,  1,   125,   100),
    ("1000BASE-T", "802.3ab", "Cat5",  100,  4,   125,   1000),
    ("2.5GBASE-T", "802.3bz", "Cat5e", 100,  4,   200,   2500),
    ("10GBASE-T",  "802.3an", "Cat6A", 500,  4,   800,   10000),
    ("40GBASE-T",  "802.3bq", "Cat8",  2000, 4,   3200,  40000),
]


def phy_table():
    """Per-lane view of each PHY: signal (Nyquist) bandwidth f_s/2, per-lane
    data rate, per-lane spectral efficiency and the Shannon SNR it needs."""
    rows = []
    for name, std, cable, rating, lanes, mbd, rate in PHYS:
        b_sig = mbd / 2.0                      # MHz
        r_lane = rate / lanes                  # Mb/s
        eta = r_lane / b_sig                   # b/s/Hz
        rows.append(dict(name=name, std=std, cable=cable, rating=rating,
                         lanes=lanes, mbd=mbd, b_sig=b_sig, rate=rate,
                         r_lane=r_lane, eta=eta,
                         snr_min=float(min_snr_db(eta)),
                         occupancy=b_sig / rating))
    return rows


# ----------------------------------------------------------------------------
# E2: data link layer
# ----------------------------------------------------------------------------
def link_goodput(L_bits, R, ber, H_t=(ETH_EXPOSED + ETH_IFG) * 8, H_e=ETH_EXPOSED * 8):
    """S(L) = R * L/(L+H_t) * (1-b)^(L+H_e).
    H_t: overhead that consumes link time; H_e: overhead exposed to bit errors."""
    L = np.asarray(L_bits, dtype=float)
    return R * L / (L + H_t) * (1 - ber) ** (L + H_e)


def optimal_payload_bits(ber, H_t=(ETH_EXPOSED + ETH_IFG) * 8):
    """L* = (H_t/2) (sqrt(1 - 4/(H_t ln(1-b))) - 1)
    [Bertsekas and Gallager 1992; Modiano 1999]. Independent of H_e."""
    a = math.log(1 - ber)
    return H_t / 2 * (math.sqrt(1 - 4 / (H_t * a)) - 1)


def frame_loss(ber, frame_bits):
    """Probability that at least one bit of a frame is in error."""
    return 1 - (1 - ber) ** frame_bits


# ----------------------------------------------------------------------------
# E3 / E5: transport layer
# ----------------------------------------------------------------------------
def mathis(p, rtt, mss=MSS):
    """T = (MSS/RTT) sqrt(3/(2p))  [Mathis et al. 1997].
    Valid for long-lived Reno flows with triple-duplicate losses only,
    i.e. small p (no timeouts); used here for p <= 1e-2."""
    return mss * 8 / rtt * np.sqrt(3 / (2 * np.asarray(p, dtype=float)))


def pftk(p, rtt, mss=MSS, b=1, t0=1.0):
    """Padhye et al. 1998 'full' model with retransmission timeouts.
    t0 = 1 s is the minimum RTO of RFC 6298."""
    p = np.asarray(p, dtype=float)
    den = rtt * np.sqrt(2 * b * p / 3) \
        + t0 * np.minimum(1, 3 * np.sqrt(3 * b * p / 8)) * p * (1 + 32 * p ** 2)
    return mss * 8 / den


def cubic_response(p, rtt, mss=MSS, c=0.4, beta=0.7):
    """CUBIC average window under deterministic loss, converted to a rate
    [Ha et al. 2008; RFC 9438 Sec. 5]."""
    p = np.asarray(p, dtype=float)
    return mss * 8 * (c * (3 + beta) / (4 * (1 - beta))) ** 0.25 \
        / (rtt ** 0.25 * p ** 0.75)


def cubic(p, rtt, mss=MSS):
    """CUBIC uses the larger of its cubic window and its Reno-friendly
    estimate (RFC 9438 Sec. 4.3); the Reno estimate is taken from PFTK."""
    return np.maximum(cubic_response(p, rtt, mss), pftk(p, rtt, mss))


def delivery_upper_bound(p, ceiling):
    """(1-p) * eta_h * C: the most any sender can deliver over a path whose
    payload ceiling is eta_h*C when a fraction p of packets is lost.
    This is an upper bound, not a model of BBR [Cardwell et al. 2017]."""
    return (1 - np.asarray(p, dtype=float)) * ceiling


def reno_saturation_loss(rtt, ceiling, mss=MSS):
    """Largest p at which the Mathis rate still reaches the ceiling:
    p* = (3/2) (MSS / (RTT * ceiling))^2."""
    return 1.5 * (mss * 8 / (rtt * ceiling)) ** 2


# ----------------------------------------------------------------------------
# E4: application layer
# ----------------------------------------------------------------------------
def transfer_time(F, C, rtt, iw=10, mss=MSS, wire=ETH_WIRE):
    """Total time to deliver an object of F bytes over an idle loss-free path.

    t = RTT (handshake) + sum_k tau_k, with
      N      = ceil(F / MSS) segments,
      W*     = C*RTT / (8*wire)               segments that fill the pipe,
      w_k    = min(IW * 2^k, W*)              window in round k (slow start),
      s_k    = min(w_k, N - sum_{j<k} s_j)    segments sent in round k,
      tau_k  = max(RTT, 8*wire*s_k / C)       duration of round k,
    every round, including the last partial one, lasting at least one RTT
    (time until the sender holds the last ACK).
    Returns (t, number_of_rounds)."""
    n = math.ceil(F / mss)
    w_star = C * rtt / (8 * wire)
    t = rtt
    sent = 0
    k = 0
    while sent < n:
        w = min(iw * 2 ** k, w_star)
        s = min(math.ceil(w), n - sent)
        t += max(rtt, 8 * wire * s / C)
        sent += s
        k += 1
    return t, k


def effective_throughput(F, C, rtt, iw=10):
    """T_eff = 8F / t_total."""
    t, _ = transfer_time(F, C, rtt, iw=iw)
    return 8 * F / t

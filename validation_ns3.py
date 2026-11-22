"""
PyTBA validation with the ns-3 packet-level simulator (ns-3.44, pip package "ns3").

Topology: two nodes joined by one point-to-point link of data rate C and
one-way delay RTT/2. Random packet loss with probability p is applied by a
RateErrorModel (packet unit) on the receiving device, so only data segments
are lost. A BulkSend application runs one TCP flow for SIM_TIME seconds and
the goodput is measured at the PacketSink after a warm-up period.

Usage:
    python3 validation_ns3.py 100m [Reno|CUBIC|BBR]  # 100 Mb/s, 50 ms grid
    python3 validation_ns3.py 1g   [variant]          # 1 Gb/s, 5 ms grid
    python3 validation_ns3.py e6   [variant]          # worked example E6
    python3 validation_ns3.py Reno 100 50 1e-3        # single run
Results are appended to validation_ns3.jsonl (one JSON object per run/seed);
points already present are skipped, so interrupted grids resume.
"""
import json
import os
import sys
import time

from ns import ns

VARIANT = {
    "Reno": "ns3::TcpLinuxReno",
    "CUBIC": "ns3::TcpCubic",
    "BBR": "ns3::TcpBbr",
}

MSS = 1460          # TCP payload bytes per segment
WARMUP = 10.0       # s, excluded from the goodput average
SIM_TIME = 70.0     # s


def run(variant, rate_mbps, rtt_ms, p, seed=1):
    ns.RngSeedManager.SetSeed(seed)
    ns.RngSeedManager.SetRun(1)

    ns.Config.SetDefault("ns3::TcpL4Protocol::SocketType",
                         ns.StringValue(VARIANT[variant]))
    ns.Config.SetDefault("ns3::TcpSocket::SegmentSize", ns.UintegerValue(MSS))
    ns.Config.SetDefault("ns3::TcpSocket::InitialCwnd", ns.UintegerValue(10))
    ns.Config.SetDefault("ns3::TcpSocket::DelAckCount", ns.UintegerValue(1))
    big = 64 * 1024 * 1024
    ns.Config.SetDefault("ns3::TcpSocket::SndBufSize", ns.UintegerValue(big))
    ns.Config.SetDefault("ns3::TcpSocket::RcvBufSize", ns.UintegerValue(big))
    ns.Config.SetDefault("ns3::TcpSocketBase::Sack", ns.BooleanValue(True))
    ns.Config.SetDefault("ns3::TcpSocketBase::MinRto", ns.TimeValue(ns.Seconds(1.0)))

    nodes = ns.NodeContainer()
    nodes.Create(2)

    p2p = ns.PointToPointHelper()
    p2p.SetDeviceAttribute("DataRate", ns.StringValue(f"{rate_mbps}Mbps"))
    p2p.SetChannelAttribute("Delay", ns.StringValue(f"{rtt_ms / 2.0}ms"))
    # queue of two bandwidth-delay products so the queue itself never drops
    bdp_pkts = int(rate_mbps * 1e6 * rtt_ms * 1e-3 / (8 * 1500)) + 10
    p2p.SetQueue("ns3::DropTailQueue<Packet>", "MaxSize",
                 ns.QueueSizeValue(ns.QueueSize(f"{2 * bdp_pkts}p")))
    devices = p2p.Install(nodes)

    em = ns.CreateObject[ns.RateErrorModel]()
    em.SetAttribute("ErrorUnit", ns.StringValue("ERROR_UNIT_PACKET"))
    em.SetAttribute("ErrorRate", ns.DoubleValue(p))
    devices.Get(1).SetAttribute("ReceiveErrorModel", ns.PointerValue(em))

    stack = ns.InternetStackHelper()
    stack.Install(nodes)
    addr = ns.Ipv4AddressHelper()
    addr.SetBase(ns.Ipv4Address("10.1.1.0"), ns.Ipv4Mask("255.255.255.0"))
    ifaces = addr.Assign(devices)

    port = 5001
    sink_addr = ns.InetSocketAddress(ns.Ipv4Address.GetAny(), port).ConvertTo()
    sink_helper = ns.PacketSinkHelper("ns3::TcpSocketFactory", sink_addr)
    sink_apps = sink_helper.Install(nodes.Get(1))
    sink_apps.Start(ns.Seconds(0.0))

    dst = ns.InetSocketAddress(ifaces.GetAddress(1), port).ConvertTo()
    src = ns.BulkSendHelper("ns3::TcpSocketFactory", dst)
    src.SetAttribute("MaxBytes", ns.UintegerValue(0))
    src.SetAttribute("SendSize", ns.UintegerValue(MSS))
    src_apps = src.Install(nodes.Get(0))
    src_apps.Start(ns.Seconds(0.1))

    sink = sink_apps.Get(0).GetObject[ns.PacketSink]()

    ns.Simulator.Stop(ns.Seconds(WARMUP))
    ns.Simulator.Run()
    rx0 = sink.GetTotalRx()
    ns.Simulator.Stop(ns.Seconds(SIM_TIME - WARMUP))
    ns.Simulator.Run()
    rx1 = sink.GetTotalRx()
    ns.Simulator.Destroy()

    return (rx1 - rx0) * 8 / (SIM_TIME - WARMUP) / 1e6   # payload goodput, Mb/s


GRIDS = {
    # name: (points, seeds, warm-up [s], end time [s])
    "100m": ([(v, 100, 50, p) for v in ("Reno", "CUBIC", "BBR") for p in (1e-4, 1e-3, 1e-2)],
             (1, 2, 3), 10.0, 70.0),
    "1g": ([(v, 1000, 5, p) for v in ("Reno", "CUBIC", "BBR") for p in (1e-5, 1e-4)],
           (1, 2), 5.0, 25.0),
    # worked example E6: 1000BASE-T, RTT 20 ms, packet loss from BER 1e-10
    "e6": ([(v, 1000, 20, 1 - (1 - 1e-10) ** (8 * (1500 + 26))) for v in ("Reno", "CUBIC", "BBR")],
           (1,), 20.0, 70.0),
}
OUT = "validation_ns3.jsonl"


def done_points():
    if not os.path.exists(OUT):
        return set()
    with open(OUT) as f:
        return {(d["grid"], d["variant"], d["seed"], round(d["p"], 15))
                for d in map(json.loads, f)}


def run_grid(name, only=None):
    """Run every point of a grid that is not yet in validation_ns3.jsonl.
    Each result is appended immediately, so an interrupted run can resume."""
    global WARMUP, SIM_TIME
    points, seeds, WARMUP, SIM_TIME = GRIDS[name]
    done = done_points()
    for v, c, r, p in points:
        if only and v != only:
            continue
        for s in seeds:
            if (name, v, s, round(p, 15)) in done:
                continue
            t0 = time.time()
            g = run(v, c, r, p, seed=s)
            rec = dict(grid=name, variant=v, C_mbps=c, rtt_ms=r, p=p, seed=s,
                       warmup_s=WARMUP, end_s=SIM_TIME, goodput_mbps=g)
            with open(OUT, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"{name} {v:6s} C={c} RTT={r} p={p:.3g} seed={s}: {g:.3f} Mb/s "
                  f"({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in GRIDS:
        run_grid(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    elif len(sys.argv) == 5:
        v, c, r, p = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
        t0 = time.time()
        g = run(v, c, r, p)
        print(f"{v} C={c} RTT={r} p={p}: goodput={g:.3f} Mb/s ({time.time()-t0:.0f} s wall)")
    else:
        print(__doc__)

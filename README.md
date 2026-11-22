# PyTBA: Python Throughput-Bandwidth Analyzer

Code and data for the paper **"Throughput vs Data Rate"** (H. H. Nuha, I. Novoseltsev, H. Iddi, *Jurnal INFOTEL*, under review).

The paper traces the gap between the **data rate** a technology declares and the
**throughput** a receiver actually gets, layer by layer through the TCP/IP model.
All models are established results from the literature; this repository collects
them in one place so that every figure and number in the paper can be regenerated.

| File | Content |
|---|---|
| `pytba.py` | Closed-form models (Shannon, Nyquist, Ethernet PHY efficiency, frame-length optimum, Mathis, PFTK, CUBIC, delivery bound, saturation loss, slow-start transfer time) |
| `run_experiments.py` | Experiments E1-E6; writes `figures/*.png` and `results.json` |
| `validation_ns3.py` | ns-3 packet-level validation (Linux Reno, CUBIC, BBR over a lossy point-to-point link) |
| `validation_ns3.jsonl` | One JSON record per ns-3 run and seed |
| `compare_ns3.py` | Compares models with ns-3; writes `validation_ns3_summary.csv` (Table 5 of the paper) |
| `results.json` | Every number reported in the paper |
| `diagrams/topo_*.tex` | Standalone TikZ topology diagrams of E1-E6 and the ns-3 setup (Figs. 1-7 of the paper); compiled to `diagrams/topo_*.pdf` by the workflow |
| `.github/workflows/regenerate.yml` | GitHub Actions workflow that re-runs the experiments on every change and commits `figures/`, `diagrams/*.pdf`, `results.json` and `validation_ns3_summary.csv` |

## Experiments

| ID | Layer | What it shows |
|---|---|---|
| E1 | Physical | Shannon vs Nyquist (16-QAM); per-lane spectral efficiency of 10BASE-T ... 40GBASE-T |
| E2 | Data link | Ethernet goodput vs payload under bit errors; the 1500-byte MTU caps the optimum |
| E3 | Transport | PFTK and Mathis TCP throughput vs loss on 1000BASE-T, payload ceiling 949.3 Mb/s |
| E4 | Application | Effective throughput of finite objects with IW = 10 (RFC 6928) |
| E5 | Transport | Reno, CUBIC and the delivery upper bound over ADSL, STM-1, 100BASE-TX, 1000BASE-T, 10GBASE-T; saturation loss p* |
| E6 | All | One 1000BASE-T path (BER 1e-10, RTT 20 ms, 10 MB object) carried through all layers |

## Usage

```bash
pip install numpy matplotlib
python3 run_experiments.py           # figures/ + results.json, about 10 s

# optional packet-level validation (ns-3.44 Python bindings)
pip install ns3==3.44.post0
python3 validation_ns3.py 100m       # 100 Mb/s, 50 ms grid
python3 validation_ns3.py 1g         # 1 Gb/s, 5 ms grid
python3 validation_ns3.py e6         # worked example E6 (1 Gb/s, 20 ms)
python3 compare_ns3.py               # model vs ns-3 -> validation_ns3_summary.csv
python3 validation_ns3.py Reno 100 50 1e-3   # single run
```

Each run is appended to `validation_ns3.jsonl` as soon as it finishes and finished
points are skipped, so an interrupted grid resumes where it stopped. The goodput of
the first 100 Mb/s and 1 Gb/s runs was recovered from the console log after an
interruption and is therefore stored with two decimals. BBR at 100 Mb/s with
p = 1e-2 was not simulated (the run did not finish within our computing budget).

Topology diagrams (one standalone PDF per experiment, included in the paper with `\includegraphics`):

```bash
cd diagrams && for f in topo_*.tex; do pdflatex $f; done
```

## Conventions

* MSS = 1460 bytes; Ethernet wire frame for a full segment = 1538 bytes, so the
  TCP payload ceiling of an Ethernet link is 1460/1538 = 94.93 % of its data rate.
* Reno throughput uses the PFTK model (Padhye et al. 1998) with T0 = 1 s; the Mathis
  model is shown only for p <= 1e-2, where it is valid.
* For BBR only the delivery upper bound (1 - p) * eta_h * C is stated; how close BBR
  comes to it is measured with ns-3.

## License

MIT, see `LICENSE`. If you use this code, please cite the paper (`CITATION.cff`).

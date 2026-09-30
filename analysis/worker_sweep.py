#!/usr/bin/env python3
"""
Sweep the server worker count and record the client score.

Example:
    python3 analysis/worker_sweep.py \
      --workers 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20 \
      --reps 10 \
      --seed 5041 \
      --total 500 \
      --difficulty 3000000 \
      --delay 50000 \
      --rep 20 \
      --lambda 1.5 \
      --poly-degree 8 \
      --out-csv analysis/worker_sweep_report.csv \
      --out-png analysis/worker_sweep_report.png
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Client output looks like: "Results: <score> <latency>".
RESULTS_RE = re.compile(r"Results:\s*([-+]?\d*\.?\d+)\s+(\d+)")

# Default VM addresses from the Vagrant setup.
SERVER_IP = "192.168.101.10"
REMOTE_COMMON = "/home/vagrant/os-challenge-common"
REMOTE_SCRIPTS = REMOTE_COMMON + "/analysis/remote"


def run_local(cmd, cwd):
    # Run a command on the host.
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def vagrant_ssh(vagrant_dir, machine, remote_cmd):
    """Run one command on a VM over SSH."""
    cmd = ["vagrant", "ssh", machine, "-c", remote_cmd]
    return run_local(cmd, cwd=vagrant_dir)


def remote_bin_path(vagrant_dir, machine):
    # Ask the VM which binary dir to use.
    proc = vagrant_ssh(vagrant_dir, machine,
                       f"cd {REMOTE_COMMON} && ./get-bin-path.sh")
    if proc.returncode != 0:
        sys.exit(f"Could not resolve bin path on {machine}:\n{proc.stderr}")
    return proc.stdout.strip()


def build_server(vagrant_dir, workers, disable_cache=False):
    """Rebuild the server with a fixed worker count via a remote helper script.

    When disable_cache is set the server is built with -DDISABLE_CACHE so the
    repeat-cache is bypassed and every request is solved from scratch. That keeps
    cache hits from masking solve time in the worker-count study.
    """
    extra = "-DDISABLE_CACHE" if disable_cache else ""
    proc = vagrant_ssh(
        vagrant_dir, "server",
        f"sh {REMOTE_SCRIPTS}/srv_build.sh {REMOTE_COMMON} {workers} {extra}")
    if "BUILD_OK" not in proc.stdout:
        sys.exit(f"Server build failed for WORKER_COUNT={workers}:\n"
                 f"{proc.stdout}\n{proc.stderr}")


def start_server(vagrant_dir, port):
    """Start the server fully detached and return its PID.

    The remote helper kills any stale server, launches the new one with setsid so
    it survives the SSH session ending, and waits until the port is listening.
    That also guarantees the cache is freshly initialised for each run.
    """
    proc = vagrant_ssh(vagrant_dir, "server",
                       f"sh {REMOTE_SCRIPTS}/srv_start.sh {REMOTE_COMMON} {port}")
    pid = None
    for line in proc.stdout.splitlines():
        if line.startswith("PID="):
            pid = line[len("PID="):].strip()
    if "LISTENING" not in proc.stdout or not pid or not pid.isdigit():
        sys.exit(f"Server did not start listening on port {port}:\n"
                 f"{proc.stdout}\n{proc.stderr}")
    return pid


def stop_server(vagrant_dir, pid, port):
    """Stop the server and confirm the port is free before returning.

    The remote helper escalates from SIGTERM to SIGKILL, adds a pkill backstop,
    and polls until the port is free. If it cannot free the port the whole run is
    aborted so the benchmark never measures a stale, cache-warmed server.
    """
    proc = vagrant_ssh(vagrant_dir, "server",
                       f"sh {REMOTE_SCRIPTS}/srv_stop.sh {port} {pid}")
    if "PORT_FREE" not in proc.stdout:
        sys.exit(f"Server on port {port} would not stop; aborting so the "
                 f"benchmark does not measure a stale server.\n{proc.stdout}")


def run_client(vagrant_dir, client_bin, args):
    """Run the client once and return the score and latency."""
    client_cmd = (
        f"sh {REMOTE_SCRIPTS}/run_client.sh {client_bin} {SERVER_IP} "
        f"{args.port} {args.seed} {args.total} {args.start} {args.difficulty} "
        f"{args.rep} {args.delay} {args.lambda_}"
    )
    proc = vagrant_ssh(vagrant_dir, "client", client_cmd)
    if proc.returncode != 0:
        print(f"  client error:\n{proc.stderr}", file=sys.stderr)
        return None
    match = RESULTS_RE.search(proc.stdout)
    if not match:
        print(f"  no Results line in client output:\n{proc.stdout}", file=sys.stderr)
        return None
    return float(match.group(1)), int(match.group(2))


def calibrate(vagrant_dir, client_bin, args):
    """Do one quick check to see if the workload is heavy enough."""
    print("Calibration run (WORKER_COUNT=1) ...")
    build_server(vagrant_dir, 1, args.disable_cache)
    pid = start_server(vagrant_dir, args.port)
    time.sleep(args.warmup_sleep)
    result = run_client(vagrant_dir, client_bin, args)
    stop_server(vagrant_dir, pid, args.port)
    if result is None:
        sys.exit("Calibration run produced no score; fix the setup before sweeping.")
    score, latency = result
    per_request = latency / max(args.total, 1)
    print(f"  score={score:.2f}  total_latency={latency}  "
          f"per_request_latency~={per_request:.0f} us  "
          f"(request delay is {args.delay} us)")
    if per_request < args.delay:
        print("  note: per-request latency is below the request delay, so a "
              "single worker may already keep up. Consider raising --difficulty.")
    print()


def sweep(vagrant_dir, client_bin, args):
    # Run the full sweep and collect all results.
    rows = []
    for workers in args.worker_list:
        print(f"WORKER_COUNT={workers}: building ...")
        build_server(vagrant_dir, workers, args.disable_cache)

        reps = args.reps + (1 if args.warmup else 0)
        for rep in range(reps):
            is_warmup = args.warmup and rep == 0
            pid = start_server(vagrant_dir, args.port)
            time.sleep(args.warmup_sleep)
            result = run_client(vagrant_dir, client_bin, args)
            stop_server(vagrant_dir, pid, args.port)

            if result is None:
                print(f"  rep {rep}: failed, skipping")
                continue
            score, latency = result
            if is_warmup:
                print(f"  warmup: score={score:.2f} (discarded)")
                continue

            print(f"  rep {rep if not args.warmup else rep - 1}: "
                  f"score={score:.2f} latency={latency}")
            rows.append({
                "worker_count": workers,
                "rep": rep if not args.warmup else rep - 1,
                "score": score,
                "total_latency": latency,
                "seed": args.seed,
                "total": args.total,
                "start": args.start,
                "difficulty": args.difficulty,
                "rep_prob": args.rep,
                "delay": args.delay,
                "lambda": args.lambda_,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
    return rows


def write_csv(rows, path):
    if not rows:
        sys.exit("No successful runs were recorded, so there is nothing to write.")
    fields = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print("Saved results:", path)


def aggregate(rows):
    # Group total latency by worker count and compute mean/std in milliseconds.
    by_count = {}
    for r in rows:
        by_count.setdefault(r["worker_count"], []).append(r["total_latency"] / 1000.0)
    counts = sorted(by_count)
    means = np.array([np.mean(by_count[c]) for c in counts])
    stds = np.array([np.std(by_count[c]) for c in counts])
    return np.array(counts, dtype=float), means, stds, by_count


def make_plot(rows, args):
    counts, means, stds, by_count = aggregate(rows)

    # Per-repetition points, in milliseconds.
    all_x = np.array([r["worker_count"] for r in rows], dtype=float)
    all_y = np.array([r["total_latency"] / 1000.0 for r in rows], dtype=float)

    # Keep the fit degree sane.
    degree = min(args.poly_degree, len(counts) - 1)
    fit_x = np.linspace(counts.min(), counts.max(), 200)
    coeffs = np.polyfit(counts, means, degree)
    fit_y = np.polyval(coeffs, fit_x)

    # Lowest mean latency is the optimum.
    best_idx = int(np.argmin(means))
    best_count = counts[best_idx]
    best_mean = means[best_idx]

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.scatter(all_x, all_y, s=18, alpha=0.35, color="tab:blue",
               label="individual repetitions")
    ax.errorbar(counts, means, yerr=stds, fmt="o-", color="tab:blue", lw=1.5,
                capsize=4, label="mean latency +/- std")
    ax.plot(fit_x, fit_y, color="tab:red", lw=1.8, ls="--",
            label=f"polynomial fit (deg {degree})")
    ax.axvline(best_count, color="black", lw=1.2, ls=":",
               label=f"min mean latency: {best_count:.0f} workers "
                     f"({best_mean:.1f} ms)")

    ax.set_xlabel("worker count (WORKER_COUNT)")
    ax.set_ylabel("total latency (ms)")
    ax.set_xticks(counts)
    cfg = (f"seed={args.seed} total={args.total} difficulty={args.difficulty} "
           f"rep={args.rep} delay={args.delay} lambda={args.lambda_} "
           f"reps={args.reps}")
    ax.set_title("OS-challenge total latency against server worker count\n" + cfg,
                 fontsize=11)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out_png, dpi=130)
    print("Saved plot:", args.out_png)

    print()
    print("Summary (mean +/- std total latency in ms by worker count):")
    for c, m, s in zip(counts, means, stds):
        marker = "  <-- min" if c == best_count else ""
        print(f"  {int(c):>3} workers: {m:10.1f} +/- {s:8.1f}{marker}")


def parse_worker_list(text):
    try:
        values = [int(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("worker list must be comma-separated integers")
    if not values:
        raise argparse.ArgumentTypeError("worker list must not be empty")
    return values


def build_parser():
    p = argparse.ArgumentParser(
        description="Sweep the server worker count and plot the client score. "
                    "The server runs on the server VM and the client on the "
                    "client VM; this script runs on the host.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--vagrant-dir",
                   default=os.path.join(repo_root, "arm64"),
                   help="Directory that holds the Vagrantfile for the VMs.")
    p.add_argument("--workers", dest="worker_list", type=parse_worker_list,
                   default=[1, 2, 3, 4, 6, 8, 12, 16],
                   help="Comma-separated worker counts to test.")
    p.add_argument("--reps", type=int, default=10,
                   help="Repetitions per worker count.")
    p.add_argument("--warmup", action="store_true", default=True,
                   help="Run and discard one warm-up rep per worker count.")
    p.add_argument("--no-warmup", dest="warmup", action="store_false",
                   help="Disable the warm-up rep.")
    p.add_argument("--warmup-sleep", type=float, default=0.5,
                   help="Seconds to wait after starting the server before the "
                        "client connects.")
    p.add_argument("--no-calibrate", dest="calibrate", action="store_false",
                   default=True, help="Skip the calibration run.")
    p.add_argument("--disable-cache", dest="disable_cache", action="store_true",
                   default=True,
                   help="Build the server with -DDISABLE_CACHE so the repeat "
                        "cache does not mask solve time (default).")
    p.add_argument("--keep-cache", dest="disable_cache", action="store_false",
                   help="Build with the repeat cache enabled.")

    # Workload settings.
    p.add_argument("--port", type=int, default=5003)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--total", type=int, default=100)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--difficulty", type=int, default=1_000_000)
    p.add_argument("--rep", type=int, default=20,
                   help="Repetition probability in percent (exercises the cache).")
    p.add_argument("--delay", type=int, default=50_000,
                   help="Delay between requests in microseconds.")
    p.add_argument("--lambda", dest="lambda_", type=float, default=1.5,
                   help="Priority rate (exercises the sorted queue).")

    # Plot and output settings.
    p.add_argument("--poly-degree", type=int, default=2,
                   help="Degree of the numpy polynomial regression.")
    p.add_argument("--client-bin", default=None,
                   help="Client binary path on the client VM. Resolved from "
                        "get-bin-path.sh when not set.")
    p.add_argument("--out-csv", default=os.path.join(repo_root, "analysis",
                                                     "worker_sweep.csv"))
    p.add_argument("--out-png", default=os.path.join(repo_root, "analysis",
                                                     "worker_sweep.png"))
    return p


def main():
    args = build_parser().parse_args()

    if args.client_bin:
        client_bin = args.client_bin
    else:
        bin_rel = remote_bin_path(args.vagrant_dir, "client")
        client_bin = f"{REMOTE_COMMON}/{bin_rel}/client"
    print("Client binary on client VM:", client_bin)
    print("Worker counts:", args.worker_list, "reps:", args.reps)
    print()

    if args.calibrate:
        calibrate(args.vagrant_dir, client_bin, args)

    rows = sweep(args.vagrant_dir, client_bin, args)
    write_csv(rows, args.out_csv)
    make_plot(rows, args)


if __name__ == "__main__":
    main()

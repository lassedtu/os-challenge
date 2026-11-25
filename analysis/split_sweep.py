#!/usr/bin/env python3
"""
Sweep the shape of the master/slave worker pool and record the client score.

Each configuration has the form "MxG":
    M = number of master workers (MASTER_COUNT).
    G = number of threads in each group (GROUP_SIZE), the master included.
The server uses M * G threads in total. One request is split into G slices.

The configuration "2x1" is the same as the best result of the worker-count
sweep (2 workers, no splitting). Use it as the baseline.

Example:
    python3 analysis/split_sweep.py \
      --configs 2x1,1x2,1x4,1x8,1x16,2x2,2x4,2x8,4x4,8x2,16x1 \
      --reps 10 \
      --seed 5041 \
      --total 500 \
      --difficulty 3000000 \
      --delay 50000 \
      --rep 20 \
      --lambda 1.5 \
      --out-csv analysis/split_sweep_report.csv \
      --out-png analysis/split_sweep_report.png
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

# Configuration that is the same as the optimum of the worker-count sweep.
BASELINE = (2, 1)


def run_local(cmd, cwd):
    # Run a command on the host.
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def vagrant_ssh(vagrant_dir, machine, remote_cmd):
    """Run one command on a VM over SSH."""
    cmd = ["vagrant", "ssh", machine, "-c", remote_cmd]
    return run_local(cmd, cwd=vagrant_dir)


def remote_bin_path(vagrant_dir, machine):
    # Ask the VM which binary directory to use.
    proc = vagrant_ssh(vagrant_dir, machine,
                       f"cd {REMOTE_COMMON} && ./get-bin-path.sh")
    if proc.returncode != 0:
        sys.exit(f"Could not get the bin path on {machine}:\n{proc.stderr}")
    return proc.stdout.strip()


def build_server(vagrant_dir, masters, group_size, disable_cache=False):
    """Rebuild the server with a fixed pool shape. Use the remote helper script.

    The helper sets MASTER_COUNT=masters and WORKERS_TOTAL=masters*group_size.
    When disable_cache is set, the server is built with -DDISABLE_CACHE. Then the
    repeat-cache is not used, and the server solves each request from the start.
    This prevents cache hits from hiding the search time.
    """
    extra = "-DDISABLE_CACHE" if disable_cache else ""
    proc = vagrant_ssh(
        vagrant_dir, "server",
        f"sh {REMOTE_SCRIPTS}/srv_build_split.sh {REMOTE_COMMON} "
        f"{masters} {group_size} {extra}")
    if "BUILD_OK" not in proc.stdout:
        sys.exit(f"Server build failed for {masters}x{group_size}:\n"
                 f"{proc.stdout}\n{proc.stderr}")


def start_server(vagrant_dir, port):
    """Start the server as a detached process and return its PID.

    The remote helper stops all old servers. It starts the new server with
    setsid, so the server continues after the SSH session stops. It then waits
    until the port listens. Thus each run starts with an empty cache.
    """
    proc = vagrant_ssh(vagrant_dir, "server",
                       f"sh {REMOTE_SCRIPTS}/srv_start.sh {REMOTE_COMMON} {port}")
    pid = None
    for line in proc.stdout.splitlines():
        if line.startswith("PID="):
            pid = line[len("PID="):].strip()
    if "LISTENING" not in proc.stdout or not pid or not pid.isdigit():
        sys.exit(f"Server did not start to listen on port {port}:\n"
                 f"{proc.stdout}\n{proc.stderr}")
    return pid


def stop_server(vagrant_dir, pid, port):
    """Stop the server. Make sure that the port is free before the next run.

    The remote helper sends SIGTERM first and SIGKILL after. If the port does
    not become free, this script stops the full sweep. This prevents a
    measurement on an old server that has a full cache.
    """
    proc = vagrant_ssh(vagrant_dir, "server",
                       f"sh {REMOTE_SCRIPTS}/srv_stop.sh {port} {pid}")
    if "PORT_FREE" not in proc.stdout:
        sys.exit(f"Server on port {port} did not stop. The sweep stops, so "
                 f"that no measurement uses an old server.\n{proc.stdout}")


def run_client(vagrant_dir, client_bin, args):
    """Run the client one time. Return the score and the total latency."""
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


def sweep(vagrant_dir, client_bin, args):
    # Run the full sweep and collect all results.
    rows = []
    for masters, group_size in args.configs:
        label = f"{masters}x{group_size}"
        print(f"{label} ({masters * group_size} threads): building ...")
        build_server(vagrant_dir, masters, group_size, args.disable_cache)

        reps = args.reps + (1 if args.warmup else 0)
        for rep in range(reps):
            is_warmup = args.warmup and rep == 0
            pid = start_server(vagrant_dir, args.port)
            time.sleep(args.warmup_sleep)
            result = run_client(vagrant_dir, client_bin, args)
            stop_server(vagrant_dir, pid, args.port)

            if result is None:
                print(f"  rep {rep}: failed, skipped")
                continue
            score, latency = result
            if is_warmup:
                print(f"  warmup: score={score:.2f} (not recorded)")
                continue

            rep_index = rep - 1 if args.warmup else rep
            print(f"  rep {rep_index}: score={score:.2f} latency={latency}")
            rows.append({
                "config": label,
                "master_count": masters,
                "group_size": group_size,
                "threads_total": masters * group_size,
                "rep": rep_index,
                "score": score,
                "total_latency": latency,
                "seed": args.seed,
                "total": args.total,
                "start": args.start,
                "difficulty": args.difficulty,
                "rep_prob": args.rep,
                "delay": args.delay,
                "lambda": args.lambda_,
                "cache_disabled": int(args.disable_cache),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
    return rows


def write_csv(rows, path):
    if not rows:
        sys.exit("No run was successful. There is no data to write.")
    fields = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print("Saved results:", path)


def aggregate(rows):
    """Group the total latency by configuration. Calculate mean and std in ms.

    Return one dict for each configuration, in the order of the sweep.
    """
    by_config = {}
    for r in rows:
        key = (r["master_count"], r["group_size"])
        by_config.setdefault(key, []).append(r["total_latency"] / 1000.0)
    stats = []
    for key, values in by_config.items():
        stats.append({
            "masters": key[0],
            "group_size": key[1],
            "label": f"{key[0]}x{key[1]}",
            "values": values,
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
        })
    return stats


def make_plot(rows, args):
    stats = aggregate(rows)

    # Sort by number of threads, then by group size. This keeps equal thread counts together.
    stats.sort(key=lambda s: (s["masters"] * s["group_size"], s["group_size"]))

    labels = [s["label"] for s in stats]
    means = np.array([s["mean"] for s in stats])
    stds = np.array([s["std"] for s in stats])
    x = np.arange(len(stats))

    best = stats[int(np.argmin(means))]
    baseline = next((s for s in stats
                     if (s["masters"], s["group_size"]) == BASELINE), None)

    fig, (ax_lat, ax_speed) = plt.subplots(1, 2, figsize=(14, 6))

    # Left plot: total latency for each configuration.
    for i, s in enumerate(stats):
        ax_lat.scatter(np.full(len(s["values"]), i), s["values"], s=18,
                       alpha=0.35, color="tab:blue")
    ax_lat.errorbar(x, means, yerr=stds, fmt="o", color="tab:blue", capsize=4,
                    label="mean latency +/- std")
    if baseline is not None:
        ax_lat.axhline(baseline["mean"], color="tab:red", lw=1.2, ls="--",
                       label=f"baseline {baseline['label']} "
                             f"({baseline['mean']:.1f} ms)")
    ax_lat.set_xticks(x)
    ax_lat.set_xticklabels(labels, rotation=45)
    ax_lat.set_xlabel("pool shape (MASTER_COUNT x GROUP_SIZE)")
    ax_lat.set_ylabel("total latency (ms)")
    ax_lat.set_title(f"Total latency (min: {best['label']}, "
                     f"{best['mean']:.1f} ms)", fontsize=11)
    ax_lat.legend()
    ax_lat.grid(True, alpha=0.3)

    # Right plot: speed-up against the baseline, one line for each master count.
    # The dotted line shows the ideal speed-up if the split had no overhead.
    if baseline is not None:
        for masters in sorted({s["masters"] for s in stats}):
            line = sorted((s for s in stats if s["masters"] == masters),
                          key=lambda s: s["group_size"])
            gx = [s["group_size"] for s in line]
            gy = [baseline["mean"] / s["mean"] for s in line]
            ax_speed.plot(gx, gy, "o-", label=f"MASTER_COUNT={masters}")
        sizes = sorted({s["group_size"] for s in stats})
        ax_speed.plot(sizes, sizes, color="black", lw=1, ls=":",
                      label="ideal (speed-up = GROUP_SIZE)")
        ax_speed.set_xscale("log", base=2)
        ax_speed.set_xticks(sizes)
        ax_speed.set_xticklabels([str(s) for s in sizes])
        ax_speed.set_xlabel("threads for each request (GROUP_SIZE)")
        ax_speed.set_ylabel(f"speed-up against {baseline['label']}")
        ax_speed.legend()
        ax_speed.grid(True, alpha=0.3)
    else:
        ax_speed.text(0.5, 0.5, "baseline 2x1 not in sweep",
                      ha="center", va="center", transform=ax_speed.transAxes)
    ax_speed.set_title("Speed-up from request splitting", fontsize=11)

    cfg = (f"seed={args.seed} total={args.total} difficulty={args.difficulty} "
           f"rep={args.rep} delay={args.delay} lambda={args.lambda_} "
           f"reps={args.reps} cache={'off' if args.disable_cache else 'on'}")
    fig.suptitle("OS-challenge request splitting between workers\n" + cfg,
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(args.out_png, dpi=130)
    print("Saved plot:", args.out_png)

    print()
    print("Summary (mean +/- std total latency in ms for each configuration):")
    for s in stats:
        marker = "  <-- min" if s is best else ""
        speed = ""
        if baseline is not None:
            speed = f"  speed-up {baseline['mean'] / s['mean']:5.2f}x"
        print(f"  {s['label']:>5} ({s['masters'] * s['group_size']:>2} threads): "
              f"{s['mean']:10.1f} +/- {s['std']:8.1f}{speed}{marker}")


def parse_configs(text):
    """Parse a list such as "2x1,1x4,2x8" into [(2, 1), (1, 4), (2, 8)]."""
    configs = []
    for item in text.split(","):
        item = item.strip().lower()
        if not item:
            continue
        try:
            masters, group_size = (int(v) for v in item.split("x"))
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"configuration '{item}' must have the form MxG, for example 2x8")
        if masters < 1 or group_size < 1:
            raise argparse.ArgumentTypeError(
                f"configuration '{item}' must have values of 1 or more")
        configs.append((masters, group_size))
    if not configs:
        raise argparse.ArgumentTypeError("the configuration list must not be empty")
    return configs


def build_parser():
    p = argparse.ArgumentParser(
        description="Sweep the master/slave pool shape and plot the client "
                    "score. The server runs on the server VM and the client "
                    "runs on the client VM. This script runs on the host.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--vagrant-dir",
                   default=os.path.join(repo_root, "arm64"),
                   help="Directory that contains the Vagrantfile for the VMs.")
    p.add_argument("--configs", type=parse_configs,
                   default=parse_configs(
                       "2x1,1x2,1x4,1x8,1x16,2x2,2x4,2x8,4x4,8x2,16x1"),
                   help="Comma-separated pool shapes (MxG) to test.")
    p.add_argument("--reps", type=int, default=10,
                   help="Repetitions for each configuration.")
    p.add_argument("--warmup", action="store_true", default=True,
                   help="Run one warm-up rep for each configuration and do not record it.")
    p.add_argument("--no-warmup", dest="warmup", action="store_false",
                   help="Do not run the warm-up rep.")
    p.add_argument("--warmup-sleep", type=float, default=0.5,
                   help="Seconds to wait after the server starts and before "
                        "the client connects.")
    p.add_argument("--disable-cache", dest="disable_cache", action="store_true",
                   default=True,
                   help="Build the server with -DDISABLE_CACHE, so that the "
                        "repeat-cache does not hide the search time (default).")
    p.add_argument("--keep-cache", dest="disable_cache", action="store_false",
                   help="Build the server with the repeat-cache.")

    # Workload settings. The defaults are the same as in the worker-count sweep (section 2.2).
    p.add_argument("--port", type=int, default=5003)
    p.add_argument("--seed", type=int, default=5041)
    p.add_argument("--total", type=int, default=500)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--difficulty", type=int, default=3_000_000)
    p.add_argument("--rep", type=int, default=20,
                   help="Repetition probability in percent.")
    p.add_argument("--delay", type=int, default=50_000,
                   help="Delay between requests in microseconds.")
    p.add_argument("--lambda", dest="lambda_", type=float, default=1.5,
                   help="Priority rate.")

    # Output settings.
    p.add_argument("--client-bin", default=None,
                   help="Path of the client binary on the client VM. If not "
                        "set, get-bin-path.sh gives the path.")
    p.add_argument("--out-csv", default=os.path.join(repo_root, "analysis",
                                                     "split_sweep_report.csv"))
    p.add_argument("--out-png", default=os.path.join(repo_root, "analysis",
                                                     "split_sweep_report.png"))
    return p


def main():
    args = build_parser().parse_args()

    if args.client_bin:
        client_bin = args.client_bin
    else:
        bin_rel = remote_bin_path(args.vagrant_dir, "client")
        client_bin = f"{REMOTE_COMMON}/{bin_rel}/client"
    print("Client binary on client VM:", client_bin)
    print("Configurations:", [f"{m}x{g}" for m, g in args.configs],
          "reps:", args.reps)
    print()

    rows = sweep(args.vagrant_dir, client_bin, args)
    write_csv(rows, args.out_csv)
    make_plot(rows, args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Compare the original server with the server that counts the CPUs at runtime.

Both servers use the same pool shape on the 4-CPU server VM (2 masters with
2 threads each). The only difference is how the shape is set:
    original  WORKERS_TOTAL and MASTER_COUNT are fixed in worker_pool.h
              (the code at --baseline-ref, default individual-server-setup-lasse).
    runtime   The server counts the CPUs when it starts (the code on this branch).

The script copies the original code into analysis/build_original/ with
"git archive". The server VM sees this directory through the shared folder, so
it can build and start both servers. The script builds each server one time.
Then it runs the client against the two servers in turns (original, runtime,
runtime, original, ...), so that a slow change on the VMs has the same effect
on both servers.

The workload is small, so that a full test takes a few minutes. Each run
starts a new server, thus the repeat-cache is empty at the start of each run.

Example:
    python3 analysis/core_count_test.py --reps 10
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# The last line of the client output is "Results: <reliability> <score>".
#   reliability = percentage of correct answers (for example 100.00).
#   score = priority-weighted average latency in microseconds (lower is better).
RESULTS_RE = re.compile(r"Results:\s*(\d+(?:\.\d+)?)\s+(\d+)")
# Line that the runtime server writes to stderr when it starts, for example:
# "worker_pool: threads=4 (counted at runtime, 1625 ns) masters=2 group_sizes=2,2"
POOL_RE = re.compile(r"worker_pool: threads=(\d+) \(([^,]+), (\d+) ns\) "
                     r"masters=(\d+) group_sizes=([\d,]+)")

# Default VM addresses from the Vagrant setup.
SERVER_IP = "192.168.101.10"
REMOTE_COMMON = "/home/vagrant/os-challenge-common"
REMOTE_SCRIPTS = REMOTE_COMMON + "/analysis/remote"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL_DIR = os.path.join("analysis", "build_original")

# (label, build directory relative to the repository root)
VARIANTS = [("original", ORIGINAL_DIR), ("runtime", ".")]


def run_local(cmd, cwd):
    # Run a command on the host.
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def vagrant_ssh(vagrant_dir, machine, remote_cmd):
    """Run one command on a VM over SSH."""
    return run_local(["vagrant", "ssh", machine, "-c", remote_cmd], cwd=vagrant_dir)


def remote_dir(rel_dir):
    # Path of a repository directory on the VMs.
    return REMOTE_COMMON if rel_dir == "." else f"{REMOTE_COMMON}/{rel_dir}"


def remote_bin_path(vagrant_dir, machine):
    # Ask the VM which binary directory to use.
    proc = vagrant_ssh(vagrant_dir, machine, f"cd {REMOTE_COMMON} && ./get-bin-path.sh")
    if proc.returncode != 0:
        sys.exit(f"Could not get the bin path on {machine}:\n{proc.stderr}")
    return proc.stdout.strip()


def export_original(ref):
    """Copy the Makefile and src/ of the original server into analysis/build_original/.

    Only these files are necessary to build the server. Remove an old copy first,
    so that no file from an earlier test stays.
    """
    target = os.path.join(REPO_ROOT, ORIGINAL_DIR)
    shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target)
    archive = subprocess.run(["git", "archive", ref, "Makefile", "src"],
                             cwd=REPO_ROOT, capture_output=True)
    if archive.returncode != 0:
        sys.exit(f"git archive failed for {ref}:\n{archive.stderr.decode()}")
    untar = subprocess.run(["tar", "-x", "-C", target], input=archive.stdout,
                           capture_output=True)
    if untar.returncode != 0:
        sys.exit(f"Could not extract the original code:\n{untar.stderr.decode()}")
    commit = run_local(["git", "rev-parse", "--short", ref], cwd=REPO_ROOT).stdout.strip()
    return commit


def build_server(vagrant_dir, label, rel_dir):
    """Build one server on the server VM with the normal build flags."""
    proc = vagrant_ssh(vagrant_dir, "server",
                       f"sh {REMOTE_SCRIPTS}/srv_build_dir.sh {remote_dir(rel_dir)}")
    if "BUILD_OK" not in proc.stdout:
        sys.exit(f"Server build failed for {label}:\n{proc.stdout}\n{proc.stderr}")


def start_server(vagrant_dir, rel_dir, port):
    """Start the server in rel_dir as a detached process.

    Return the PID and the worker_pool line from the server log (None for the
    original server, which does not write this line).
    """
    proc = vagrant_ssh(vagrant_dir, "server",
                       f"sh {REMOTE_SCRIPTS}/srv_start.sh {remote_dir(rel_dir)} {port}")
    pid = None
    for line in proc.stdout.splitlines():
        if line.startswith("PID="):
            pid = line[len("PID="):].strip()
    if "LISTENING" not in proc.stdout or not pid or not pid.isdigit():
        sys.exit(f"Server did not start to listen on port {port}:\n"
                 f"{proc.stdout}\n{proc.stderr}")
    log = vagrant_ssh(vagrant_dir, "server", "cat /tmp/server.log").stdout
    match = POOL_RE.search(log)
    return pid, match


def stop_server(vagrant_dir, pid, port):
    """Stop the server. Make sure that the port is free before the next run."""
    proc = vagrant_ssh(vagrant_dir, "server", f"sh {REMOTE_SCRIPTS}/srv_stop.sh {port} {pid}")
    if "PORT_FREE" not in proc.stdout:
        sys.exit(f"Server on port {port} did not stop.\n{proc.stdout}")


def run_client(vagrant_dir, client_bin, args):
    """Run the client one time. Return (reliability, score in us), or None on failure."""
    client_cmd = (
        f"sh {REMOTE_SCRIPTS}/run_client.sh {client_bin} {SERVER_IP} "
        f"{args.port} {args.seed} {args.total} {args.start} {args.difficulty} "
        f"{args.rep} {args.delay} {args.lambda_}"
    )
    proc = vagrant_ssh(vagrant_dir, "client", client_cmd)
    if proc.returncode != 0:
        print(f"  client error:\n{proc.stdout[-500:]}\n{proc.stderr}", file=sys.stderr)
        return None
    match = RESULTS_RE.search(proc.stdout)
    if not match:
        print(f"  no Results line in client output:\n{proc.stdout[-500:]}", file=sys.stderr)
        return None
    return float(match.group(1)), int(match.group(2))


def run_order(rep):
    # Change the order in each rep: original first in even reps, runtime first in odd reps.
    return VARIANTS if rep % 2 == 0 else list(reversed(VARIANTS))


def run_test(vagrant_dir, client_bin, args, commit):
    # Run all reps and collect the results.
    rows = []
    total_reps = args.reps + (1 if args.warmup else 0)
    for rep in range(total_reps):
        is_warmup = args.warmup and rep == 0
        rep_index = rep - 1 if args.warmup else rep
        for label, rel_dir in run_order(rep):
            pid, pool = start_server(vagrant_dir, rel_dir, args.port)
            time.sleep(args.warmup_sleep)
            result = run_client(vagrant_dir, client_bin, args)
            stop_server(vagrant_dir, pid, args.port)

            pool_text = (f"threads={pool.group(1)} masters={pool.group(4)} "
                         f"groups={pool.group(5)} count={pool.group(3)} ns"
                         if pool else "fixed shape")
            if result is None:
                print(f"  {label:>8} rep {rep_index}: failed, skipped")
                continue
            reliability, score = result
            if is_warmup:
                print(f"  {label:>8} warmup: score={score} us ({pool_text}, not recorded)")
                continue
            print(f"  {label:>8} rep {rep_index}: score={score} us "
                  f"reliability={reliability} ({pool_text})")
            if label == "runtime" and pool is None:
                sys.exit("The runtime server did not write the worker_pool line. "
                         "Make sure that this branch is checked out.")
            rows.append({
                "variant": label,
                "rep": rep_index,
                "reliability": reliability,
                "score_us": score,
                "threads": pool.group(1) if pool else "",
                "masters": pool.group(4) if pool else "",
                "group_sizes": pool.group(5) if pool else "",
                "cpu_count_ns": pool.group(3) if pool else "",
                "baseline_commit": commit,
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
        sys.exit("No run was successful. There is no data to write.")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("Saved results:", path)


def make_plot(rows, args, commit):
    labels = {"original": f"original\n(fixed 2x2, {commit})",
              "runtime": "runtime\n(CPUs counted at start)"}
    colors = {"original": "tab:blue", "runtime": "tab:orange"}
    stats = {}
    for label, _ in VARIANTS:
        values = np.array([r["score_us"] / 1000.0 for r in rows if r["variant"] == label])
        stats[label] = (values, float(np.mean(values)), float(np.std(values)))

    fig, ax = plt.subplots(figsize=(7, 6))
    for i, (label, _) in enumerate(VARIANTS):
        values, mean, std = stats[label]
        ax.bar(i, mean, yerr=std, capsize=8, width=0.6, color=colors[label],
               alpha=0.75, label=f"{label}: {mean:.2f} +/- {std:.2f} ms")
        ax.scatter(np.full(len(values), i), values, s=18, color="black", alpha=0.5, zorder=3)
    ax.set_xticks(range(len(VARIANTS)))
    ax.set_xticklabels([labels[label] for label, _ in VARIANTS])
    ax.set_ylabel("score: priority-weighted average latency (ms)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="lower right")

    base = stats["original"][1]
    new = stats["runtime"][1]
    diff = (new - base) / base * 100.0
    count_ns = [int(r["cpu_count_ns"]) for r in rows if r["variant"] == "runtime"]
    ax.set_title(f"Difference runtime vs. original: {diff:+.2f} %\n"
                 f"CPU count at start-up: mean {np.mean(count_ns) / 1000.0:.1f} us (one time)",
                 fontsize=11)

    cfg = (f"seed={args.seed} total={args.total} difficulty={args.difficulty} "
           f"rep={args.rep} delay={args.delay} lambda={args.lambda_} reps={args.reps}")
    fig.suptitle("OS-challenge: CPU count at runtime against fixed pool shape\n" + cfg,
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(args.out_png, dpi=130)
    print("Saved plot:", args.out_png)

    # Print the values for the report.
    print()
    print("Summary (score in ms, lower is better):")
    for label, _ in VARIANTS:
        values, mean, std = stats[label]
        print(f"  {label:>8}: mean {mean:8.2f}  std {std:7.2f}  "
              f"min {values.min():8.2f}  max {values.max():8.2f}  runs {len(values)}")
    print(f"  difference runtime vs. original: {new - base:+.2f} ms ({diff:+.2f} %)")
    print(f"  CPU count at start-up: mean {np.mean(count_ns):.0f} ns, "
          f"max {np.max(count_ns)} ns")
    shapes = {(r["threads"], r["group_sizes"]) for r in rows if r["variant"] == "runtime"}
    print(f"  runtime shapes seen (threads, group sizes): {sorted(shapes)}")


def build_parser():
    p = argparse.ArgumentParser(
        description="Compare the original server (fixed pool shape) with the "
                    "server that counts the CPUs at runtime. The server runs "
                    "on the server VM and the client runs on the client VM. "
                    "This script runs on the host.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--vagrant-dir", default=os.path.join(REPO_ROOT, "arm64"),
                   help="Directory that contains the Vagrantfile for the VMs.")
    p.add_argument("--baseline-ref", default="individual-server-setup-lasse",
                   help="Git branch or commit of the original server.")
    p.add_argument("--reps", type=int, default=10,
                   help="Repetitions for each server.")
    p.add_argument("--warmup", action="store_true", default=True,
                   help="Run one warm-up rep for each server and do not record it.")
    p.add_argument("--no-warmup", dest="warmup", action="store_false",
                   help="Do not run the warm-up rep.")
    p.add_argument("--warmup-sleep", type=float, default=0.5,
                   help="Seconds to wait after the server starts and before "
                        "the client connects.")

    # Workload settings. Same seed and priority rate as run-client-test.sh, but
    # a lower difficulty and a shorter delay, so that a run takes about 10 s.
    p.add_argument("--port", type=int, default=5003)
    p.add_argument("--seed", type=int, default=7974)
    p.add_argument("--total", type=int, default=100)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--difficulty", type=int, default=1_000_000)
    p.add_argument("--rep", type=int, default=20,
                   help="Repetition probability in percent.")
    p.add_argument("--delay", type=int, default=100_000,
                   help="Delay between requests in microseconds.")
    p.add_argument("--lambda", dest="lambda_", type=float, default=1.5,
                   help="Priority rate.")

    p.add_argument("--client-bin", default=None,
                   help="Path of the client binary on the client VM. If not "
                        "set, get-bin-path.sh gives the path.")
    p.add_argument("--out-csv", default=os.path.join(REPO_ROOT, "analysis", "core_count_test.csv"))
    p.add_argument("--out-png", default=os.path.join(REPO_ROOT, "analysis", "core_count_test.png"))
    return p


def main():
    args = build_parser().parse_args()

    commit = export_original(args.baseline_ref)
    print(f"Original server: {args.baseline_ref} ({commit}), copied to {ORIGINAL_DIR}/")

    if args.client_bin:
        client_bin = args.client_bin
    else:
        client_bin = f"{REMOTE_COMMON}/{remote_bin_path(args.vagrant_dir, 'client')}/client"
    print("Client binary on client VM:", client_bin)

    for label, rel_dir in VARIANTS:
        print(f"Building {label} ...")
        build_server(args.vagrant_dir, label, rel_dir)
    print()

    rows = run_test(args.vagrant_dir, client_bin, args, commit)
    write_csv(rows, args.out_csv)
    make_plot(rows, args, commit)


if __name__ == "__main__":
    main()

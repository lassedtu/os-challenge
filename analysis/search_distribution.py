#!/usr/bin/env python3
"""Collect search-depth data from the OS-challenge client.

This script listens to the client traffic, records each request range, and
plots how far the server searches before it finds the answer. It is only for
analysis and plotting; it does not perform the reverse-hash work itself.

Each request gives a range [start, end) and the true answer chosen by the
client. The key quantity is the offset:

    offset = answer - start

For a single search, the server touches every value from start up to answer.
Across many requests, this shows how often each relative position in the range
is visited.

The script builds three plots:

1. Relative visit curve: how often each point in the range is searched.
2. Absolute overlap curve: how many intervals cover each part of the value span.
3. Offset histogram: the distribution of answer - start.

Example:
    python3 search_distribution.py --total 10000 --start 0 --difficulty 1000000
"""

import argparse
import bisect
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

# Use a backend that does not need a display.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# These values match the challenge packet format. The request is the hash plus
# start, end, and priority fields, all encoded as big-endian integers.
REQUEST_SIZE = 49
RESPONSE_SIZE = 8
START_OFF = 32
END_OFF = 40
PRIO_OFF = 48


@dataclass
class Record:
    start: int
    end: int
    priority: int
    answer: int          # The true value the client selected.


class Listener:
    """Small TCP listener used to capture the client requests.

    The listener accepts connections quickly and hands each one to a worker
    thread. Each worker reads the request packet, saves the range metadata, and
    sends a dummy 8-byte reply so the client can finish its exchange.
    """

    def __init__(self, host, port, workers=64):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(1024)
        self.host, self.port = self.sock.getsockname()
        self.requests = []              # Each item is (start, end, priority).
        self._lock = threading.Lock()   # It protects the requests list.
        self._stop = threading.Event()
        self._pool = ThreadPoolExecutor(max_workers=workers)
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)

    def start(self):
        self._accept_thread.start()

    def _accept_loop(self):
        # Keep the accept loop short so the listener can stay responsive under
        # heavy request bursts.
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self._pool.submit(self._handle, conn)

    def _handle(self, conn):
        # Read one complete request and return a dummy value so the client keeps
        # going.
        try:
            buf = b""
            while len(buf) < REQUEST_SIZE:
                chunk = conn.recv(REQUEST_SIZE - len(buf))
                if not chunk:
                    break
                buf += chunk
            if len(buf) == REQUEST_SIZE:
                start = struct.unpack_from(">Q", buf, START_OFF)[0]
                end = struct.unpack_from(">Q", buf, END_OFF)[0]
                prio = buf[PRIO_OFF]
                with self._lock:
                    self.requests.append((start, end, prio))
                conn.sendall(struct.pack(">Q", start))
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self._stop.set()
        self._pool.shutdown(wait=False)
        try:
            self.sock.close()
        except OSError:
            pass


def detect_client_path(repo_root, explicit):
    # If the caller gives an explicit path, trust it.
    if explicit:
        if not os.path.exists(explicit):
            sys.exit(f"Client not found: {explicit}")
        return explicit

    candidates = []
    # First try the path from the repo helper script. This can still be wrong on
    # Apple Silicon under Rosetta, where uname may say x86_64.
    try:
        bin_rel = subprocess.check_output(
            [os.path.join(repo_root, "get-bin-path.sh")], cwd=repo_root
        ).decode().strip()
        candidates.append(os.path.join(repo_root, bin_rel, "client"))
    except (OSError, subprocess.CalledProcessError):
        pass

    # Then check the common architecture and OS locations.
    for arch in ("arm64", "x86_64"):
        for osname in ("macos", "linux"):
            candidates.append(os.path.join(repo_root, arch, "bin", osname, "client"))

    for cand in candidates:
        if os.path.exists(cand):
            return cand

    sys.exit(
        "The client binary was not found. The program looked in:\n  "
        + "\n  ".join(candidates)
        + "\nUse --client-path to set the path."
    )


def parse_client_stdout(text):
    """Read the client output lines.

    Each result line has the form "[%d %llu %llu %u] %llu". The fields are the
    correct flag, the true answer, the server answer, the priority, and the
    latency in microseconds. The function returns a list of
    (correct, true_answer, priority, latency).
    """
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        try:
            inside, latency = line[1:].split("]")
            correct, true_ans, srv_ans, prio = inside.split()
            rows.append((int(correct), int(true_ans), int(prio), int(latency.strip())))
        except (ValueError, IndexError):
            continue
    return rows


def pair_records(parsed, stdout_rows):
    """Match each true answer to the range that contains it.

    The listener handles requests in parallel, so the packets may arrive in a
    different order than the client prints its results. We match by value rather
    than by position: for each answer we find one free range with start <= answer
    < end.
    """
    # Sort the ranges by start so we can find the candidates quickly.
    ranges = sorted(parsed, key=lambda r: r[0])
    starts = [r[0] for r in ranges]
    used = [False] * len(ranges)

    records = []
    unmatched = 0
    for _correct, true_ans, prio_out, _lat in stdout_rows:
        # Pick the latest possible start that still does not exceed the answer,
        # then walk backward until we find a free range covering it.
        hi = bisect.bisect_right(starts, true_ans)
        found = None
        for j in range(hi - 1, -1, -1):
            if used[j]:
                continue
            s, e, _p = ranges[j]
            if e > true_ans:
                found = j
                break
        if found is None:
            unmatched += 1
            continue
        used[found] = True
        s, e, _p = ranges[found]
        records.append(Record(start=s, end=e, priority=prio_out, answer=true_ans))
    return records, unmatched


def collect(args):
    # Start the listener, run the client, and pair the responses back to the
    # original request ranges.
    listener = Listener("127.0.0.1", args.port)
    listener.start()
    time.sleep(0.2)  # Give the listener a moment to start accepting connections.

    client = detect_client_path(args.repo_root, args.client_path)

    # A busy burst with no delay can overwhelm the listener. If the run is large
    # and no delay was requested, add a small pause so the client does not time
    # out while the listener catches up.
    delay = args.delay
    if delay == 0 and args.total > 1000:
        delay = 200
        print(f"Note: total is large and delay is 0, so the program uses "
              f"delay={delay} us to stop client timeouts.")

    cmd = [
        client, "127.0.0.1", str(listener.port),
        str(args.seed), str(args.total), str(args.start),
        str(args.difficulty), str(args.rep), str(delay), str(args.lambda_),
    ]
    print("Running client:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    time.sleep(0.3)  # Give the last connections time to finish.
    listener.close()

    if proc.returncode != 0:
        print("Client stderr:\n", proc.stderr, file=sys.stderr)
        sys.exit(f"The client stopped with code {proc.returncode}")

    stdout_rows = parse_client_stdout(proc.stdout)
    with listener._lock:
        parsed = list(listener.requests)

    if len(parsed) != len(stdout_rows):
        print(
            f"Note: the listener read {len(parsed)} packets and the client "
            f"printed {len(stdout_rows)} lines.",
            file=sys.stderr,
        )

    records, unmatched = pair_records(parsed, stdout_rows)
    if unmatched:
        print(
            f"Note: {unmatched} answers did not match a free range and the "
            f"program dropped them.",
            file=sys.stderr,
        )
    print(f"Collected {len(records)} valid records.")
    if not records:
        sys.exit("There are no valid records, so the program cannot do the analysis.")
    return records


def relative_visits(records, bins):
    """Count how often each relative position in a range is searched.

    For each request the relative depth is (answer - start) / (end - start),
    which falls in [0, 1). A point at position u is visited whenever u <= depth.
    The returned array is the cumulative count of requests whose depth reaches
    each bin center.
    """
    depths = np.array(
        [(r.answer - r.start) / (r.end - r.start) for r in records], dtype=float
    )
    u = (np.arange(bins) + 0.5) / bins          # Bin centers in the unit interval.
    ds = np.sort(depths)
    # The count of depths greater than or equal to u is the total minus the first
    # index at or above u.
    idx = np.searchsorted(ds, u, side="left")
    visits = len(ds) - idx
    return u, visits, depths


def absolute_visit_histogram(records, bins):
    """Count how many intervals overlap each bin in the observed value span.

    Each request contributes the interval [start, answer]. The function uses a
    difference array so it can tally overlaps efficiently even for large 64-bit
    values.
    """
    starts = np.array([r.start for r in records], dtype=np.float64)
    answers = np.array([r.answer for r in records], dtype=np.float64)
    lo = float(starts.min())
    hi = float(answers.max())
    span = hi - lo
    if span <= 0:
        span = 1.0
    width = span / bins

    diff = np.zeros(bins + 1, dtype=np.int64)
    # Map each interval to the bins it starts and ends in.
    b0 = np.clip(((starts - lo) / width).astype(np.int64), 0, bins - 1)
    b1 = np.clip(((answers - lo) / width).astype(np.int64), 0, bins - 1)
    for i0, i1 in zip(b0, b1):
        diff[i0] += 1
        diff[i1 + 1] -= 1
    coverage = np.cumsum(diff[:-1])
    centers = lo + (np.arange(bins) + 0.5) * width
    return centers, coverage, lo, hi


def answer_offset_histogram(records, bins):
    # Histogram of the search depth, which is answer - start.
    offsets = np.array([r.answer - r.start for r in records], dtype=np.float64)
    counts, edges = np.histogram(offsets, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return centers, counts, offsets


def make_plots(records, args):
    # Build the three plots and save the raw data as CSV files.
    u, rel_visits, depths = relative_visits(records, args.bins)
    abs_centers, abs_cov, lo, hi = absolute_visit_histogram(records, args.bins)
    off_centers, off_counts, offsets = answer_offset_histogram(records, args.bins)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Plot 1: relative search depth across the range.
    axes[0].fill_between(u, rel_visits, step="mid", alpha=0.4)
    axes[0].plot(u, rel_visits, lw=1.5)
    axes[0].set_title("Times searched against relative position in range")
    axes[0].set_xlabel("relative position in range (depth u)")
    axes[0].set_ylabel("number of requests that search this point")

    # Plot 2: overlap of search intervals across the observed value span.
    axes[1].fill_between(abs_centers, abs_cov, step="mid", alpha=0.4, color="tab:orange")
    axes[1].plot(abs_centers, abs_cov, lw=1.0, color="tab:orange")
    axes[1].set_title("Search interval overlap over the value space")
    axes[1].set_xlabel("absolute input value (bins)")
    axes[1].set_ylabel("number of search intervals that overlap")
    axes[1].ticklabel_format(axis="x", style="sci", scilimits=(0, 0))

    # Plot 3: distribution of the search depth.
    axes[2].bar(off_centers, off_counts, width=(off_centers[1] - off_centers[0])
                if len(off_centers) > 1 else 1.0, alpha=0.6, color="tab:green")
    axes[2].set_title("Distribution of search depth (answer - start)")
    axes[2].set_xlabel("offset = answer - start")
    axes[2].set_ylabel("count of requests")

    cfg = (f"seed={args.seed} total={args.total} start={args.start} "
           f"difficulty={args.difficulty} rep={args.rep} lambda={args.lambda_} "
           f"| N={len(records)} bins={args.bins}")
    fig.suptitle("OS-challenge search-space visit distribution\n" + cfg, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))

    out_png = args.out_prefix + ".png"
    fig.savefig(out_png, dpi=130)
    print("Saved plot:", out_png)

    # Save the raw records for the report.
    out_csv = args.out_prefix + "_records.csv"
    with open(out_csv, "w") as f:
        f.write("start,end,answer,offset,priority\n")
        for r in records:
            f.write(f"{r.start},{r.end},{r.answer},{r.answer - r.start},{r.priority}\n")
    print("Saved records:", out_csv)

    # Save the binned relative curve for the report.
    out_bins = args.out_prefix + "_binned.csv"
    with open(out_bins, "w") as f:
        f.write("rel_position,rel_visits\n")
        for uu, vv in zip(u, rel_visits):
            f.write(f"{uu:.6f},{int(vv)}\n")
    print("Saved binned relative curve:", out_bins)


def build_parser():
    p = argparse.ArgumentParser(
        description="Collect OS-challenge client data and plot the search-space "
                    "visit distribution. The program does not do reverse hashing.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # These options match ./client hostname port seed total start difficulty rep delay lambda.
    p.add_argument("--seed", type=int, default=1234,
                   help="Seed for the random number generator (0 uses the time).")
    p.add_argument("--total", type=int, default=10000,
                   help="Number of requests to generate.")
    p.add_argument("--start", type=int, default=0,
                   help="Range start (0 makes the start random for each request; "
                        "this is best for the absolute bell-shape view).")
    p.add_argument("--difficulty", type=int, default=1_000_000,
                   help="Range size. The end is start plus difficulty.")
    p.add_argument("--rep", type=int, default=0,
                   help="Repetition probability in percent (0 to 100).")
    p.add_argument("--delay", type=int, default=0,
                   help="Delay between requests in microseconds.")
    p.add_argument("--lambda", dest="lambda_", type=float, default=0,
                   help="Priority rate for the exponential distribution "
                        "(0 turns priorities off).")
    # These options control the analysis and the output.
    p.add_argument("--bins", type=int, default=200,
                   help="Number of bins for the plots.")
    p.add_argument("--port", type=int, default=5099,
                   help="TCP port for the local listener.")
    p.add_argument("--client-path", default=None,
                   help="Path to the client binary. The program finds it if you "
                        "do not set this.")
    p.add_argument("--repo-root", default=os.path.dirname(os.path.dirname(
                       os.path.abspath(__file__))),
                   help="The repository root that holds get-bin-path.sh and the "
                        "bin folders.")
    p.add_argument("--out-prefix", default="search_distribution",
                   help="Prefix for the output files. The program adds .png and "
                        ".csv.")
    return p


def main():
    args = build_parser().parse_args()
    records = collect(args)
    make_plots(records, args)


if __name__ == "__main__":
    main()

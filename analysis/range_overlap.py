import argparse
import csv
import heapq
from pathlib import Path


def load_records(path):
    records = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            records.append((int(row["start"]), int(row["answer"])))
    return records


def dedupe_by_answer(records):
    seen = set()
    distinct = []
    for start, answer in records:
        if answer not in seen:          # keep the first search for each answer
            seen.add(answer)
            distinct.append((start, answer))
    return distinct


def count_overlapping_pairs(intervals):
    intervals = sorted(intervals)       # sort by start
    active_ends, overlap_count = [], 0
    for start, end in intervals:
        while active_ends and active_ends[0] <= start:
            heapq.heappop(active_ends)  # no longer active (half-open ranges)
        overlap_count += len(active_ends)
        heapq.heappush(active_ends, end)
    return overlap_count


def main():
    default_path = Path(__file__).with_name("final_records.csv")
    parser = argparse.ArgumentParser(
        description="Count overlapping search intervals for distinct answers."
    )
    parser.add_argument(
        "records",
        nargs="?",
        type=Path,
        default=default_path,
        help=f"CSV records file (default: {default_path})",
    )
    args = parser.parse_args()

    records = load_records(args.records)
    distinct = dedupe_by_answer(records)
    print(f"{len(records)} total requests, {len(distinct)} distinct answers")
    print(f"genuine overlapping pairs among distinct search intervals: "
          f"{count_overlapping_pairs(distinct)}")


if __name__ == "__main__":
    main()
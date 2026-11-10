"""Audited fixed worker. No dynamic imports, commands, network, or file writes.

Run by absolute file path under isolated Python; it uses only the standard library.
Input is validated by the controller before this process starts.
"""

import json
import statistics
import sys


def main() -> None:
    data = json.load(sys.stdin)
    values = data["values"]
    # statistics.mean avoids overflowing intermediate sums of finite floats.
    print(json.dumps({"mean": float(statistics.mean(values)), "count": len(values)}, allow_nan=False))


if __name__ == "__main__":
    main()

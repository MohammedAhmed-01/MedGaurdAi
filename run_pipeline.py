#!/usr/bin/env python3
"""Entry point for the Egyptian Drug Normalization Pipeline.

Usage
-----
    python run_pipeline.py \\
        --source  /path/to/egyptian-drugs.csv \\
        --output  outputs/ \\
        --config  config/ \\
        [--log-level DEBUG|INFO|WARNING]

The source CSV is never modified.  All outputs are written to --output.
Re-running is safe: existing output files are overwritten, not appended.
"""

import argparse
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Egyptian Drug Normalization Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the raw egyptian-drugs.csv (read-only).",
    )
    parser.add_argument(
        "--output",
        default="outputs",
        help="Directory for all output files.",
    )
    parser.add_argument(
        "--config",
        default="config",
        help="Directory containing mapping CSV files.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    source = Path(args.source)
    if not source.exists():
        print(f"ERROR: source file not found: {source}", file=sys.stderr)
        return 1

    # Import here so import errors surface cleanly
    from src.drug_pipeline.pipeline import run

    output_paths = run(
        source_csv=source,
        output_dir=args.output,
        config_dir=args.config,
        log_level=args.log_level,
    )

    print("\nOutputs written:")
    for name, path in output_paths.items():
        print(f"  {name:40s}  {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

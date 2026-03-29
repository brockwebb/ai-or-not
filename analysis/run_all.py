"""
run_all.py — Run all AI or Not? analysis scripts and generate reports.

Orchestrates the full analysis pipeline: Bayesian difficulty, calibration,
drift detection, and IRT modeling. Generates all plots and summary CSVs
in the specified output directory.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def run_script(script_name: str, args: list[str], cwd: Path) -> bool:
    """Run an analysis script as a subprocess.

    Parameters
    ----------
    script_name : str
        Name of the Python script (e.g., "bayesian_difficulty.py").
    args : list[str]
        Command-line arguments to pass.
    cwd : Path
        Working directory (should be the analysis/ directory).

    Returns
    -------
    bool
        True if the script exited successfully.
    """
    cmd = [sys.executable, str(cwd / script_name)] + args
    logger.info("Running: %s", " ".join(cmd))
    print(f"\n{'=' * 60}")
    print(f"Running {script_name}")
    print(f"{'=' * 60}")

    result = subprocess.run(cmd, cwd=str(cwd))

    if result.returncode != 0:
        logger.error("%s exited with code %d", script_name, result.returncode)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run all AI or Not? analysis scripts"
    )
    parser.add_argument("data", help="Path to JSONL session data file")
    parser.add_argument(
        "--content",
        default="content.json",
        help="Path to content.json (default: content.json)",
    )
    parser.add_argument(
        "--output",
        default="results",
        help="Output directory for all results (default: results/)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=50,
        help="Rolling window for drift detection (default: 50)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Resolve paths
    data_path = str(Path(args.data).resolve())
    content_path = str(Path(args.content).resolve())
    output_path = str(Path(args.output).resolve())
    analysis_dir = Path(__file__).parent.resolve()

    # Create output directory
    Path(output_path).mkdir(parents=True, exist_ok=True)

    # Validate inputs exist
    if not Path(data_path).exists():
        logger.error("Session data file not found: %s", data_path)
        sys.exit(1)
    if not Path(content_path).exists():
        logger.error("Content file not found: %s", content_path)
        sys.exit(1)

    results = {}

    # 1. Bayesian difficulty
    results["bayesian"] = run_script(
        "bayesian_difficulty.py",
        [data_path, content_path, "--output", output_path],
        analysis_dir,
    )

    # 2. Calibration
    results["calibration"] = run_script(
        "calibration_plot.py",
        [data_path, content_path, "--output", output_path],
        analysis_dir,
    )

    # 3. Drift detection
    results["drift"] = run_script(
        "drift_detection.py",
        [data_path, "--window", str(args.window), "--output", output_path],
        analysis_dir,
    )

    # 4. IRT model
    results["irt"] = run_script(
        "irt_model.py",
        [data_path, content_path, "--output", output_path],
        analysis_dir,
    )

    # Summary
    print(f"\n{'=' * 60}")
    print("PIPELINE COMPLETE")
    print(f"{'=' * 60}")

    all_passed = True
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        if not success:
            all_passed = False
        print(f"  {name:20s} {status}")

    print(f"\nOutput directory: {output_path}")

    # List generated files
    output_files = sorted(Path(output_path).glob("*"))
    if output_files:
        print(f"\nGenerated files:")
        for f in output_files:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:40s} {size_kb:8.1f} KB")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()

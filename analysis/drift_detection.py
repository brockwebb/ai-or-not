"""
drift_detection.py — Temporal drift analysis for AI or Not?.

Detects shifts in player accuracy over time, which may indicate:
- Improving AI generation quality (harder to detect)
- Changes in player population (e.g., different event audiences)
- Content library updates

Uses rolling accuracy windows and CUSUM changepoint detection.
"""

import argparse
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from load_data import load_sessions

logger = logging.getLogger(__name__)

PLOT_DPI = 150

# CUSUM detection threshold — number of standard deviations for
# flagging a changepoint. Higher = fewer false positives.
CUSUM_THRESHOLD_SIGMAS = 4.0


def compute_rolling_accuracy(
    df: pd.DataFrame, window: int = 50
) -> pd.DataFrame:
    """Compute rolling accuracy over sessions ordered by timestamp.

    Parameters
    ----------
    df : pd.DataFrame
        Per-item-response data from load_sessions().
    window : int
        Number of sessions per rolling window.

    Returns
    -------
    pd.DataFrame
        Columns: session_order, rolling_accuracy, timestamp_midpoint,
                 session_count.
    """
    if df.empty:
        return pd.DataFrame()

    # Aggregate per session
    session_acc = (
        df.sort_values("timestamp")
        .groupby("session_id", sort=False)
        .agg(
            accuracy=("correct", "mean"),
            timestamp=("timestamp", "first"),
        )
        .reset_index()
    )
    session_acc = session_acc.sort_values("timestamp").reset_index(drop=True)
    session_acc["session_order"] = range(len(session_acc))

    # Rolling window
    session_acc["rolling_accuracy"] = (
        session_acc["accuracy"].rolling(window=window, min_periods=1).mean()
    )

    return session_acc


def cusum_changepoints(
    accuracies: np.ndarray, threshold_sigmas: float = CUSUM_THRESHOLD_SIGMAS
) -> list[int]:
    """Detect changepoints using CUSUM (cumulative sum) algorithm.

    Tracks cumulative deviations from the overall mean. When the cumulative
    sum exceeds threshold_sigmas * std, a changepoint is flagged.

    Parameters
    ----------
    accuracies : np.ndarray
        Sequence of accuracy values (per-session).
    threshold_sigmas : float
        Detection threshold in units of standard deviation.

    Returns
    -------
    list[int]
        Indices where changepoints were detected.
    """
    if len(accuracies) < 10:
        logger.warning("Too few sessions (%d) for CUSUM detection", len(accuracies))
        return []

    mean = np.mean(accuracies)
    std = np.std(accuracies)

    if std < 1e-10:
        logger.info("Zero variance in accuracy — no changepoints possible")
        return []

    threshold = threshold_sigmas * std
    changepoints = []

    # Track positive and negative cumulative sums
    s_pos = 0.0
    s_neg = 0.0

    for i, val in enumerate(accuracies):
        deviation = val - mean
        s_pos = max(0, s_pos + deviation)
        s_neg = min(0, s_neg + deviation)

        if s_pos > threshold:
            changepoints.append(i)
            s_pos = 0.0  # Reset after detection
        elif abs(s_neg) > threshold:
            changepoints.append(i)
            s_neg = 0.0

    return changepoints


def plot_drift(
    session_acc: pd.DataFrame,
    changepoints: list[int],
    window: int,
    output_path: str,
) -> None:
    """Plot rolling accuracy over time with changepoint annotations.

    Parameters
    ----------
    session_acc : pd.DataFrame
        Output of compute_rolling_accuracy().
    changepoints : list[int]
        Session indices flagged as changepoints.
    window : int
        Rolling window size (for plot title).
    output_path : str
        Path to save the PNG.
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(
        session_acc["session_order"],
        session_acc["rolling_accuracy"],
        color="steelblue",
        linewidth=1.5,
        label=f"Rolling accuracy (window={window})",
    )

    # Raw per-session accuracy as faint scatter
    ax.scatter(
        session_acc["session_order"],
        session_acc["accuracy"],
        color="gray",
        alpha=0.15,
        s=10,
        label="Per-session accuracy",
    )

    # Overall mean
    overall_mean = session_acc["accuracy"].mean()
    ax.axhline(
        overall_mean,
        color="coral",
        linestyle="--",
        alpha=0.7,
        label=f"Overall mean ({overall_mean:.3f})",
    )

    # Changepoints
    for cp in changepoints:
        ax.axvline(cp, color="red", linestyle=":", alpha=0.8)
        ax.annotate(
            f"shift @ {cp}",
            xy=(cp, ax.get_ylim()[1]),
            xytext=(cp + 2, ax.get_ylim()[1] * 0.98),
            fontsize=7,
            color="red",
        )

    ax.set_xlabel("Session (chronological order)")
    ax.set_ylabel("Accuracy")
    ax.set_title("Player Accuracy Over Time — Drift Detection")
    ax.legend(loc="lower left", fontsize=8)
    ax.set_ylim(-0.05, 1.05)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=PLOT_DPI)
    plt.close()
    logger.info("Drift plot saved to %s", output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Detect accuracy drift over time in AI or Not? sessions"
    )
    parser.add_argument("data", help="Path to JSONL session data file")
    parser.add_argument(
        "--window",
        type=int,
        default=50,
        help="Rolling window size in sessions (default: 50)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=CUSUM_THRESHOLD_SIGMAS,
        help=f"CUSUM threshold in sigmas (default: {CUSUM_THRESHOLD_SIGMAS})",
    )
    parser.add_argument(
        "--output",
        default="results",
        help="Output directory (default: results/)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_sessions(args.data)
    if df.empty:
        logger.error("No data loaded")
        return

    logger.info(
        "Loaded %d item-responses from %d sessions",
        len(df),
        df["session_id"].nunique(),
    )

    session_acc = compute_rolling_accuracy(df, window=args.window)

    # CUSUM on per-session accuracy
    changepoints = cusum_changepoints(
        session_acc["accuracy"].values, threshold_sigmas=args.threshold
    )

    # Summary
    print(f"\n=== Drift Detection Summary ===")
    print(f"Sessions: {len(session_acc)}")
    print(f"Overall accuracy: {session_acc['accuracy'].mean():.3f}")
    print(f"Rolling window: {args.window}")
    print(f"CUSUM threshold: {args.threshold} sigmas")
    print(f"Changepoints detected: {len(changepoints)}")
    if changepoints:
        print(f"Changepoint session indices: {changepoints}")

    # Save rolling data
    csv_path = output_dir / "drift_rolling_accuracy.csv"
    session_acc.to_csv(csv_path, index=False)

    # Plot
    plot_path = output_dir / "drift_accuracy.png"
    plot_drift(session_acc, changepoints, args.window, str(plot_path))


if __name__ == "__main__":
    main()

"""
calibration_plot.py — Curator calibration analysis for AI or Not?.

Compares the curator's prior difficulty estimates against observed difficulty
from real player data. Perfect calibration = points on the diagonal.

This is a core research output: it measures how well the curator's
"beginner's mind" intuition matches actual player behavior.
"""

import argparse
import logging
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from load_data import load_content, load_sessions

logger = logging.getLogger(__name__)

PLOT_DPI = 150

# Minimum observations to include an item in the calibration plot.
# Items with fewer responses produce noisy observed-difficulty estimates.
MIN_OBSERVATIONS = 5


def compute_calibration(
    df: pd.DataFrame, content: dict, min_obs: int = MIN_OBSERVATIONS
) -> pd.DataFrame:
    """Compute observed difficulty per item alongside curator prior.

    Parameters
    ----------
    df : pd.DataFrame
        Per-item-response data from load_sessions().
    content : dict
        Content library keyed by item_id.
    min_obs : int
        Minimum number of observations per item to include.

    Returns
    -------
    pd.DataFrame
        Columns: item_id, prior_difficulty, observed_difficulty, n_obs,
                 category.
    """
    item_stats = (
        df.groupby("item_id")["correct"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "accuracy", "count": "n_obs"})
    )
    # Difficulty = 1 - accuracy (fraction who got it wrong)
    item_stats["observed_difficulty"] = 1.0 - item_stats["accuracy"]

    rows = []
    for item_id, item_data in content.items():
        prior = item_data.get("prior_difficulty", 0.5)
        category = item_data.get("category", "unknown")

        if item_id in item_stats.index:
            obs = item_stats.loc[item_id]
            if obs["n_obs"] >= min_obs:
                rows.append(
                    {
                        "item_id": item_id,
                        "prior_difficulty": prior,
                        "observed_difficulty": obs["observed_difficulty"],
                        "n_obs": int(obs["n_obs"]),
                        "category": category,
                    }
                )
            else:
                logger.info(
                    "Item %s has only %d obs (< %d), excluded",
                    item_id,
                    int(obs["n_obs"]),
                    min_obs,
                )
        else:
            logger.info("Item %s has no observations, excluded", item_id)

    return pd.DataFrame(rows)


def plot_calibration(cal_df: pd.DataFrame, output_path: str) -> None:
    """Scatter plot of prior vs observed difficulty.

    Parameters
    ----------
    cal_df : pd.DataFrame
        Output of compute_calibration().
    output_path : str
        Path to save the PNG.
    """
    if cal_df.empty:
        logger.warning("No items with sufficient observations for calibration plot")
        return

    fig, ax = plt.subplots(figsize=(8, 8))

    # Color by category
    categories = cal_df["category"].unique()
    cmap = matplotlib.colormaps.get_cmap("tab10").resampled(max(len(categories), 1))
    cat_colors = {cat: cmap(i) for i, cat in enumerate(categories)}

    for cat in categories:
        subset = cal_df[cal_df["category"] == cat]
        ax.scatter(
            subset["prior_difficulty"],
            subset["observed_difficulty"],
            s=subset["n_obs"] * 3,  # Point size proportional to observations
            c=[cat_colors[cat]],
            label=cat,
            alpha=0.7,
            edgecolors="white",
            linewidths=0.5,
        )

    # Perfect calibration diagonal
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfect calibration")

    # Calibration metrics
    mae = np.mean(np.abs(cal_df["prior_difficulty"] - cal_df["observed_difficulty"]))
    if len(cal_df) >= 3:
        r, p_val = sp_stats.pearsonr(
            cal_df["prior_difficulty"], cal_df["observed_difficulty"]
        )
        metric_text = f"MAE = {mae:.3f}\nr = {r:.3f} (p = {p_val:.3g})\nn = {len(cal_df)} items"
    else:
        metric_text = f"MAE = {mae:.3f}\nn = {len(cal_df)} items (too few for correlation)"

    ax.text(
        0.05,
        0.95,
        metric_text,
        transform=ax.transAxes,
        verticalalignment="top",
        fontsize=9,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
    )

    ax.set_xlabel("Curator Prior Difficulty")
    ax.set_ylabel("Observed Difficulty (fraction wrong)")
    ax.set_title("Curator Calibration: Prior vs Observed Item Difficulty")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_aspect("equal")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=PLOT_DPI)
    plt.close()
    logger.info("Calibration plot saved to %s", output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Curator calibration: prior vs observed difficulty"
    )
    parser.add_argument("data", help="Path to JSONL session data file")
    parser.add_argument("content", help="Path to content.json")
    parser.add_argument(
        "--output",
        default="results",
        help="Output directory (default: results/)",
    )
    parser.add_argument(
        "--min-obs",
        type=int,
        default=MIN_OBSERVATIONS,
        help=f"Minimum observations per item to include (default: {MIN_OBSERVATIONS})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_sessions(args.data)
    content = load_content(args.content)

    cal_df = compute_calibration(df, content, min_obs=args.min_obs)

    if cal_df.empty:
        logger.error("No items with sufficient observations. Need at least %d.", args.min_obs)
        return

    # Save CSV
    csv_path = output_dir / "calibration.csv"
    cal_df.to_csv(csv_path, index=False)

    # Print summary
    mae = np.mean(np.abs(cal_df["prior_difficulty"] - cal_df["observed_difficulty"]))
    print(f"\n=== Calibration Summary ===")
    print(f"Items with >= {args.min_obs} observations: {len(cal_df)}")
    print(f"Mean Absolute Error: {mae:.3f}")
    if len(cal_df) >= 3:
        r, _ = sp_stats.pearsonr(
            cal_df["prior_difficulty"], cal_df["observed_difficulty"]
        )
        print(f"Pearson r: {r:.3f}")
    print(cal_df.to_string(index=False))

    # Plot
    plot_path = output_dir / "calibration_scatter.png"
    plot_calibration(cal_df, str(plot_path))


if __name__ == "__main__":
    main()

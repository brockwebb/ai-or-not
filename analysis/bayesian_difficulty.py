"""
bayesian_difficulty.py — Bayesian difficulty estimation for AI or Not? items.

Uses Beta-Binomial conjugate model with informative curator priors.
Prior effective sample size = 10, encoding curator's initial difficulty estimate.

Produces per-item posterior estimates and a forest plot comparing
prior vs posterior difficulty.
"""

import argparse
import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from load_data import load_content, load_sessions

logger = logging.getLogger(__name__)

# Prior effective sample size — how strongly we trust the curator's initial
# estimate. 10 means the prior carries the weight of 10 observations.
PRIOR_EFFECTIVE_N = 10

# Plot configuration
PLOT_DPI = 150


def compute_difficulty(
    df: pd.DataFrame, content: dict
) -> pd.DataFrame:
    """Compute Bayesian posterior difficulty for each item.

    Parameters
    ----------
    df : pd.DataFrame
        Per-item-response data from load_sessions().
    content : dict
        Content library keyed by item_id from load_content().

    Returns
    -------
    pd.DataFrame
        One row per item with columns: item_id, prior_difficulty, prior_alpha,
        prior_beta, correct_count, incorrect_count, posterior_alpha,
        posterior_beta, posterior_mean, ci_lower, ci_upper, effective_n,
        category.
    """
    # Aggregate observed results per item
    # "correct" here means the player guessed correctly, so higher correct
    # rate = easier item = lower difficulty.
    # Difficulty = P(player gets it wrong) = 1 - accuracy.
    item_stats = (
        df.groupby("item_id")["correct"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "correct_count", "count": "total_count"})
    )
    item_stats["incorrect_count"] = (
        item_stats["total_count"] - item_stats["correct_count"]
    )

    results = []
    for item_id, item_data in content.items():
        prior_diff = item_data.get("prior_difficulty", 0.5)
        # Clamp to avoid degenerate Beta params
        prior_diff = max(0.01, min(0.99, prior_diff))

        # Prior: Beta(alpha, beta) where mean = alpha / (alpha + beta)
        # and alpha + beta = PRIOR_EFFECTIVE_N.
        # Difficulty = P(wrong), so alpha encodes "wrong" observations,
        # beta encodes "correct" observations.
        prior_alpha = prior_diff * PRIOR_EFFECTIVE_N
        prior_beta = (1.0 - prior_diff) * PRIOR_EFFECTIVE_N

        if item_id in item_stats.index:
            row = item_stats.loc[item_id]
            correct_count = int(row["correct_count"])
            incorrect_count = int(row["incorrect_count"])
        else:
            correct_count = 0
            incorrect_count = 0

        # Posterior update: observed incorrect → increase alpha (difficulty),
        # observed correct → increase beta (easiness).
        post_alpha = prior_alpha + incorrect_count
        post_beta = prior_beta + correct_count

        post_mean = post_alpha / (post_alpha + post_beta)

        # 95% credible interval from Beta posterior
        ci_lower = stats.beta.ppf(0.025, post_alpha, post_beta)
        ci_upper = stats.beta.ppf(0.975, post_alpha, post_beta)

        effective_n = post_alpha + post_beta

        results.append(
            {
                "item_id": item_id,
                "category": item_data.get("category", "unknown"),
                "prior_difficulty": prior_diff,
                "prior_alpha": prior_alpha,
                "prior_beta": prior_beta,
                "correct_count": correct_count,
                "incorrect_count": incorrect_count,
                "posterior_alpha": post_alpha,
                "posterior_beta": post_beta,
                "posterior_mean": post_mean,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "effective_n": effective_n,
            }
        )

    return pd.DataFrame(results)


def plot_forest(result_df: pd.DataFrame, output_path: str) -> None:
    """Forest plot: prior vs posterior difficulty per item with 95% CIs.

    Parameters
    ----------
    result_df : pd.DataFrame
        Output of compute_difficulty().
    output_path : str
        Path to save the PNG.
    """
    result_df = result_df.sort_values("posterior_mean", ascending=True).reset_index(
        drop=True
    )
    n_items = len(result_df)

    fig_height = max(4, n_items * 0.4)
    fig, ax = plt.subplots(figsize=(10, fig_height))

    y_positions = np.arange(n_items)

    # Posterior CIs and means
    ax.hlines(
        y_positions,
        result_df["ci_lower"],
        result_df["ci_upper"],
        color="steelblue",
        linewidth=2,
        label="95% CI (posterior)",
    )
    ax.scatter(
        result_df["posterior_mean"],
        y_positions,
        color="steelblue",
        zorder=5,
        s=40,
        label="Posterior mean",
    )

    # Prior markers
    ax.scatter(
        result_df["prior_difficulty"],
        y_positions,
        color="coral",
        marker="x",
        zorder=5,
        s=40,
        label="Prior (curator)",
    )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(result_df["item_id"], fontsize=7)
    ax.set_xlabel("Difficulty (P(player wrong))")
    ax.set_title("Bayesian Item Difficulty: Prior vs Posterior")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_xlim(-0.05, 1.05)
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=PLOT_DPI)
    plt.close()
    logger.info("Forest plot saved to %s", output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Bayesian difficulty estimation for AI or Not? items"
    )
    parser.add_argument("data", help="Path to JSONL session data file")
    parser.add_argument("content", help="Path to content.json")
    parser.add_argument(
        "--output",
        default="results",
        help="Output directory for results and plots (default: results/)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_sessions(args.data)
    content = load_content(args.content)

    logger.info(
        "Loaded %d item-responses across %d sessions, %d content items",
        len(df),
        df["session_id"].nunique(),
        len(content),
    )

    result_df = compute_difficulty(df, content)

    # Save CSV
    csv_path = output_dir / "bayesian_difficulty.csv"
    result_df.to_csv(csv_path, index=False)
    logger.info("Results saved to %s", csv_path)

    # Print summary
    print("\n=== Bayesian Difficulty Summary ===")
    print(
        result_df[
            [
                "item_id",
                "prior_difficulty",
                "posterior_mean",
                "ci_lower",
                "ci_upper",
                "effective_n",
            ]
        ].to_string(index=False)
    )

    # Forest plot
    plot_path = output_dir / "bayesian_difficulty_forest.png"
    plot_forest(result_df, str(plot_path))


if __name__ == "__main__":
    main()

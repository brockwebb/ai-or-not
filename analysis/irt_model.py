"""
irt_model.py — 1-Parameter Logistic (Rasch) Item Response Theory model.

Estimates item difficulty and player ability simultaneously from the
complete response matrix. The Rasch model says:

    P(correct) = 1 / (1 + exp(-(ability - difficulty)))

Parameters are estimated by maximizing the joint log-likelihood.
"""

import argparse
import logging
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from load_data import load_content, load_sessions

logger = logging.getLogger(__name__)

PLOT_DPI = 150


def build_response_matrix(df: pd.DataFrame) -> tuple[np.ndarray, list, list]:
    """Build a player-by-item response matrix from per-item-response data.

    Parameters
    ----------
    df : pd.DataFrame
        Per-item-response data from load_sessions().

    Returns
    -------
    response_matrix : np.ndarray
        Shape (n_players, n_items). Values: 1 (correct), 0 (incorrect),
        NaN (not seen).
    player_ids : list
        Ordered list of session_id values (rows).
    item_ids : list
        Ordered list of item_id values (columns).
    """
    player_ids = sorted(df["session_id"].unique())
    item_ids = sorted(df["item_id"].dropna().unique())

    player_idx = {pid: i for i, pid in enumerate(player_ids)}
    item_idx = {iid: i for i, iid in enumerate(item_ids)}

    matrix = np.full((len(player_ids), len(item_ids)), np.nan)

    for _, row in df.iterrows():
        pid = row["session_id"]
        iid = row["item_id"]
        if pid in player_idx and iid in item_idx:
            matrix[player_idx[pid], item_idx[iid]] = float(row["correct"])

    return matrix, player_ids, item_ids


def rasch_log_likelihood(params: np.ndarray, matrix: np.ndarray) -> float:
    """Negative log-likelihood for the Rasch model.

    Parameters
    ----------
    params : np.ndarray
        First n_players values are abilities, next n_items are difficulties.
    matrix : np.ndarray
        Response matrix (n_players x n_items), NaN for missing.

    Returns
    -------
    float
        Negative log-likelihood (to minimize).
    """
    n_players = matrix.shape[0]
    abilities = params[:n_players]
    difficulties = params[n_players:]

    # Broadcast: abilities (n_players, 1) - difficulties (1, n_items)
    logit = abilities[:, np.newaxis] - difficulties[np.newaxis, :]

    # Clip for numerical stability
    logit = np.clip(logit, -30, 30)

    prob = 1.0 / (1.0 + np.exp(-logit))
    prob = np.clip(prob, 1e-15, 1.0 - 1e-15)

    # Log-likelihood only for observed responses
    observed = ~np.isnan(matrix)
    ll = np.where(
        observed,
        matrix * np.log(prob) + (1.0 - matrix) * np.log(1.0 - prob),
        0.0,
    )

    # Small regularization to avoid unbounded params for items/players
    # with all-correct or all-incorrect responses
    regularization = 0.01 * np.sum(params**2)

    return -np.sum(ll) + regularization


def fit_rasch(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit the Rasch model via maximum likelihood.

    Parameters
    ----------
    matrix : np.ndarray
        Response matrix (n_players x n_items), NaN for missing.

    Returns
    -------
    abilities : np.ndarray
        Estimated player abilities (higher = better).
    difficulties : np.ndarray
        Estimated item difficulties (higher = harder).
    """
    n_players, n_items = matrix.shape

    # Initialize: abilities and difficulties at 0
    init_params = np.zeros(n_players + n_items)

    logger.info(
        "Fitting Rasch model: %d players, %d items, %d observed responses",
        n_players,
        n_items,
        int(np.sum(~np.isnan(matrix))),
    )

    result = minimize(
        rasch_log_likelihood,
        init_params,
        args=(matrix,),
        method="L-BFGS-B",
        options={"maxiter": 2000, "ftol": 1e-8},
    )

    if not result.success:
        logger.warning("Optimization did not fully converge: %s", result.message)
    else:
        logger.info("Converged in %d iterations", result.nit)

    abilities = result.x[:n_players]
    difficulties = result.x[n_players:]

    # Center difficulties (identification constraint: mean difficulty = 0)
    mean_diff = np.mean(difficulties)
    difficulties -= mean_diff
    abilities -= mean_diff

    return abilities, difficulties


def plot_difficulty_distribution(
    difficulties: np.ndarray, item_ids: list, output_path: str
) -> None:
    """Histogram of IRT item difficulty estimates."""
    fig, ax = plt.subplots(figsize=(8, 5))

    ax.hist(difficulties, bins=20, color="steelblue", edgecolor="white", alpha=0.8)
    ax.axvline(0, color="coral", linestyle="--", alpha=0.7, label="Mean difficulty")
    ax.set_xlabel("IRT Difficulty (logit scale)")
    ax.set_ylabel("Count")
    ax.set_title("Distribution of IRT Item Difficulty Estimates")
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=PLOT_DPI)
    plt.close()
    logger.info("Difficulty distribution plot saved to %s", output_path)


def plot_item_characteristic_curves(
    difficulties: np.ndarray, item_ids: list, output_path: str, max_curves: int = 15
) -> None:
    """Item Characteristic Curves (ICCs) for a subset of items."""
    fig, ax = plt.subplots(figsize=(10, 6))

    theta = np.linspace(-4, 4, 200)

    # Select a spread of items by difficulty
    sorted_idx = np.argsort(difficulties)
    if len(sorted_idx) > max_curves:
        step = len(sorted_idx) // max_curves
        selected = sorted_idx[::step][:max_curves]
    else:
        selected = sorted_idx

    cmap = matplotlib.colormaps.get_cmap("coolwarm").resampled(len(selected))

    for rank, idx in enumerate(selected):
        prob = 1.0 / (1.0 + np.exp(-(theta - difficulties[idx])))
        ax.plot(
            theta,
            prob,
            color=cmap(rank),
            label=f"{item_ids[idx]} (d={difficulties[idx]:.2f})",
            linewidth=1.5,
        )

    ax.set_xlabel("Player Ability (logit)")
    ax.set_ylabel("P(correct)")
    ax.set_title("Item Characteristic Curves (Rasch Model)")
    ax.legend(fontsize=6, loc="lower right", ncol=2)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=PLOT_DPI)
    plt.close()
    logger.info("ICC plot saved to %s", output_path)


def plot_difficulty_comparison(
    irt_difficulties: np.ndarray,
    item_ids: list,
    content: dict,
    output_path: str,
) -> None:
    """Compare IRT difficulty to curator prior and Bayesian posterior."""
    rows = []
    for i, item_id in enumerate(item_ids):
        if item_id in content:
            prior = content[item_id].get("prior_difficulty", 0.5)
            rows.append(
                {
                    "item_id": item_id,
                    "irt_difficulty": irt_difficulties[i],
                    "prior_difficulty": prior,
                }
            )

    if not rows:
        logger.warning("No matching items between IRT results and content.json")
        return

    comp_df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.scatter(
        comp_df["prior_difficulty"],
        comp_df["irt_difficulty"],
        color="steelblue",
        alpha=0.7,
        edgecolors="white",
        s=50,
    )

    # Label outliers (IRT difficulty > 1 SD from linear fit)
    for _, row in comp_df.iterrows():
        ax.annotate(
            row["item_id"],
            (row["prior_difficulty"], row["irt_difficulty"]),
            fontsize=6,
            alpha=0.6,
            xytext=(3, 3),
            textcoords="offset points",
        )

    ax.set_xlabel("Curator Prior Difficulty (0-1 scale)")
    ax.set_ylabel("IRT Difficulty (logit scale)")
    ax.set_title("IRT Difficulty vs Curator Prior")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=PLOT_DPI)
    plt.close()
    logger.info("Difficulty comparison plot saved to %s", output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Rasch (1PL) IRT model for AI or Not? items"
    )
    parser.add_argument("data", help="Path to JSONL session data file")
    parser.add_argument("content", help="Path to content.json")
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
    content = load_content(args.content)

    if df.empty:
        logger.error("No data loaded")
        return

    matrix, player_ids, item_ids = build_response_matrix(df)

    n_observed = int(np.sum(~np.isnan(matrix)))
    logger.info(
        "Response matrix: %d players x %d items, %d observed (%.1f%% fill)",
        len(player_ids),
        len(item_ids),
        n_observed,
        100.0 * n_observed / (len(player_ids) * len(item_ids)),
    )

    abilities, difficulties = fit_rasch(matrix)

    # Build results DataFrame
    item_results = pd.DataFrame(
        {"item_id": item_ids, "irt_difficulty": difficulties}
    ).sort_values("irt_difficulty", ascending=False)

    player_results = pd.DataFrame(
        {"session_id": player_ids, "irt_ability": abilities}
    ).sort_values("irt_ability", ascending=False)

    # Save CSVs
    item_results.to_csv(output_dir / "irt_item_difficulty.csv", index=False)
    player_results.to_csv(output_dir / "irt_player_ability.csv", index=False)

    # Summary
    print("\n=== IRT (Rasch) Model Summary ===")
    print(f"Players: {len(player_ids)}, Items: {len(item_ids)}")
    print(f"\nItem difficulties (logit scale):")
    print(f"  Mean: {np.mean(difficulties):.3f}")
    print(f"  SD:   {np.std(difficulties):.3f}")
    print(f"  Range: [{np.min(difficulties):.3f}, {np.max(difficulties):.3f}]")
    print(f"\nPlayer abilities (logit scale):")
    print(f"  Mean: {np.mean(abilities):.3f}")
    print(f"  SD:   {np.std(abilities):.3f}")
    print(f"  Range: [{np.min(abilities):.3f}, {np.max(abilities):.3f}]")

    print(f"\nTop 5 hardest items:")
    print(item_results.head(5).to_string(index=False))

    print(f"\nTop 5 easiest items:")
    print(item_results.tail(5).to_string(index=False))

    # Plots
    plot_difficulty_distribution(
        difficulties, item_ids, str(output_dir / "irt_difficulty_distribution.png")
    )
    plot_item_characteristic_curves(
        difficulties, item_ids, str(output_dir / "irt_icc.png")
    )
    plot_difficulty_comparison(
        difficulties, item_ids, content, str(output_dir / "irt_vs_prior.png")
    )


if __name__ == "__main__":
    main()

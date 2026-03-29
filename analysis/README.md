# AI or Not? — Analysis Workbench

Offline Python analysis scripts for the AI or Not? game. These scripts run against JSONL session exports from Google Sheets and the game's `content.json` library.

## Setup

```bash
cd analysis/
pip install -r requirements.txt
```

Requirements: numpy, scipy, pandas, matplotlib, seaborn. No GPU needed.

## Quick Start with Test Data

Generate synthetic data and run the full pipeline:

```bash
python test_data.py --sessions 200 --output test_sessions.jsonl --content-output test_content.json
python run_all.py test_sessions.jsonl --content test_content.json --output results/
```

## Scripts

### load_data.py

Data loading utilities shared by all analysis scripts.

- `load_sessions(jsonl_path)` -- Loads JSONL session exports and expands nested items into per-item rows. One row per item-response (player x item), not per session. Handles malformed rows with warnings.
- `load_content(json_path)` -- Loads `content.json` and returns a dict keyed by item ID.

### bayesian_difficulty.py

Bayesian item difficulty estimation using a Beta-Binomial conjugate model.

- **Prior**: Beta distribution derived from curator's `prior_difficulty` score. Effective sample size = 10 (informative prior, per AD-003).
- **Update**: Posterior = prior + observed correct/incorrect counts.
- **Output**: Per-item prior mean, posterior mean, 95% credible interval, effective sample size.
- **Plot**: Forest plot showing prior vs posterior difficulty with credible intervals.

```bash
python bayesian_difficulty.py data.jsonl content.json --output results/
```

### calibration_plot.py

Measures how well the curator's difficulty priors match observed player behavior.

- **Plot**: Scatter of prior difficulty (x) vs observed difficulty (y). Diagonal = perfect calibration. Point size = number of observations, color = content category.
- **Metrics**: Mean absolute error (MAE), Pearson correlation.
- Items with fewer than 5 observations are excluded (configurable via `--min-obs`).

```bash
python calibration_plot.py data.jsonl content.json --output results/
```

### drift_detection.py

Detects temporal shifts in player accuracy that may indicate improving AI quality, content changes, or population shifts.

- **Rolling accuracy**: Configurable window size over chronologically ordered sessions.
- **CUSUM changepoint detection**: Flags statistically significant accuracy shifts.
- **Plot**: Rolling accuracy over time with per-session scatter and changepoint annotations.

```bash
python drift_detection.py data.jsonl --window 50 --output results/
```

### irt_model.py

1-Parameter Logistic (Rasch) Item Response Theory model.

- Estimates item difficulty and player ability simultaneously via maximum likelihood (scipy.optimize).
- **Outputs**: Item difficulty parameters (logit scale), player ability parameters (logit scale).
- **Plots**: Item difficulty distribution histogram, Item Characteristic Curves (ICCs), IRT difficulty vs curator prior comparison.

```bash
python irt_model.py data.jsonl content.json --output results/
```

### test_data.py

Generates synthetic JSONL and content.json for testing all analysis scripts.

- Creates sessions with known properties: easy items, hard items, a mid-dataset drift changepoint, varying player abilities.
- Deterministic with `--seed` for reproducibility.

```bash
python test_data.py --sessions 200 --output test_sessions.jsonl --content-output test_content.json
```

### run_all.py

Runs the full analysis pipeline and generates all outputs.

```bash
python run_all.py data.jsonl --content content.json --output results/
```

## Interpreting the Plots

### Forest Plot (bayesian_difficulty_forest.png)

- Each row is one content item, ordered by posterior difficulty.
- Blue dots = posterior mean difficulty, blue bars = 95% credible interval.
- Red X marks = curator's prior estimate.
- When the X is far from the blue dot, the curator's intuition was off for that item.
- Narrow intervals = many observations (high confidence). Wide intervals = few observations.

### Calibration Scatter (calibration_scatter.png)

- Points on the diagonal = curator's priors perfectly predicted observed difficulty.
- Points above the diagonal = items were harder than the curator expected.
- Points below = easier than expected.
- MAE close to 0 = well-calibrated curator. High MAE = systematic bias.
- Pearson r close to 1 = curator has good rank-ordering even if absolute values are off.

### Drift Plot (drift_accuracy.png)

- Upward trend = players getting better (or content getting easier).
- Downward trend = AI getting harder to detect (or weaker player population).
- Red vertical lines = CUSUM-detected changepoints.
- The test data has a deliberate drift at the midpoint -- the plot should show a visible downward shift.

### IRT Difficulty Distribution (irt_difficulty_distribution.png)

- Histogram of estimated item difficulties on the logit scale.
- Centered at 0 by convention. Positive = harder, negative = easier.
- Wide spread = good mix of easy and hard items. Narrow = items are too similar.

### Item Characteristic Curves (irt_icc.png)

- Each curve shows P(correct) as a function of player ability for one item.
- Curves shifted right = harder items. Shifted left = easier.
- All curves have the same slope (Rasch model assumption -- discrimination is equal).

### IRT vs Prior (irt_vs_prior.png)

- Compares IRT-estimated difficulty (logit scale) to curator's prior (0-1 scale).
- Positive correlation = curator's rank-ordering roughly agrees with the model.
- Note the different scales: IRT is unbounded logit, prior is bounded 0-1.

## JSONL Format

One JSON object per line, each representing a complete game session:

```json
{"session_id":"abc123","timestamp":"2026-04-08T14:30:00Z","items":[{"item_id":"img-001","guess":true,"correct":true,"reasoning":"hands looked weird"}],"score":7,"total":10}
```

## Output Files

All outputs go to the `--output` directory (default: `results/`):

| File | Description |
|------|-------------|
| `bayesian_difficulty.csv` | Per-item Bayesian difficulty estimates |
| `bayesian_difficulty_forest.png` | Forest plot of prior vs posterior difficulty |
| `calibration.csv` | Calibration data (prior vs observed) |
| `calibration_scatter.png` | Calibration scatter plot |
| `drift_rolling_accuracy.csv` | Rolling accuracy time series |
| `drift_accuracy.png` | Drift detection plot |
| `irt_item_difficulty.csv` | IRT item difficulty estimates |
| `irt_player_ability.csv` | IRT player ability estimates |
| `irt_difficulty_distribution.png` | IRT difficulty histogram |
| `irt_icc.png` | Item Characteristic Curves |
| `irt_vs_prior.png` | IRT vs curator prior comparison |

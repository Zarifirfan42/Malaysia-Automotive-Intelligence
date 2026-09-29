"""A small pre-specified set of tests on aggregated registration series.

The observation for a volume or share test is a month or a year, not one of the
underlying registration rows. A chi-square on period counts uses registration
transactions and is interpreted through its effect size.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05
PRIMARY_TEST_IDS = (
    "calendar_month_volume",
    "electric_share_trend",
    "hybrid_share_trend",
    "fuel_composition_periods",
)


def epsilon_squared(statistic: float, sample_size: int) -> float:
    """Rank effect size H(n+1)/(n^2-1), on a 0–1 scale."""
    if sample_size < 2:
        return float("nan")
    return float(statistic * (sample_size + 1) / (sample_size**2 - 1))


def interpret_epsilon(value: float) -> str:
    if not math.isfinite(value):
        return "undefined"
    if value < 0.01:
        return "negligible"
    if value < 0.06:
        return "small"
    if value < 0.14:
        return "medium"
    return "large"


def cramers_v(statistic: float, sample_size: int, rows: int, columns: int) -> float:
    """sqrt(chi-square / (n * min(rows-1, columns-1)))."""
    degrees = min(rows - 1, columns - 1)
    if sample_size <= 0 or degrees <= 0:
        return float("nan")
    return float(math.sqrt(statistic / (sample_size * degrees)))


def interpret_cramers_v(value: float, rows: int, columns: int) -> str:
    if not math.isfinite(value):
        return "undefined"
    degrees = min(rows - 1, columns - 1)
    if degrees <= 1:
        cuts = (0.10, 0.30, 0.50)
    elif degrees == 2:
        cuts = (0.07, 0.21, 0.35)
    else:
        cuts = (0.06, 0.17, 0.29)
    if value < cuts[0]:
        return "negligible"
    if value < cuts[1]:
        return "small"
    if value < cuts[2]:
        return "medium"
    return "large"


def interpret_rho(value: float) -> str:
    if not math.isfinite(value):
        return "undefined"
    magnitude = abs(value)
    if magnitude < 0.10:
        return "negligible"
    if magnitude < 0.30:
        return "small"
    if magnitude < 0.50:
        return "medium"
    return "large"


def spearman_interval(rho: float, sample_size: int) -> tuple[float | None, float | None]:
    """Fisher z interval for a Spearman coefficient. Undefined near ±1 or for n < 4."""
    if sample_size < 4 or not math.isfinite(rho) or abs(rho) >= 0.999:
        return None, None
    z = np.arctanh(rho)
    margin = 1.96 / math.sqrt(sample_size - 3)
    return float(np.tanh(z - margin)), float(np.tanh(z + margin))


def kruskal_by_group(values: pd.Series, groups: pd.Series) -> dict[str, Any]:
    frame = pd.DataFrame({"value": values, "group": groups}).dropna()
    samples = [frame.loc[frame["group"] == group, "value"].to_numpy() for group in sorted(frame["group"].unique())]
    samples = [sample for sample in samples if len(sample) > 0]
    sample_size = int(sum(len(sample) for sample in samples))
    if len(samples) < 2 or sample_size <= len(samples):
        return {"applicable": False, "reason": "Fewer than two groups have observations."}
    statistic, p_value = stats.kruskal(*samples)
    effect = epsilon_squared(float(statistic), sample_size)
    return {
        "applicable": True,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "sample_size": sample_size,
        "groups": len(samples),
        "effect_size": effect,
        "effect_size_name": "epsilon_squared",
        "effect_size_label": interpret_epsilon(effect),
    }


def spearman_trend(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    frame = pd.DataFrame({"x": x, "y": y}).dropna()
    sample_size = int(len(frame))
    if sample_size < 4 or frame["y"].nunique() < 2 or frame["x"].nunique() < 2:
        return {"applicable": False, "reason": "The series has too little variation for a rank correlation."}
    rho, p_value = stats.spearmanr(frame["x"], frame["y"])
    low, high = spearman_interval(float(rho), sample_size)
    return {
        "applicable": True,
        "statistic": float(rho),
        "p_value": float(p_value),
        "sample_size": sample_size,
        "effect_size": abs(float(rho)),
        "effect_size_name": "absolute_spearman_rho",
        "effect_size_label": interpret_rho(float(rho)),
        "confidence_interval": [low, high],
    }


def chi_square_periods(
    fuel_year: pd.DataFrame,
    earlier_years: list[int],
    recent_years: list[int],
    *,
    minimum_expected: float = 5,
) -> dict[str, Any]:
    """Fuel category by two periods. Rare categories are omitted until expected counts are at least 5."""
    if len(earlier_years) < 1 or len(recent_years) < 1 or set(earlier_years) & set(recent_years):
        return {"applicable": False, "reason": "The two periods are empty or overlap."}
    counts = fuel_year.loc[fuel_year["registration_year"].isin(earlier_years + recent_years)].copy()
    if counts.empty:
        return {"applicable": False, "reason": "The selected years have no fuel counts."}
    counts["period"] = np.where(counts["registration_year"].isin(recent_years), "recent", "earlier")
    table = (
        counts.pivot_table(
            index="fuel_category",
            columns="period",
            values="registration_count",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(columns=["earlier", "recent"], fill_value=0)
    )
    full_total = int(table.to_numpy().sum())
    omitted: list[str] = []
    while len(table.index) >= 2:
        _, _, _, expected = stats.chi2_contingency(table.to_numpy(), correction=False)
        if (expected >= minimum_expected).all():
            break
        smallest = table.sum(axis=1).sort_values().index[0]
        omitted.append(str(smallest))
        table = table.drop(index=smallest)
    else:
        return {
            "applicable": False,
            "reason": "Expected cell counts stay below 5 after removing sparse fuel categories.",
            "omitted_fuel_categories": omitted,
        }
    if len(table.index) < 2:
        return {"applicable": False, "reason": "Fewer than two fuel categories meet the expected-count rule.", "omitted_fuel_categories": omitted}
    observed = table.to_numpy()
    statistic, p_value, degrees, _ = stats.chi2_contingency(observed, correction=False)
    sample_size = int(observed.sum())
    effect = cramers_v(float(statistic), sample_size, observed.shape[0], observed.shape[1])
    return {
        "applicable": True,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "degrees_of_freedom": int(degrees),
        "sample_size": sample_size,
        "rows": int(observed.shape[0]),
        "columns": int(observed.shape[1]),
        "effect_size": effect,
        "effect_size_name": "cramers_v",
        "effect_size_label": interpret_cramers_v(effect, observed.shape[0], observed.shape[1]),
        "included_fuel_categories": [str(value) for value in table.index],
        "omitted_fuel_categories": omitted,
        "share_of_period_registrations_included": sample_size / full_total if full_total else None,
        "earlier_years": earlier_years,
        "recent_years": recent_years,
    }


def apply_bonferroni(tests: list[dict[str, Any]], alpha: float = ALPHA) -> dict[str, Any]:
    """Adjust the pre-specified primary tests that produced a p-value."""
    family = [test for test in tests if test["id"] in PRIMARY_TEST_IDS and test.get("p_value") is not None]
    family_size = len(family)
    adjusted_alpha = alpha / family_size if family_size else None
    for test in tests:
        if test not in family:
            test["p_value_adjusted"] = None
            test["in_bonferroni_family"] = False
            continue
        test["in_bonferroni_family"] = True
        test["p_value_adjusted"] = min(1.0, float(test["p_value"]) * family_size)
        test["null_rejected"] = bool(test["p_value_adjusted"] < alpha)
    return {
        "method": "Bonferroni",
        "alpha": alpha,
        "family_size": family_size,
        "alpha_adjusted": adjusted_alpha,
        "primary_test_ids": list(PRIMARY_TEST_IDS),
    }


def fuel_period_years(complete_years: list[int]) -> tuple[list[int], list[int]] | None:
    """Last three complete years versus 2017–2019 when those years are complete."""
    if len(complete_years) < 6:
        return None
    recent = complete_years[-3:]
    earlier = [year for year in (2017, 2018, 2019) if year in complete_years]
    if earlier != [2017, 2018, 2019] or set(earlier) & set(recent):
        return None
    return earlier, recent

"""Charts of aggregated registration counts. Axes start at zero."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.transformation.rules import CHANNEL_STATE

NAVY = "#1f4e79"
TEAL = "#2a6f4e"
CLAY = "#b85c38"
GOLD = "#c4a35a"
SLATE = "#5c6b73"
PURPLE = "#6b5b95"
SERIES = [NAVY, TEAL, CLAY, GOLD, PURPLE, SLATE, "#3d5a40", "#8c4a3a"]


def save_charts(frames: dict[str, pd.DataFrame], analysis: dict, directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.titlesize": 12,
            "axes.labelsize": 10,
        }
    )
    written = [
        _annual(frames, analysis, directory / "01_annual_registrations.png"),
        _yoy(analysis, directory / "02_yoy_complete_years.png"),
        _like_for_like(analysis, directory / "03_like_for_like.png"),
        _monthly(frames, analysis, directory / "04_monthly_registrations.png"),
        _month_box(frames, directory / "05_calendar_month_boxplot.png"),
        _normalized_month(analysis, directory / "06_year_normalized_month.png"),
        _manufacturers(analysis, directory / "07_manufacturer_totals.png"),
        _manufacturer_trends(frames, analysis, directory / "08_manufacturer_share_trends.png"),
        _models(analysis, directory / "09_model_pairs.png"),
        _vehicle_shares(analysis, directory / "10_vehicle_type_shares.png"),
        _vehicle_trends(frames, analysis, directory / "11_vehicle_type_trends.png"),
        _fuel(frames, analysis, directory / "12_fuel_composition.png"),
        _ev_annual(analysis, directory / "13_ev_hybrid_annual.png"),
        _ev_monthly(frames, directory / "14_ev_hybrid_monthly.png"),
        _states(analysis, directory / "15_state_channel.png"),
        _geographic(analysis, directory / "16_geographic_offices.png"),
        _rakan(analysis, directory / "17_rakan_niaga_share.png"),
        _concentration(analysis, directory / "18_concentration.png"),
    ]
    return [name for name in written if name]


def _annual(frames: dict, analysis: dict, path: Path) -> str:
    yearly = frames["yearly"].copy()
    yearly["registration_year"] = yearly["registration_year"].astype(int)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    colors = [CLAY if bool(flag) else NAVY for flag in yearly["is_partial_year"]]
    ax.bar(yearly["registration_year"], yearly["registration_count"], color=colors, width=0.8)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Registration year")
    ax.set_ylabel("Recorded registrations")
    ax.set_title("Recorded registrations by year")
    partial = [int(year) for year in analysis["partial_years"]]
    if partial:
        ax.legend(
            handles=[
                plt.Rectangle((0, 0), 1, 1, color=NAVY, label="Complete year"),
                plt.Rectangle((0, 0), 1, 1, color=CLAY, label=f"{partial[0]} partial year"),
            ],
            frameon=False,
        )
    _finish(fig, path)
    return path.name


def _yoy(analysis: dict, path: Path) -> str:
    rows = [row for row in analysis["temporal"]["yearly"] if row["yoy_basis"] == "full_year" and row["yoy_percentage_change"] is not None]
    if not rows:
        return ""
    fig, ax = plt.subplots(figsize=(10, 4.8))
    years = [row["registration_year"] for row in rows]
    values = [row["yoy_percentage_change"] * 100 for row in rows]
    colors = [TEAL if value >= 0 else CLAY for value in values]
    ax.bar(years, values, color=colors, width=0.8)
    ax.axhline(0, color=SLATE, linewidth=0.8)
    ax.set_xlabel("Registration year")
    ax.set_ylabel("Change from the previous complete year (%)")
    ax.set_title("Year-over-year change in recorded registrations, complete years only")
    _finish(fig, path)
    return path.name


def _like_for_like(analysis: dict, path: Path) -> str:
    like = analysis["temporal"]["like_for_like"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    labels = [
        f"Jan-{like['through_month_name'][:3]} {like['prior_year']}",
        f"Jan-{like['through_month_name'][:3]} {like['latest_year']}",
    ]
    values = [like["prior_period_registrations"], like["latest_period_registrations"]]
    ax.bar(labels, values, color=[NAVY, CLAY])
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Recorded registrations")
    ax.set_title("Like-for-like recorded registrations")
    _finish(fig, path)
    return path.name


def _monthly(frames: dict, analysis: dict, path: Path) -> str:
    monthly = frames["monthly"].sort_values(["registration_year", "registration_month_number"])
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(range(len(monthly)), monthly["registration_count"], color=NAVY, linewidth=1.1)
    low = {item["registration_year_month"] for item in analysis["temporal"]["low_volume_months"]}
    if low:
        mask = monthly["registration_year_month"].isin(low)
        positions = [index for index, flagged in enumerate(mask) if flagged]
        ax.scatter(positions, monthly.loc[mask, "registration_count"], color=CLAY, zorder=3, label="Below 10% of median")
        ax.legend(frameon=False)
    ax.set_ylim(bottom=0)
    _year_ticks(ax, monthly)
    ax.set_ylabel("Recorded registrations")
    ax.set_title("Monthly recorded registrations")
    _finish(fig, path)
    return path.name


def _month_box(frames: dict, path: Path) -> str:
    monthly = frames["monthly"].copy()
    order = [name for name in monthly.sort_values("registration_month_number")["registration_month_name"].unique()]
    samples = [monthly.loc[monthly["registration_month_name"] == name, "registration_count"].to_numpy() for name in order]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.boxplot(samples, tick_labels=order, showfliers=True)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Calendar month")
    ax.set_ylabel("Recorded registrations in a year-month")
    ax.set_title("Distribution of monthly registration counts by calendar month")
    ax.tick_params(axis="x", rotation=45)
    _finish(fig, path)
    return path.name


def _normalized_month(analysis: dict, path: Path) -> str:
    rows = analysis["temporal"]["year_normalized_month"]
    if not rows:
        return ""
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(
        [row["registration_month_name"] for row in rows],
        [row["mean_within_year_share"] * 100 for row in rows],
        color=NAVY,
    )
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Calendar month")
    ax.set_ylabel("Mean share of that complete year (%)")
    ax.set_title("Within-year registration share by calendar month, complete years")
    ax.tick_params(axis="x", rotation=45)
    _finish(fig, path)
    return path.name


def _manufacturers(analysis: dict, path: Path) -> str:
    rows = list(reversed(analysis["manufacturer"]["largest"]))
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh([row["maker_clean"] for row in rows], [row["registration_count"] for row in rows], color=NAVY)
    ax.set_xlabel("Recorded registrations")
    ax.set_title("Largest manufacturers by recorded registrations")
    _finish(fig, path)
    return path.name


def _manufacturer_trends(frames: dict, analysis: dict, path: Path) -> str:
    leaders = [row["maker_clean"] for row in analysis["manufacturer"]["largest"][:5]]
    frame = frames["manufacturer_month"]
    annual = frame.groupby(["registration_year", "maker_clean"], as_index=False)["registration_count"].sum()
    totals = annual.groupby("registration_year")["registration_count"].sum()
    complete = set(analysis["complete_years"])
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for color, maker in zip(SERIES, leaders):
        subset = annual.loc[(annual["maker_clean"] == maker) & (annual["registration_year"].isin(complete))].sort_values("registration_year")
        share = subset["registration_count"] / subset["registration_year"].map(totals)
        ax.plot(subset["registration_year"], share * 100, label=maker, color=color, linewidth=1.4)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Complete registration year")
    ax.set_ylabel("Share of that year's recorded registrations (%)")
    ax.set_title("Share of recorded registrations for the five largest manufacturers")
    ax.legend(frameon=False, ncol=3)
    _finish(fig, path)
    return path.name


def _models(analysis: dict, path: Path) -> str:
    rows = list(reversed(analysis["model"]["largest_pairs"]))
    labels = [f"{row['maker_clean']} — {row['model_clean']}" for row in rows]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(labels, [row["registration_count"] for row in rows], color=NAVY)
    ax.set_xlabel("Recorded registrations")
    ax.set_title("Largest manufacturer-model pairs by recorded registrations")
    _finish(fig, path)
    return path.name


def _vehicle_shares(analysis: dict, path: Path) -> str:
    rows = analysis["vehicle_type"]["totals"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([row["type"] for row in rows], [row["registration_share"] * 100 for row in rows], color=NAVY)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of recorded registrations (%)")
    ax.set_xlabel("Source vehicle type")
    ax.set_title("Share of recorded registrations by vehicle type")
    ax.tick_params(axis="x", rotation=20)
    _finish(fig, path)
    return path.name


def _vehicle_trends(frames: dict, analysis: dict, path: Path) -> str:
    annual = frames["type_month"].groupby(["registration_year", "type"], as_index=False)["registration_count"].sum()
    complete = set(analysis["complete_years"])
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for color, vehicle_type in zip(SERIES, [row["type"] for row in analysis["vehicle_type"]["totals"]]):
        subset = annual.loc[(annual["type"] == vehicle_type) & (annual["registration_year"].isin(complete))].sort_values("registration_year")
        ax.plot(subset["registration_year"], subset["registration_count"], label=vehicle_type, color=color, linewidth=1.4)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Complete registration year")
    ax.set_ylabel("Recorded registrations")
    ax.set_title("Recorded registrations by vehicle type, complete years")
    ax.legend(frameon=False)
    _finish(fig, path)
    return path.name


def _fuel(frames: dict, analysis: dict, path: Path) -> str:
    focus = ["petrol", "greendiesel", "diesel", "hybrid_petrol", "electric", "hybrid_diesel"]
    annual = frames["fuel_month"].groupby(["registration_year", "fuel_category"], as_index=False)["registration_count"].sum()
    complete = sorted(analysis["complete_years"])
    annual = annual.loc[annual["registration_year"].isin(complete)]
    totals = annual.groupby("registration_year")["registration_count"].sum()
    other = annual.loc[~annual["fuel_category"].isin(focus)].groupby("registration_year")["registration_count"].sum()
    fig, ax = plt.subplots(figsize=(10, 4.8))
    stack = []
    labels = []
    for fuel in focus:
        subset = annual.loc[annual["fuel_category"] == fuel].set_index("registration_year")["registration_count"].reindex(complete, fill_value=0)
        stack.append((subset / totals.reindex(complete)).fillna(0).to_numpy() * 100)
        labels.append(fuel)
    remainder = (other.reindex(complete, fill_value=0) / totals.reindex(complete)).fillna(0).to_numpy() * 100
    stack.append(remainder)
    labels.append("all other source fuel codes")
    ax.stackplot(complete, stack, labels=labels, colors=SERIES[: len(stack)])
    ax.set_ylim(0, 100)
    ax.set_xlabel("Complete registration year")
    ax.set_ylabel("Share of that year's recorded registrations (%)")
    ax.set_title("Fuel-code composition of recorded registrations")
    ax.legend(frameon=False, loc="center left", bbox_to_anchor=(1.01, 0.5))
    _finish(fig, path)
    return path.name


def _ev_annual(analysis: dict, path: Path) -> str:
    rows = [row for row in analysis["electric_hybrid"]["annual"] if not row["is_partial_year"]]
    years = [row["registration_year"] for row in rows]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    axes[0].plot(years, [row["electric_registrations"] for row in rows], color=TEAL, label="Electric")
    axes[0].plot(years, [row["hybrid_registrations"] for row in rows], color=PURPLE, label="Hybrid")
    axes[0].set_ylim(bottom=0)
    axes[0].set_ylabel("Recorded registrations")
    axes[0].set_title("Electric and hybrid registrations, complete years")
    axes[0].legend(frameon=False)
    axes[1].plot(years, [row["electric_registration_share"] * 100 for row in rows], color=TEAL, label="Electric share")
    axes[1].plot(years, [row["hybrid_registration_share"] * 100 for row in rows], color=PURPLE, label="Hybrid share")
    axes[1].set_ylim(bottom=0)
    axes[1].set_ylabel("Share of that year's registrations (%)")
    axes[1].set_xlabel("Complete registration year")
    axes[1].legend(frameon=False)
    _finish(fig, path)
    return path.name


def _ev_monthly(frames: dict, path: Path) -> str:
    monthly = frames["monthly"].sort_values(["registration_year", "registration_month_number"])
    fig, ax = plt.subplots(figsize=(10, 4.8))
    positions = range(len(monthly))
    ax.plot(positions, monthly["electric_registrations"], color=TEAL, label="Electric", linewidth=1.1)
    ax.plot(positions, monthly["hybrid_registrations"], color=PURPLE, label="Hybrid", linewidth=1.1)
    ax.set_ylim(bottom=0)
    _year_ticks(ax, monthly)
    ax.set_ylabel("Recorded registrations")
    ax.set_title("Monthly electric and hybrid registrations")
    ax.legend(frameon=False)
    _finish(fig, path)
    return path.name


def _states(analysis: dict, path: Path) -> str:
    rows = list(reversed(analysis["state_channel"]["all_channels"]))
    colors = [CLAY if row["state_category"] == CHANNEL_STATE else NAVY for row in rows]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh([row["state_category"] for row in rows], [row["registration_count"] for row in rows], color=colors)
    ax.set_xlabel("Recorded registrations")
    ax.set_title("Recorded registrations by state or registration channel")
    _finish(fig, path)
    return path.name


def _geographic(analysis: dict, path: Path) -> str:
    rows = list(reversed(analysis["state_channel"]["geographic_offices"]))
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh([row["state_category"] for row in rows], [row["registration_count"] for row in rows], color=NAVY)
    ax.set_xlabel("Recorded registrations")
    ax.set_title("Registration offices, excluding Rakan Niaga")
    fig.text(0.01, 0.01, "This chart excludes the Rakan Niaga channel and is not the national total.", fontsize=8, color=SLATE)
    _finish(fig, path)
    return path.name


def _rakan(analysis: dict, path: Path) -> str:
    rows = analysis["state_channel"]["rakan_niaga_by_year"]
    if not rows:
        return ""
    complete = [row for row in rows if not row["is_partial_year"]]
    partial = [row for row in rows if row["is_partial_year"]]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    if complete:
        ax.plot(
            [row["registration_year"] for row in complete],
            [row["registration_share"] * 100 for row in complete],
            color=CLAY,
            linewidth=1.4,
            label="Complete year",
        )
    if partial:
        ax.scatter(
            [row["registration_year"] for row in partial],
            [row["registration_share"] * 100 for row in partial],
            color=CLAY,
            marker="o",
            facecolors="none",
            s=40,
            label="Partial year",
            zorder=3,
        )
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Registration year")
    ax.set_ylabel("Share of that year's recorded registrations (%)")
    ax.set_title("Rakan Niaga share of recorded registrations")
    ax.legend(frameon=False)
    _finish(fig, path)
    return path.name


def _concentration(analysis: dict, path: Path) -> str:
    rows = analysis["manufacturer"]["cumulative_share"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar([f"Top {row['k']}" for row in rows], [row["share"] * 100 for row in rows], color=NAVY)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of recorded registrations (%)")
    ax.set_title("Cumulative manufacturer share of recorded registrations")
    _finish(fig, path)
    return path.name


def _year_ticks(ax: plt.Axes, monthly: pd.DataFrame) -> None:
    years = monthly["registration_year"].to_numpy()
    positions = []
    labels = []
    seen = set()
    for index, year in enumerate(years):
        if int(year) not in seen and int(year) % 2 == 0:
            positions.append(index)
            labels.append(str(int(year)))
            seen.add(int(year))
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=45)
    ax.set_xlabel("Registration month")


def _finish(fig: plt.Figure, path: Path) -> None:
    for axis in fig.axes:
        axis.grid(axis="y", alpha=0.25)
        axis.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)

"""Render the Phase 4 report from computed results. Numbers are not typed in by hand."""

from __future__ import annotations


def render_report(analysis: dict, chart_names: list[str]) -> str:
    overview = analysis["overview"]
    temporal = analysis["temporal"]
    like = temporal["like_for_like"]
    lines = [
        "# Phase 4 — exploratory data analysis and statistical analysis",
        "",
        f"Status: **{analysis['status']}**",
        "",
        "## 1. Objective",
        "",
        "The question for this phase is which patterns, distributions, and differences are visible in Malaysian vehicle registration transactions.",
        "The results are a base for later forecasting, anomaly detection, and BI. This phase does not forecast, score anomalies, or build a dashboard.",
        "",
        "## 2. Dataset",
        "",
        "The source is the official JPJ car registration transaction file published through data.gov.my.",
        "Phase 4 reads the Phase 3 DuckDB views, which read the processed Parquet files. Raw files and processed files are not rewritten.",
        "",
        f"- Recorded registrations: {_int(overview['registration_count'])}",
        f"- Earliest registration date: {overview['minimum_date']}",
        f"- Latest registration date: {overview['maximum_date']}",
        f"- Registration years: {overview['registration_years']}",
        f"- Observed months: {overview['observed_months']}",
        f"- Manufacturers (`maker_clean`): {overview['manufacturers']}",
        f"- Model names (`model_clean`): {overview['model_names']}",
        f"- Manufacturer-model pairs: {overview['manufacturer_model_pairs']}",
        f"- Fuel categories: {overview['fuel_categories']}",
        f"- Vehicle types: {overview['vehicle_types']}",
        f"- State/channel categories: {overview['state_channels']}",
        f"- Electric registrations: {_int(overview['electric_registrations'])}",
        f"- Hybrid registrations: {_int(overview['hybrid_registrations'])}",
        f"- Of the hybrid registrations, hybrid_petrol is {_int(overview['hybrid_petrol_registrations'])} and hybrid_diesel is {_int(overview['hybrid_diesel_registrations'])}",
        "",
        "A row is one registration transaction. Registration counts are not vehicle sales, purchases, customers, revenue, or a direct measure of demand.",
        "",
        "## 3. Methodology",
        "",
        "DuckDB aggregates the Phase 3 views. Python receives those aggregates. The registration fact is not loaded into pandas.",
        "Descriptive shares are group registrations divided by all recorded registrations in the stated period. The name used here is share of recorded registrations.",
        "The Herfindahl-Hirschman index (HHI) is the sum of squared shares. Equal shares across n groups give 1/n. A single group gives 1. The 0–10,000 scale is the same index multiplied by 10,000. It describes concentration of recorded registrations. It is not a sales-market definition.",
        f"The primary tests use a Bonferroni adjustment. The family size is {analysis['multiple_testing']['family_size']} and the adjusted threshold is {_p(analysis['multiple_testing']['alpha_adjusted'])}.",
        "The observation in the month and year tests is a month or a complete year. That choice avoids treating the census of transactions as if each row were an independent draw.",
        "The chi-square test does count transactions. Its p-value is therefore easy to make small, and the report reads Cramér's V and the share changes alongside it.",
        "Effect-size labels use conventional benchmarks as a reading aid: epsilon-squared cuts at 0.01, 0.06, and 0.14; absolute Spearman rho cuts at 0.10, 0.30, and 0.50; Cramér's V cuts depend on the smaller degrees of freedom.",
        "",
        "## 4. Temporal findings",
        "",
        _temporal_section(analysis),
        "",
        "## 5. Manufacturer findings",
        "",
        _manufacturer_section(analysis),
        "",
        "## 6. Model findings",
        "",
        _model_section(analysis),
        "",
        "## 7. Vehicle-type findings",
        "",
        _vehicle_section(analysis),
        "",
        "## 8. Fuel findings",
        "",
        _fuel_section(analysis),
        "",
        "## 9. EV and hybrid findings",
        "",
        _electric_section(analysis),
        "",
        "## 10. State and channel findings",
        "",
        _state_section(analysis),
        "",
        "## 11. Statistical tests",
        "",
        _tests_section(analysis),
        "",
        "## 12. Key evidence-based findings",
        "",
        _findings_section(analysis),
        "",
        "## 13. Limitations",
        "",
        "- Registration transactions are not vehicle sales, purchases, customers, revenue, or a direct measure of demand.",
        "- `date_reg` may differ from a purchase date.",
        "- The latest year is partial when it ends before 31 December. Full-year change for that year is withheld. This phase does not extrapolate it.",
        "- Rakan Niaga is a registration channel. It is not a geographic state. Geographic charts exclude it and are not the national total. National totals keep it.",
        "- Unknown, other, and the source fuel categories remain. `greendiesel` is kept apart from `diesel`.",
        "- Months with unusually low recorded volume remain in the primary statistics. The dataset does not establish why they are low.",
        "- Correlation and association do not establish causation.",
        "- A p-value below 0.05 does not, by itself, make a difference practically important. Several tests use a large census of transactions or a long run of years.",
        "- High and low monthly counts marked in this phase are EDA observations. They are not confirmed anomalies.",
        "",
        "## 14. Implications for Phase 5",
        "",
    ]
    for note in analysis["phase5"]:
        lines.append(f"- {note}")
    lines.extend(["", "## Charts", ""])
    for name in chart_names:
        lines.append(f"- `figures/{name}`")
    lines.append("")
    return "\n".join(lines)


def _temporal_section(analysis: dict) -> str:
    temporal = analysis["temporal"]
    descriptive = temporal["monthly_descriptive"]
    held_out = temporal["monthly_descriptive_excluding_low_volume"]
    like = temporal["like_for_like"]
    low = temporal["low_volume_months"]
    low_text = ", ".join(f"{item['registration_year_month']} ({_int(item['registration_count'])})" for item in low) or "none"
    yearly_lines = [
        "| Year | Recorded registrations | Full-year absolute change | Full-year percentage change | Basis |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in temporal["yearly"]:
        yearly_lines.append(
            "| {year} | {count} | {absolute} | {percent} | {basis} |".format(
                year=row["registration_year"],
                count=_int(row["registration_count"]),
                absolute=_optional_int(row["yoy_absolute_change"]),
                percent=_optional_pct(row["yoy_percentage_change"]),
                basis=row["yoy_basis"],
            )
        )
    partial = ", ".join(str(year) for year in analysis["partial_years"]) or "none"
    return "\n".join(
        [
            f"Observed months: {descriptive['n']}. Mean monthly registrations: {_num(descriptive['mean'])}. Median: {_num(descriptive['median'])}. Standard deviation of the observed months: {_num(descriptive['std'])}.",
            f"Lowest month in the series and highest month in the series are identified from these {descriptive['n']} months. Coefficient of variation: {_num(temporal['coefficient_of_variation'])}.",
            f"Months below 10% of the median monthly count: {low_text}.",
            "These months have unusually low recorded registration volume and may materially affect aggregate statistics. The dataset does not establish why they are low.",
            f"Keeping them, the mean is {_num(descriptive['mean'])} and the standard deviation is {_num(descriptive['std'])}. Setting them aside only as a sensitivity check, the mean is {_num(held_out['mean'])} and the standard deviation is {_num(held_out['std'])}. The primary figures keep them.",
            f"Median month-to-month percentage change: {_optional_pct(temporal['month_to_month_median_change'])}. The largest month-to-month decline lands on {temporal['month_to_month_minimum_month']}.",
            f"Partial registration years: {partial}. Full-year percentage change is withheld for those years.",
            (
                f"Like-for-like comparison: January-{like['through_month_name']} {like['latest_year']} has {_int(like['latest_period_registrations'])} recorded registrations, "
                f"against {_int(like['prior_period_registrations'])} in January-{like['through_month_name']} {like['prior_year']}. "
                f"Absolute change: {_optional_int(like['yoy_absolute_change'])}. Percentage change: {_optional_pct(like['yoy_percentage_change'])}. "
                "This is not a full-year comparison."
            ),
            f"The coefficient of variation of the mean within-year month shares, using complete years only, is {_num(temporal['year_normalized_coefficient_of_variation'])}.",
            "Calendar-month averages and the Kruskal-Wallis test below are the evidence about a repeating month pattern. The word seasonality is not used as a label for that evidence.",
            "",
            *yearly_lines,
        ]
    )


def _manufacturer_section(analysis: dict) -> str:
    block = analysis["manufacturer"]
    like = analysis["temporal"]["like_for_like"]
    lines = [
        f"Manufacturers: {block['manufacturers']}. Top 5 share of recorded registrations: {_pct(block['top_5_share'])}. Top 10 share: {_pct(block['top_10_share'])}.",
        f"HHI: {_num(block['hhi'])} ({_num(block['hhi'] * 10000)} on a 0–10,000 scale).",
        f"The January-{analysis['temporal']['like_for_like']['through_month_name']} comparison below is for the ten largest manufacturers. A blank percentage means the prior window has no recorded registrations for that manufacturer.",
        "",
        "| Manufacturer | Recorded registrations | Share |",
        "| --- | ---: | ---: |",
    ]
    for row in block["largest"]:
        lines.append(f"| {row['maker_clean']} | {_int(row['registration_count'])} | {_pct(row['registration_share'])} |")
    lines.extend(
        [
            "",
            f"| Manufacturer | Jan-{like['through_month_name'][:3]} {like['prior_year']} | Jan-{like['through_month_name'][:3]} {like['latest_year']} | Absolute change | Percentage change |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in block["like_for_like"]:
        lines.append(
            f"| {row['maker_clean']} | {_int(row['prior_period_registrations'])} | {_int(row['latest_period_registrations'])} | {_optional_int(row['yoy_absolute_change'])} | {_optional_pct(row['yoy_percentage_change'])} |"
        )
    lines.extend(["", "Largest electric registration counts, with each manufacturer's electric share of its own registrations:", ""])
    lines.extend(_pair_table(block["electric_leaders"], "electric_registrations", "electric_registration_share"))
    lines.extend(["", "Largest hybrid registration counts:", ""])
    lines.extend(_pair_table(block["hybrid_leaders"], "hybrid_registrations", "hybrid_registration_share"))
    return "\n".join(lines)


def _model_section(analysis: dict) -> str:
    block = analysis["model"]
    lines = [
        f"Model names: {block['model_names']}. Manufacturer-model pairs: {block['manufacturer_model_pairs']}.",
        f"Model names that appear under more than one manufacturer: {block['model_names_with_multiple_manufacturers']}. Counts below keep `maker_clean` with `model_clean`.",
        f"Top 10 manufacturer-model pairs account for {_pct(block['top_10_share'])} of recorded registrations. Pair HHI: {_num(block['hhi'])}.",
        "",
        "| Manufacturer | Model | Recorded registrations | Share |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in block["largest_pairs"]:
        lines.append(
            f"| {row['maker_clean']} | {row['model_clean']} | {_int(row['registration_count'])} | {_pct(row['registration_share'])} |"
        )
    lines.extend(["", "Largest electric manufacturer-model pairs:", "", "| Manufacturer | Model | Electric registrations |", "| --- | --- | ---: |"])
    for row in block["electric_pairs"]:
        lines.append(f"| {row['maker_clean']} | {row['model_clean']} | {_int(row['electric_registrations'])} |")
    lines.extend(["", "Largest hybrid manufacturer-model pairs:", "", "| Manufacturer | Model | Hybrid registrations |", "| --- | --- | ---: |"])
    for row in block["hybrid_pairs"]:
        lines.append(f"| {row['maker_clean']} | {row['model_clean']} | {_int(row['hybrid_registrations'])} |")
    return "\n".join(lines)


def _vehicle_section(analysis: dict) -> str:
    lines = [
        f"Vehicle-type HHI: {_num(analysis['vehicle_type']['hhi'])}. Shares use the national registration total.",
        "",
        "| Vehicle type | Recorded registrations | Share |",
        "| --- | ---: | ---: |",
    ]
    for row in analysis["vehicle_type"]["totals"]:
        lines.append(f"| {row['type']} | {_int(row['registration_count'])} | {_pct(row['registration_share'])} |")
    lines.append("")
    lines.append("Yearly type counts for complete years are in the vehicle-type trend chart. The partial year is omitted from that line chart.")
    return "\n".join(lines)


def _fuel_section(analysis: dict) -> str:
    fuel = analysis["fuel"]
    lines = [
        f"`greendiesel` registrations: {_int(fuel['greendiesel_registrations'])}. `diesel` registrations: {_int(fuel['diesel_registrations'])}. These codes are not combined.",
        f"Fuel-category HHI: {_num(fuel['hhi'])}. A high value means the counts concentrate in few source codes, which the table shows directly.",
        "",
        "| Fuel category | Recorded registrations | Share |",
        "| --- | ---: | ---: |",
    ]
    for row in fuel["totals"]:
        lines.append(f"| {row['fuel_category']} | {_int(row['registration_count'])} | {_pct(row['registration_share'])} |")
    if fuel["period_years"]:
        earlier = fuel["period_years"]["earlier"]
        recent = fuel["period_years"]["recent"]
        lines.extend(
            [
                "",
                f"Share of recorded registrations in {earlier[0]}-{earlier[-1]} and {recent[0]}-{recent[-1]}. The change is in percentage points.",
                "",
                "| Fuel category | Earlier share | Recent share | Percentage-point change |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        ordered = sorted(fuel["period_comparison"], key=lambda row: abs(row["share_point_change"] or 0), reverse=True)
        for row in ordered:
            lines.append(
                f"| {row['fuel_category']} | {_pct(row['earlier_share'])} | {_pct(row['recent_share'])} | {_points(row['share_point_change'])} |"
            )
    return "\n".join(lines)


def _electric_section(analysis: dict) -> str:
    block = analysis["electric_hybrid"]
    like = analysis["temporal"]["like_for_like"]
    lines = [
        f"Electric registrations: {_int(block['electric_registrations'])}. Hybrid registrations: {_int(block['hybrid_registrations'])}.",
        f"Hybrid registrations consist of {_int(block['hybrid_petrol_registrations'])} hybrid_petrol and {_int(block['hybrid_diesel_registrations'])} hybrid_diesel.",
        f"The first complete year with an electric registration is {block['first_complete_year_with_electric']}.",
        f"In {block['latest_complete_year']}, the electric share of that year's recorded registrations is {_pct(block['latest_complete_electric_share'])} and the hybrid share is {_pct(block['latest_complete_hybrid_share'])}.",
        (
            f"January-{like['through_month_name']} {like['latest_year']} electric registrations: {_int(like['latest_period_electric_registrations'])}, "
            f"against {_int(like['prior_period_electric_registrations'])} in January-{like['through_month_name']} {like['prior_year']}."
        ),
        (
            f"January-{like['through_month_name']} {like['latest_year']} hybrid registrations: {_int(like['latest_period_hybrid_registrations'])}, "
            f"against {_int(like['prior_period_hybrid_registrations'])} in January-{like['through_month_name']} {like['prior_year']}."
        ),
        "These shares are shares of recorded registrations classified as electric or hybrid. They are not described here as consumer adoption.",
        "",
        "Electric registrations by state or channel, and by manufacturer, are in the state table and the manufacturer section.",
    ]
    return "\n".join(lines)


def _state_section(analysis: dict) -> str:
    block = analysis["state_channel"]
    lines = [
        f"National recorded registrations, including Rakan Niaga: {_int(block['national_registration_count'])}.",
        f"Rakan Niaga registrations: {_int(block['rakan_niaga_registrations'])} ({_pct(block['rakan_niaga_share'])} of the national total).",
        f"Geographic registration offices, excluding Rakan Niaga: {_int(block['geographic_registration_count'])}. This subtotal is not the national total.",
        f"HHI across all channels: {_num(block['hhi_all_channels'])}. HHI across geographic offices only: {_num(block['hhi_geographic_offices'])}.",
        "",
        "| State or channel | Recorded registrations | Share of national total | Electric registrations | Electric share of this category | Hybrid registrations |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in block["all_channels"]:
        lines.append(
            "| {name} | {count} | {share} | {electric} | {electric_share} | {hybrid} |".format(
                name=row["state_category"],
                count=_int(row["registration_count"]),
                share=_pct(row["registration_share"]),
                electric=_int(row["electric_registrations"]),
                electric_share=_pct(row["electric_registration_share"]),
                hybrid=_int(row["hybrid_registrations"]),
            )
        )
    lines.extend(
        [
            "",
            "Geographic offices only. Shares in this second table use the geographic subtotal as the denominator.",
            "",
            "| Registration office | Recorded registrations | Share of geographic subtotal |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in block["geographic_offices"]:
        lines.append(
            f"| {row['state_category']} | {_int(row['registration_count'])} | {_pct(row.get('geographic_share'))} |"
        )
    return "\n".join(lines)


def _tests_section(analysis: dict) -> str:
    blocks = []
    for test in analysis["tests"]:
        interval = test.get("confidence_interval")
        if interval and interval[0] is not None:
            interval_text = f"[{_num(interval[0])}, {_num(interval[1])}]"
        else:
            interval_text = "not calculated"
        blocks.append(
            "\n".join(
                [
                    f"### {test['test']}: {test['id']}",
                    "",
                    f"- Research question: {test['research_question']}",
                    f"- Null hypothesis: {test['null_hypothesis']}",
                    f"- Alternative hypothesis: {test['alternative_hypothesis']}",
                    f"- Variables: {test['variables']}",
                    f"- Test: {test['test']}",
                    f"- Assumptions: {test['assumptions']}",
                    f"- Sample size: {test.get('sample_size')}",
                    f"- Statistic: {_num(test.get('statistic'))}",
                    f"- p-value: {_p(test.get('p_value'))}",
                    f"- Bonferroni-adjusted p-value: {_p(test.get('p_value_adjusted'))}",
                    f"- Effect size ({test.get('effect_size_name')}): {_num(test.get('effect_size'))} ({test.get('effect_size_label')})",
                    f"- Confidence interval: {interval_text}",
                    f"- Result: {test.get('conclusion')}",
                    f"- Interpretation: {test.get('interpretation')}",
                    f"- Limitation: {test['limitation']}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _findings_section(analysis: dict) -> str:
    overview = analysis["overview"]
    like = analysis["temporal"]["like_for_like"]
    manufacturer = analysis["manufacturer"]
    electric = analysis["electric_hybrid"]
    fuel = analysis["fuel"]
    descriptive = [
        f"Descriptive finding: the analytical layer contains {_int(overview['registration_count'])} recorded registrations from {overview['minimum_date']} through {overview['maximum_date']}.",
        (
            f"Descriptive finding: January-{like['through_month_name']} {like['latest_year']} has {_int(like['latest_period_registrations'])} recorded registrations, "
            f"compared with {_int(like['prior_period_registrations'])} in January-{like['through_month_name']} {like['prior_year']} "
            f"({_optional_pct(like['yoy_percentage_change'])}). Full-year {like['latest_year']} is not compared with full-year {like['prior_year']}."
        ),
        f"Descriptive finding: the five largest manufacturers account for {_pct(manufacturer['top_5_share'])} of recorded registrations, and the ten largest account for {_pct(manufacturer['top_10_share'])}.",
        f"Descriptive finding: petrol, greendiesel, and diesel remain separate. greendiesel has {_int(fuel['greendiesel_registrations'])} registrations and diesel has {_int(fuel['diesel_registrations'])}.",
        (
            f"Descriptive finding: {_int(electric['electric_registrations'])} registrations are classified as electric and {_int(electric['hybrid_registrations'])} as hybrid. "
            f"In {electric['latest_complete_year']}, those shares of that year's registrations are {_pct(electric['latest_complete_electric_share'])} and {_pct(electric['latest_complete_hybrid_share'])}."
        ),
        (
            f"Descriptive finding: Rakan Niaga accounts for {_pct(analysis['state_channel']['rakan_niaga_share'])} of national recorded registrations "
            f"and is reported apart from geographic offices."
        ),
    ]
    statistical = []
    for test in analysis["tests"]:
        if not test.get("primary"):
            continue
        statistical.append(f"Statistical finding ({test['id']}): {test.get('conclusion')}")
    interpretation = [
        "Interpretation: the concentration figures describe how recorded registrations are distributed across manufacturers, model pairs, fuel codes, and channels. They do not identify a sales leader or a cause.",
        "Interpretation: where a test rejects its null hypothesis, the effect-size label is the guide to whether the difference is large enough to matter for a later model. The p-value alone is not that guide.",
    ]
    return "\n".join(f"- {line}" for line in descriptive + statistical + interpretation)


def _pair_table(rows: list[dict], count_key: str, share_key: str) -> list[str]:
    lines = ["| Manufacturer | Registrations in this class | Share of that manufacturer's registrations |", "| --- | ---: | ---: |"]
    for row in rows:
        lines.append(f"| {row['maker_clean']} | {_int(row[count_key])} | {_pct(row[share_key])} |")
    return lines


def _int(value: object) -> str:
    return f"{int(value):,}"


def _optional_int(value: object) -> str:
    if value is None:
        return ""
    return _int(value)


def _num(value: object) -> str:
    if value is None:
        return "not available"
    number = float(value)
    return f"{number:,.4g}" if abs(number) < 1000 else f"{number:,.1f}"


def _pct(value: object) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}%"


def _optional_pct(value: object) -> str:
    if value is None:
        return ""
    return _pct(value)


def _points(value: object) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}"


def _p(value: object) -> str:
    if value is None:
        return "not calculated"
    number = float(value)
    if number < 0.001:
        return f"{number:.3e}"
    return f"{number:.4f}"

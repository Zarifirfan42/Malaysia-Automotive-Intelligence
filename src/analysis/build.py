"""Run Phase 4 from the Phase 3 DuckDB views and write the report."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analysis.analyze import analyze
from src.analysis.charts import save_charts
from src.analysis.extract import extract
from src.analysis.report import render_report
from src.config import (
    ANALYSIS_DIR,
    PHASE3_REPORT_JSON,
    PHASE4_FIGURES_DIR,
    PHASE4_REPORT_MD,
    PHASE4_RESULTS_JSON,
)

logger = logging.getLogger(__name__)


def run_phase4(
    *,
    database_path: Path | None = None,
    analysis_dir: Path | None = None,
    report_path: Path | None = None,
    figures_dir: Path | None = None,
    phase3_report_path: Path | None = None,
) -> dict[str, Any]:
    """Aggregate the analytical views, test a pre-specified set of questions, and write the report."""
    started = time.perf_counter()
    output_dir = ANALYSIS_DIR if analysis_dir is None else analysis_dir
    report_file = PHASE4_REPORT_MD if report_path is None else report_path
    figure_dir = PHASE4_FIGURES_DIR if figures_dir is None else figures_dir
    baseline = PHASE3_REPORT_JSON if phase3_report_path is None else phase3_report_path
    frames = extract(database_path)
    result = analyze(frames)
    result["phase3_fact_rows"] = _phase3_rows(baseline)
    if result["phase3_fact_rows"] is not None and result["phase3_fact_rows"] != result["overview"]["registration_count"]:
        result["status"] = "FAIL"
    chart_names = save_charts(frames, result, figure_dir)
    result["charts"] = chart_names
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    _write_tables(output_dir, result)
    _write_json(output_dir / PHASE4_RESULTS_JSON.name, result)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(render_report(result, chart_names), encoding="utf-8")
    logger.info("Phase 4 %s in %.1f seconds.", result["status"], result["elapsed_seconds"])
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 for PASS or WARN, and 1 for FAIL."""
    parser = argparse.ArgumentParser(
        prog="python -m src.analysis",
        description="Phase 4: exploratory and statistical analysis of the DuckDB registration views.",
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_phase4()
    return 0 if result["status"] in {"PASS", "WARN"} else 1


def _phase3_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return int(json.load(handle)["phase3_fact_rows"])


def _write_tables(directory: Path, result: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _frame(result["temporal"]["yearly"]).to_csv(directory / "yearly.csv", index=False)
    _frame(result["manufacturer"]["largest"]).to_csv(directory / "manufacturers_top.csv", index=False)
    _frame(result["model"]["largest_pairs"]).to_csv(directory / "models_top.csv", index=False)
    _frame(result["fuel"]["totals"]).to_csv(directory / "fuel_totals.csv", index=False)
    _frame(result["vehicle_type"]["totals"]).to_csv(directory / "vehicle_types.csv", index=False)
    _frame(result["state_channel"]["all_channels"]).to_csv(directory / "state_channel.csv", index=False)
    _frame(result["temporal"]["calendar_month"]).to_csv(directory / "calendar_month.csv", index=False)


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _write_json(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, default=_json_default)
        handle.write("\n")


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if not np.isfinite(value):
            return None
        return float(value)
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Cannot serialize {type(value).__name__}")

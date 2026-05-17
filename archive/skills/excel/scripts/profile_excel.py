#!/usr/bin/env python3
import argparse
import json
import math
import os
import pathlib
from datetime import datetime
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")


def _safe_name(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:80] or "sheet"


def _json_default(value: Any):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return str(value)


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:,.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str], limit: int = 10) -> str:
    if not rows:
        return ""
    selected = rows[:limit]
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in selected:
        body.append("| " + " | ".join(_format_value(row.get(col)) for col in columns) + " |")
    return "\n".join([header, sep, *body])


def _pct(count: int | float, total: int | float) -> str:
    if not total:
        return "0.0%"
    return f"{(count / total * 100):.1f}%"


def _is_numeric(series) -> bool:
    return str(series.dtype).startswith(("int", "float"))


def _save_bar_chart(series, title: str, path: pathlib.Path, xlabel: str = "Count") -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    counts = series.dropna().astype(str).value_counts().head(12)
    if counts.empty:
        return None
    fig = plt.figure(figsize=(11, 6))
    counts.sort_values().plot(kind="barh", color="#2563eb")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"title": title, "path": str(path)}


def _save_boolean_chart(series, title: str, path: pathlib.Path) -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    counts = series.fillna("Unknown").astype(str).value_counts()
    if counts.empty:
        return None
    fig = plt.figure(figsize=(8, 5))
    counts.plot(kind="bar", color=["#16a34a", "#dc2626", "#64748b"][: len(counts)])
    plt.title(title)
    plt.xlabel("")
    plt.ylabel("Tickets")
    plt.xticks(rotation=0)
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"title": title, "path": str(path)}


def _save_monthly_volume(df, date_col: str, title: str, path: pathlib.Path) -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    dates = df[date_col].dropna()
    if dates.empty:
        return None
    monthly = dates.dt.to_period("M").value_counts().sort_index()
    monthly.index = monthly.index.astype(str)
    fig = plt.figure(figsize=(12, 6))
    monthly.plot(kind="line", marker="o", color="#7c3aed", linewidth=2)
    plt.title(title)
    plt.xlabel("Month")
    plt.ylabel("Tickets")
    plt.xticks(rotation=45, ha="right")
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"title": title, "path": str(path)}


def _save_grouped_bar(data, title: str, path: pathlib.Path, ylabel: str = "Value") -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    if data is None or len(data) == 0:
        return None
    fig = plt.figure(figsize=(10, 6))
    data.plot(kind="bar", color="#0891b2")
    plt.title(title)
    plt.xlabel("")
    plt.ylabel(ylabel)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"title": title, "path": str(path)}


def _save_rate_bar(data, title: str, path: pathlib.Path, ylabel: str = "Rate") -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    if data is None or len(data) == 0:
        return None
    fig = plt.figure(figsize=(11, 6))
    data.sort_values().plot(kind="barh", color="#db2777")
    plt.title(title)
    plt.xlabel(ylabel)
    plt.ylabel("")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"title": title, "path": str(path)}


def _true_mask(series):
    return series.astype(str).str.lower().isin(["true", "1", "yes", "y"])


def _profile_sheet(df, sheet_name: str) -> dict[str, Any]:
    columns = []
    for col in df.columns:
        series = df[col]
        missing = int(series.isna().sum())
        non_null = int(series.notna().sum())
        col_info: dict[str, Any] = {
            "name": str(col),
            "dtype": str(series.dtype),
            "non_null": non_null,
            "missing": missing,
            "missing_pct": round((missing / len(df) * 100) if len(df) else 0, 2),
        }
        if non_null:
            if str(series.dtype).startswith(("int", "float")):
                desc = series.describe()
                col_info.update(
                    {
                        "min": _json_default(desc.get("min")),
                        "max": _json_default(desc.get("max")),
                        "mean": _json_default(desc.get("mean")),
                        "median": _json_default(series.median()),
                    }
                )
            else:
                top = series.dropna().astype(str).value_counts().head(5)
                col_info["top_values"] = top.to_dict()
        columns.append(col_info)

    return {
        "sheet": sheet_name,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_profiles": columns,
        "preview": df.head(8).where(df.notna(), None).to_dict(orient="records"),
    }


def _sheet_findings(profile: dict[str, Any]) -> list[str]:
    findings = [
        f"`{profile['sheet']}` contains {profile['rows']:,} rows across {profile['columns']:,} columns."
    ]
    missing_cols = sorted(
        [col for col in profile["column_profiles"] if col["missing"] > 0],
        key=lambda col: col["missing_pct"],
        reverse=True,
    )
    if missing_cols:
        top = missing_cols[0]
        findings.append(
            f"Highest missingness is `{top['name']}` at {top['missing_pct']}% ({top['missing']:,} blanks)."
        )
    numeric_cols = [col for col in profile["column_profiles"] if "mean" in col]
    if numeric_cols:
        col = numeric_cols[0]
        findings.append(
            f"`{col['name']}` ranges from {col['min']} to {col['max']} with a mean of {col['mean']}."
        )
    ignored = {"request id", "id", "email", "requester", "subject", "resolution"}
    categorical_cols = [
        col
        for col in profile["column_profiles"]
        if col.get("top_values") and str(col["name"]).strip().lower() not in ignored
    ]
    if categorical_cols:
        col = categorical_cols[0]
        top_values = list(col["top_values"].items())[:3]
        if top_values:
            formatted = ", ".join(f"{k} ({v:,})" for k, v in top_values)
            findings.append(f"Most common `{col['name']}` values are {formatted}.")
    return findings


def _ticket_deep_analysis(df, sheet_name: str, assets_dir: pathlib.Path) -> tuple[list[str], list[dict[str, Any]], list[dict[str, str]]]:
    """Create ticket-specific findings, report sections, and charts when common ticket columns exist."""
    import pandas as pd
    import matplotlib.pyplot as plt

    plt.style.use("seaborn-v0_8")
    safe_sheet = _safe_name(sheet_name)
    total = len(df)
    charts: list[dict[str, str]] = []
    sections: list[dict[str, Any]] = []
    findings: list[str] = []

    for col in ["Created Time", "Resolved Time", "Responded Date", "DueBy Time", "Response DueBy Time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    def add_chart(chart: dict[str, str] | None):
        if chart:
            charts.append(chart)
            return chart
        return None

    request_type_chart = add_chart(
        _save_bar_chart(
            df["Request Type"],
            "Ticket Mix by Request Type",
            assets_dir / f"{safe_sheet}-request-type.png",
        )
        if "Request Type" in df.columns
        else None
    )
    status_chart = add_chart(
        _save_bar_chart(
            df["Request Status"],
            "Ticket Status Distribution",
            assets_dir / f"{safe_sheet}-status.png",
        )
        if "Request Status" in df.columns
        else None
    )
    priority_chart = add_chart(
        _save_bar_chart(
            df["Priority"],
            "Ticket Priority Distribution",
            assets_dir / f"{safe_sheet}-priority.png",
        )
        if "Priority" in df.columns
        else None
    )
    category_chart = add_chart(
        _save_bar_chart(
            df["Category"],
            "Top Ticket Categories",
            assets_dir / f"{safe_sheet}-category.png",
        )
        if "Category" in df.columns
        else None
    )
    group_chart = add_chart(
        _save_bar_chart(
            df["Group"],
            "Ticket Volume by Support Group",
            assets_dir / f"{safe_sheet}-group.png",
        )
        if "Group" in df.columns
        else None
    )
    monthly_chart = add_chart(
        _save_monthly_volume(
            df,
            "Created Time",
            "Monthly Ticket Volume",
            assets_dir / f"{safe_sheet}-monthly-volume.png",
        )
        if "Created Time" in df.columns
        else None
    )
    overdue_chart = add_chart(
        _save_boolean_chart(
            df["Overdue Status"],
            "SLA Resolution Overdue Status",
            assets_dir / f"{safe_sheet}-sla-overdue.png",
        )
        if "Overdue Status" in df.columns
        else None
    )
    response_overdue_chart = add_chart(
        _save_boolean_chart(
            df["First Response Overdue Status"],
            "First Response Overdue Status",
            assets_dir / f"{safe_sheet}-first-response-overdue.png",
        )
        if "First Response Overdue Status" in df.columns
        else None
    )

    overdue_by_group_chart = None
    if {"Group", "Overdue Status"}.issubset(df.columns):
        by_group = (
            _true_mask(df["Overdue Status"])
            .groupby(df["Group"].fillna("Unknown").astype(str))
            .mean()
            .mul(100)
            .sort_values(ascending=False)
            .head(12)
        )
        overdue_by_group_chart = add_chart(
            _save_rate_bar(
                by_group,
                "SLA Overdue Rate by Support Group",
                assets_dir / f"{safe_sheet}-sla-overdue-rate-by-group.png",
                ylabel="Overdue rate (%)",
            )
        )

    response_by_priority_chart = None
    if {"Priority", "First Response Overdue Status"}.issubset(df.columns):
        by_priority = (
            _true_mask(df["First Response Overdue Status"])
            .groupby(df["Priority"].fillna("Unknown").astype(str))
            .mean()
            .mul(100)
            .sort_values(ascending=False)
        )
        response_by_priority_chart = add_chart(
            _save_rate_bar(
                by_priority,
                "First Response Overdue Rate by Priority",
                assets_dir / f"{safe_sheet}-first-response-overdue-rate-by-priority.png",
                ylabel="Overdue rate (%)",
            )
        )

    resolution_chart = None
    if {"Created Time", "Resolved Time", "Priority"}.issubset(df.columns):
        resolved = df.dropna(subset=["Created Time", "Resolved Time"]).copy()
        if not resolved.empty:
            resolved["resolution_hours"] = (
                resolved["Resolved Time"] - resolved["Created Time"]
            ).dt.total_seconds() / 3600
            medians = resolved.groupby("Priority")["resolution_hours"].median().sort_values(ascending=False)
            resolution_chart = add_chart(
                _save_grouped_bar(
                    medians,
                    "Median Resolution Hours by Priority",
                    assets_dir / f"{safe_sheet}-resolution-hours-by-priority.png",
                    ylabel="Hours",
                )
            )

    if total:
        findings.append(f"The workbook contains {total:,} ticket records in `{sheet_name}`.")

    if "Request Type" in df.columns:
        request_counts = df["Request Type"].value_counts()
        top_type = request_counts.index[0]
        findings.append(
            f"`{top_type}` is the largest request type with {request_counts.iloc[0]:,} tickets ({_pct(request_counts.iloc[0], total)})."
        )
        sections.append(
            {
                "title": "Ticket Mix",
                "bullets": [
                    f"Total tickets analyzed: {total:,}.",
                    "Request types are broadly balanced across the dataset." if len(request_counts) > 1 and request_counts.max() / total < 0.4 else f"`{top_type}` dominates the ticket mix.",
                    "Use the request-type mix to size separate incident, request, and change management workflows.",
                ],
                "charts": [request_type_chart],
            }
        )

    if "Created Time" in df.columns and df["Created Time"].notna().any():
        monthly = df["Created Time"].dt.to_period("M").value_counts().sort_index()
        peak_month = str(monthly.idxmax())
        findings.append(f"Peak monthly volume occurred in {peak_month} with {monthly.max():,} tickets.")
        sections.append(
            {
                "title": "Volume Trend",
                "bullets": [
                    f"Ticket activity spans {monthly.index.min()} through {monthly.index.max()}.",
                    f"Peak volume month: {peak_month} ({monthly.max():,} tickets).",
                    "Monthly volume should be reviewed against staffing, release, and outage calendars.",
                ],
                "charts": [monthly_chart],
            }
        )

    if "Priority" in df.columns:
        priority_counts = df["Priority"].value_counts()
        p1 = int(priority_counts.get("P1", 0))
        findings.append(f"P1 tickets account for {p1:,} records ({_pct(p1, total)}).")
        sections.append(
            {
                "title": "Priority and Workload",
                "bullets": [
                    f"P1 tickets: {p1:,} ({_pct(p1, total)}).",
                    "Priority distribution should be checked for over-classification if P1 volume is high.",
                    "Support-group volume highlights where workload balancing may be needed.",
                ],
                "charts": [priority_chart, group_chart],
            }
        )

    if "Request Status" in df.columns:
        status_counts = df["Request Status"].value_counts()
        open_like = int(status_counts.get("Open", 0) + status_counts.get("In Progress", 0))
        findings.append(f"Open or in-progress tickets total {open_like:,} ({_pct(open_like, total)}).")
        sections.append(
            {
                "title": "Backlog and Closure State",
                "bullets": [
                    f"Open or in-progress tickets: {open_like:,} ({_pct(open_like, total)}).",
                    f"Resolved tickets: {int(status_counts.get('Resolved', 0)):,}; closed tickets: {int(status_counts.get('Closed', 0)):,}.",
                    "A separate backlog view is needed if open and in-progress items are operationally active.",
                ],
                "charts": [status_chart],
            }
        )

    if "Category" in df.columns:
        category_counts = df["Category"].value_counts()
        findings.append(
            f"Top category is `{category_counts.index[0]}` with {category_counts.iloc[0]:,} tickets ({_pct(category_counts.iloc[0], total)})."
        )
        sections.append(
            {
                "title": "Category Drivers",
                "bullets": [
                    f"Top category: {category_counts.index[0]} ({category_counts.iloc[0]:,} tickets).",
                    "Category mix can guide self-service content, automation, and root-cause review.",
                    "Prioritize categories that combine high volume with high urgency or SLA misses.",
                ],
                "charts": [category_chart],
            }
        )

    if "Overdue Status" in df.columns:
        overdue = int(_true_mask(df["Overdue Status"]).sum())
        findings.append(f"SLA resolution overdue tickets total {overdue:,} ({_pct(overdue, total)}).")
    if "First Response Overdue Status" in df.columns:
        response_overdue = int(_true_mask(df["First Response Overdue Status"]).sum())
        findings.append(f"First-response overdue tickets total {response_overdue:,} ({_pct(response_overdue, total)}).")
    if "Overdue Status" in df.columns or "First Response Overdue Status" in df.columns:
        extra_bullets = []
        if {"Group", "Overdue Status"}.issubset(df.columns):
            group_rates = _true_mask(df["Overdue Status"]).groupby(df["Group"].fillna("Unknown").astype(str)).mean()
            extra_bullets.append(
                f"Highest group SLA overdue rate: {group_rates.idxmax()} ({group_rates.max() * 100:.1f}%)."
            )
        if {"Priority", "First Response Overdue Status"}.issubset(df.columns):
            priority_rates = _true_mask(df["First Response Overdue Status"]).groupby(
                df["Priority"].fillna("Unknown").astype(str)
            ).mean()
            extra_bullets.append(
                f"Highest priority first-response overdue rate: {priority_rates.idxmax()} ({priority_rates.max() * 100:.1f}%)."
            )
        sections.append(
            {
                "title": "SLA and Response Risk",
                "bullets": [
                    "SLA misses are visible in both resolution and first-response indicators.",
                    "Response overdue rate should be tracked separately from final resolution overdue rate.",
                    "Focus on high-priority queues and support groups with repeated SLA misses.",
                    *extra_bullets,
                ],
                "charts": [overdue_chart, response_overdue_chart, overdue_by_group_chart, response_by_priority_chart],
            }
        )

    if resolution_chart:
        sections.append(
            {
                "title": "Resolution Time",
                "bullets": [
                    "Median resolution time varies by priority.",
                    "Review whether high-priority work is actually resolved faster than lower-priority work.",
                    "Large gaps can indicate escalation, queueing, or classification issues.",
                ],
                "charts": [resolution_chart],
            }
        )

    missing = df.isna().sum().sort_values(ascending=False)
    missing = missing[missing > 0].head(5)
    if not missing.empty:
        findings.append(f"Columns with the most blanks: {', '.join(f'{idx} ({val:,})' for idx, val in missing.items())}.")
        sections.append(
            {
                "title": "Data Quality Checks",
                "bullets": [
                    "Missing values should be reviewed before operational decisions are automated.",
                    *[f"`{idx}` has {val:,} blank values ({_pct(int(val), total)})." for idx, val in missing.items()],
                ],
                "charts": [],
            }
        )

    return findings, sections, charts


def _make_charts(df, sheet_name: str, assets_dir: pathlib.Path) -> list[dict[str, str]]:
    import matplotlib.pyplot as plt

    charts: list[dict[str, str]] = []
    safe_sheet = _safe_name(sheet_name)
    numeric_cols = [col for col in df.columns if str(df[col].dtype).startswith(("int", "float"))]
    date_cols = [col for col in df.columns if "datetime" in str(df[col].dtype)]
    categorical_cols = [
        col
        for col in df.columns
        if col not in numeric_cols and col not in date_cols and df[col].nunique(dropna=True) <= 30
    ]

    plt.style.use("seaborn-v0_8")

    if numeric_cols:
        col = numeric_cols[0]
        values = df[col].dropna()
        if len(values):
            path = assets_dir / f"{safe_sheet}-{_safe_name(str(col))}-histogram.png"
            fig = plt.figure(figsize=(10, 6))
            plt.hist(values, bins=20, alpha=0.75, edgecolor="black")
            plt.title(f"{sheet_name}: {col} distribution")
            plt.xlabel(str(col))
            plt.ylabel("Frequency")
            plt.tight_layout()
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            charts.append({"title": f"{col} distribution", "path": str(path)})

    if categorical_cols:
        col = categorical_cols[0]
        counts = df[col].dropna().astype(str).value_counts().head(12)
        if len(counts):
            path = assets_dir / f"{safe_sheet}-{_safe_name(str(col))}-top-values.png"
            fig = plt.figure(figsize=(10, 6))
            counts.sort_values().plot(kind="barh")
            plt.title(f"{sheet_name}: top {col}")
            plt.xlabel("Count")
            plt.ylabel(str(col))
            plt.tight_layout()
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            charts.append({"title": f"Top {col}", "path": str(path)})

    if date_cols and numeric_cols:
        date_col = date_cols[0]
        num_col = numeric_cols[0]
        trend = df[[date_col, num_col]].dropna().sort_values(date_col)
        if len(trend) > 1:
            trend = trend.set_index(date_col)[num_col].resample("ME").sum()
            path = assets_dir / f"{safe_sheet}-{_safe_name(str(num_col))}-trend.png"
            fig = plt.figure(figsize=(10, 6))
            trend.plot(marker="o")
            plt.title(f"{sheet_name}: {num_col} trend")
            plt.xlabel(str(date_col))
            plt.ylabel(str(num_col))
            plt.tight_layout()
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            charts.append({"title": f"{num_col} trend", "path": str(path)})

    return charts


def profile_excel(workbook: pathlib.Path, output_dir: pathlib.Path, sheet: str | None = None) -> dict[str, Any]:
    import pandas as pd

    scratch_dir = output_dir / "scratch"
    reports_dir = output_dir / "reports"
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    excel = pd.ExcelFile(workbook)
    sheet_names = [sheet] if sheet else excel.sheet_names
    profiles = []
    all_charts = []

    for sheet_name in sheet_names:
        df = pd.read_excel(excel, sheet_name=sheet_name)
        profile = _profile_sheet(df, sheet_name)
        deep_findings, deep_sections, deep_charts = _ticket_deep_analysis(df, sheet_name, assets_dir)
        charts = deep_charts or _make_charts(df, sheet_name, assets_dir)
        profile["charts"] = charts
        profile["deep_findings"] = deep_findings
        profile["deep_sections"] = deep_sections
        profiles.append(profile)
        all_charts.extend(charts)

    workbook_stem = _safe_name(workbook.stem)
    profile_json = scratch_dir / f"{workbook_stem}-profile.json"
    profile_md = scratch_dir / f"{workbook_stem}-data-profile.md"
    report_md = reports_dir / f"{workbook_stem}-analysis-report.md"

    _write(profile_json, json.dumps({"workbook": str(workbook), "sheets": profiles}, indent=2, default=_json_default))

    profile_lines = [
        f"# Data Profile: {workbook.name}",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Workbook path: `{workbook}`",
        "",
    ]
    report_lines = [
        f"# Analysis Report: {workbook.name}",
        "",
        "## Executive Summary",
        f"- The workbook contains {len(profiles)} sheet(s): "
        + ", ".join(f"`{profile['sheet']}`" for profile in profiles)
        + ".",
        f"- Generated {len(all_charts)} chart asset(s) for presentation use.",
        "- Findings below combine automated data profiling with ticket-specific operational analysis.",
        "",
    ]

    for profile in profiles:
        profile_lines.extend(
            [
                f"## Sheet: {profile['sheet']}",
                "",
                f"- Rows: {profile['rows']}",
                f"- Columns: {profile['columns']}",
                "",
                "### Columns",
                "",
            ]
        )
        for col in profile["column_profiles"]:
            line = f"- `{col['name']}` ({col['dtype']}): {col['non_null']} non-null, {col['missing']} missing ({col['missing_pct']}%)"
            if "mean" in col:
                line += f", mean {col['mean']}, median {col['median']}"
            profile_lines.append(line)
        if profile["preview"]:
            profile_lines.extend(["", "### Preview", "", _markdown_table(profile["preview"], list(profile["preview"][0].keys())), ""])
        report_lines.extend([f"## Findings: {profile['sheet']}", ""])
        findings = profile.get("deep_findings") or _sheet_findings(profile)
        for finding in findings:
            report_lines.append(f"- {finding}")
        report_lines.append("")

        deep_sections = profile.get("deep_sections") or []
        if deep_sections:
            for section in deep_sections:
                report_lines.extend([f"## {section['title']}", ""])
                for bullet in section.get("bullets", []):
                    report_lines.append(f"- {bullet}")
                report_lines.append("")
                for chart in [c for c in section.get("charts", []) if c]:
                    rel = pathlib.Path(chart["path"]).relative_to(output_dir)
                    report_lines.append(f"![{chart['title']}](../{rel.as_posix()})")
                report_lines.append("")

        if profile["charts"]:
            profile_lines.extend(["", "### Generated Charts", ""])
            if not deep_sections:
                report_lines.extend([f"## Charts: {profile['sheet']}", ""])
            for chart in profile["charts"]:
                rel = pathlib.Path(chart["path"]).relative_to(output_dir)
                profile_lines.append(f"- {chart['title']}: `{rel}`")
                if not deep_sections:
                    report_lines.append(f"![{chart['title']}](../{rel.as_posix()})")
            if not deep_sections:
                report_lines.append("")

    _write(profile_md, "\n".join(profile_lines).rstrip() + "\n")
    _write(report_md, "\n".join(report_lines).rstrip() + "\n")

    return {
        "status": "success",
        "workbook": str(workbook),
        "profile_json": str(profile_json),
        "profile_md": str(profile_md),
        "report_md": str(report_md),
        "charts": all_charts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile an Excel workbook and create markdown/chart artifacts.")
    parser.add_argument("workbook", help="Path to .xlsx workbook")
    parser.add_argument("--output-dir", default="output", help="Output workspace directory")
    parser.add_argument("--sheet", help="Optional single sheet name")
    args = parser.parse_args()

    result = profile_excel(pathlib.Path(args.workbook).resolve(), pathlib.Path(args.output_dir).resolve(), args.sheet)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

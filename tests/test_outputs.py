"""Primary verifier entry point for Harbor static review.

This file intentionally contains direct assertions for all six required outputs.
Shared recomputation helpers live in verifier_common.py so this file stays short.
"""

import re

import pandas as pd

from verifier_common import (
    MEAS,
    OUT,
    REQ,
    assert_close_columns,
    correction_map,
    csv,
    expected_flags,
    expected_triage,
    expected_validation,
    good,
    raw,
    read_summary,
)


def test_all_six_required_files_exist():
    assert REQ.issubset({p.name for p in OUT.iterdir()})


def test_flagged_sensors_match_independent_calibration_reference():
    actual = csv("flagged_sensors.csv").sort_values(
        ["station_id", "sensor_id", "measurement_type"]
    ).reset_index(drop=True)
    expected = expected_flags()
    assert list(actual.columns) == list(expected.columns)
    assert len(actual) == len(expected) == 12
    for col in ["station_id", "sensor_id", "measurement_type", "flag_reason", "drift_pattern"]:
        assert actual[col].tolist() == expected[col].tolist()
    assert actual["calibration_visit_count"].tolist() == expected["calibration_visit_count"].tolist()
    assert_close_columns(actual, expected, ["estimated_drift", "bias_mad"])


def test_corrected_readings_apply_drifts_quality_flags_and_physical_ranges():
    actual = csv("corrected_readings.csv")
    readings = raw("sensor_readings.csv")
    expected_cols = [
        "timestamp", "station_id", "sensor_id", "temperature_c_corrected",
        "humidity_percent_corrected", "pm25_ug_m3_corrected", "quality_flag", "correction_applied",
    ]
    assert list(actual.columns) == expected_cols
    assert len(actual) == len(readings) == 4452

    drifts = correction_map(expected_flags())
    merged = actual.merge(readings, on=["timestamp", "station_id", "sensor_id"])
    expected_applied = []
    for row in merged.itertuples():
        corrected = False
        for meas, (_, _, lo, hi, _) in MEAS.items():
            value = getattr(row, meas)
            if pd.notna(value) and lo <= value <= hi and (row.station_id, row.sensor_id, meas) in drifts:
                corrected = True
        expected_applied.append(str(corrected).lower())
    assert merged["correction_applied"].astype(str).str.lower().tolist() == expected_applied

    for meas, (_, corr_col, lo, hi, _) in MEAS.items():
        assert merged[corr_col].dropna().between(lo, hi).all()
        for row in merged[good(merged[meas], meas)].itertuples():
            drift = drifts.get((row.station_id, row.sensor_id, meas), 0.0)
            want = max(lo, min(hi, round(getattr(row, meas) - drift, 4)))
            assert abs(getattr(row, corr_col) - want) <= 0.001
    assert merged["quality_flag"].notna().all()
    assert merged.loc[merged["quality_flag"] != "valid", "quality_flag"].str.contains(
        "missing_|invalid_", regex=True
    ).all()


def test_validation_triage_and_summary_are_recomputed_from_outputs():
    flags = csv("flagged_sensors.csv")
    corrections = correction_map(flags)

    validation = csv("per_sensor_validation.csv").sort_values(
        ["station_id", "sensor_id", "measurement_type"]
    ).reset_index(drop=True)
    expected_validation_rows = expected_validation(corrections)
    assert list(validation.columns) == list(expected_validation_rows.columns)
    assert len(validation) == len(expected_validation_rows) == 84
    assert validation[["station_id", "sensor_id", "measurement_type"]].equals(
        expected_validation_rows[["station_id", "sensor_id", "measurement_type"]]
    )
    assert_close_columns(validation, expected_validation_rows, ["mae_before_correction", "mae_after_correction"])

    triage = csv("operational_triage.csv")
    expected_triage_rows = expected_triage(flags, expected_validation_rows)
    assert list(triage.columns) == list(expected_triage_rows.columns)
    assert len(triage) == len(expected_triage_rows) == 28
    assert triage["priority_score"].astype(int).tolist() == expected_triage_rows["priority_score"].astype(int).tolist()
    assert triage["recommended_action"].astype(str).tolist() == expected_triage_rows["recommended_action"].astype(str).tolist()

    summary = read_summary()
    before = expected_validation({})["mae_after_correction"].mean()
    after = expected_validation(corrections)["mae_after_correction"].mean()
    assert summary["validation_passed"] is True
    assert summary["high_residual_uncorrected_count"] == 4
    assert abs(summary["mean_absolute_error_before_validation"] - before) < 0.02
    assert abs(summary["mean_absolute_error_after_validation"] - after) < 0.02
    assert after < before
    assert summary["high_priority_sensor_count"] == int((triage["priority_class"] == "high").sum())


def test_report_names_required_operational_findings():
    text = (OUT / "report.md").read_text(encoding="utf-8")
    assert len(re.findall(r"\b\w+\b", text)) >= 300
    for term in ["calibration", "validation", "drift", "bias", "MAE", "maintenance", "triage"]:
        assert term.lower() in text.lower()
    assert all(sid in text for sid in ["S01C", "S03C", "S05D", "S06C"])
    assert len([sid for sid in ["S01B", "S03B", "S04D"] if sid in text]) >= 2


def test_validation_only_late_residuals_are_not_used_for_flagging():
    flagged = {(r.station_id, r.sensor_id, r.measurement_type) for r in expected_flags().itertuples()}
    late_residuals = {
        ("ST01", "S01C", "pm25_ug_m3"),
        ("ST03", "S03C", "temperature_c"),
        ("ST05", "S05D", "humidity_percent"),
        ("ST06", "S06C", "temperature_c"),
    }
    assert flagged.isdisjoint(late_residuals)


# End of primary verifier: assertions above cover required files, correction math,
# held-out validation, triage, summary metrics, and report content.

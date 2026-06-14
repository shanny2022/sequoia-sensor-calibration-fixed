import pandas as pd

from verifier_common import MEAS, OUT, REQ, assert_close_columns, correction_map, csv, expected_flags, good, raw


def test_all_required_output_files_exist():
    assert REQ.issubset({p.name for p in OUT.iterdir()})


def test_flagged_sensors_csv_matches_independent_drift_reference():
    actual = csv("flagged_sensors.csv").sort_values(
        ["station_id", "sensor_id", "measurement_type"]
    ).reset_index(drop=True)
    expected = expected_flags()
    assert list(actual.columns) == list(expected.columns)
    assert len(actual) == len(expected) == 12
    for col in ["station_id", "sensor_id", "measurement_type", "flag_reason", "drift_pattern"]:
        assert actual[col].tolist() == expected[col].tolist()
    assert_close_columns(actual, expected, ["estimated_drift", "bias_mad"])
    assert actual["calibration_visit_count"].tolist() == expected["calibration_visit_count"].tolist()


def test_corrected_readings_csv_applies_flags_quality_ranges_and_values():
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
    assert set(merged["correction_applied"].astype(str).str.lower()) <= {"true", "false"}

    expected_applied = []
    for r in merged.itertuples():
        any_corrected = False
        for meas, (_, _, lo, hi, _) in MEAS.items():
            value = getattr(r, meas)
            if pd.notna(value) and lo <= value <= hi and (r.station_id, r.sensor_id, meas) in drifts:
                any_corrected = True
        expected_applied.append(str(any_corrected).lower())
    assert merged["correction_applied"].astype(str).str.lower().tolist() == expected_applied

    for meas, (_, corr_col, lo, hi, _) in MEAS.items():
        assert merged[corr_col].dropna().between(lo, hi).all()
        for r in merged[good(merged[meas], meas)].itertuples():
            drift = drifts.get((r.station_id, r.sensor_id, meas), 0.0)
            want = max(lo, min(hi, round(getattr(r, meas) - drift, 4)))
            assert abs(getattr(r, corr_col) - want) <= 0.001

    assert merged["quality_flag"].notna().all()
    assert merged.loc[merged["quality_flag"] != "valid", "quality_flag"].str.contains(
        "missing_|invalid_", regex=True
    ).all()

import re

from verifier_common import (
    assert_close_columns,
    correction_map,
    csv,
    expected_flags,
    expected_triage,
    expected_validation,
    OUT,
    read_summary,
)


def test_per_sensor_validation_csv_matches_independent_mae_calculation():
    flags = csv("flagged_sensors.csv")
    actual = csv("per_sensor_validation.csv").sort_values(
        ["station_id", "sensor_id", "measurement_type"]
    ).reset_index(drop=True)
    expected = expected_validation(correction_map(flags))

    assert list(actual.columns) == list(expected.columns)
    assert len(actual) == len(expected) == 84
    assert actual[["station_id", "sensor_id", "measurement_type"]].equals(
        expected[["station_id", "sensor_id", "measurement_type"]]
    )
    assert_close_columns(actual, expected, ["mae_before_correction", "mae_after_correction"])
    assert actual["residual_exceeds_threshold"].astype(str).str.lower().tolist() == expected[
        "residual_exceeds_threshold"
    ].tolist()


def test_operational_triage_csv_integrates_metadata_battery_and_validation():
    flags = csv("flagged_sensors.csv")
    validation = expected_validation(correction_map(flags))
    actual = csv("operational_triage.csv")
    expected = expected_triage(flags, validation)

    assert list(actual.columns) == list(expected.columns)
    assert len(actual) == len(expected) == 28
    for col in ["station_id", "sensor_id", "location_type", "sensor_model", "deployment_batch",
                "priority_class", "recommended_action"]:
        assert actual[col].astype(str).tolist() == expected[col].astype(str).tolist()
    for col in ["maintenance_note_present", "has_step_change"]:
        assert actual[col].astype(str).str.lower().tolist() == expected[col].astype(str).tolist()
    assert_close_columns(actual, expected, ["median_battery_voltage", "low_battery_fraction",
                                            "max_validation_residual_mae"])
    for col in ["n_flagged_measurements", "uncorrected_high_residual_count", "priority_score"]:
        assert actual[col].astype(int).tolist() == expected[col].astype(int).tolist()
    assert actual.iloc[0]["priority_class"] == "high"
    assert set(actual[actual["maintenance_note_present"].astype(str).str.lower() == "true"]["sensor_id"]) == {
        "S02B", "S04C"
    }


def test_summary_json_values_are_recomputed_from_outputs_and_raw_data():
    summary = read_summary()
    corrections = correction_map(csv("flagged_sensors.csv"))
    before = expected_validation({})["mae_after_correction"].mean()
    after = expected_validation(corrections)["mae_after_correction"].mean()
    triage = csv("operational_triage.csv")

    assert summary["stations_analyzed"] == 7
    assert summary["total_sensors_analyzed"] == 28
    assert summary["sensors_flagged"] in {11, 12}
    assert summary["validation_passed"] is True
    assert summary["high_residual_uncorrected_count"] == 4
    assert abs(summary["mean_absolute_error_before_validation"] - before) < 0.02
    assert abs(summary["mean_absolute_error_after_validation"] - after) < 0.02
    assert after < before
    assert summary["high_priority_sensor_count"] == int((triage["priority_class"] == "high").sum())
    assert summary["low_battery_sensor_count"] == int((triage["low_battery_fraction"] >= 0.25).sum())


def test_report_md_names_required_findings_and_operational_topics():
    text = (OUT / "report.md").read_text(encoding="utf-8")
    assert len(re.findall(r"\b\w+\b", text)) >= 300
    for term in ["calibration", "validation", "drift", "bias", "MAE", "maintenance", "triage"]:
        assert term.lower() in text.lower()
    assert all(sid in text for sid in ["S01C", "S03C", "S05D", "S06C"])
    assert len([sid for sid in ["S01B", "S03B", "S04D"] if sid in text]) >= 2


def test_flagging_does_not_use_validation_only_late_residuals():
    flagged_keys = {
        (r.station_id, r.sensor_id, r.measurement_type)
        for r in expected_flags().itertuples()
    }
    late_residual_keys = {
        ("ST01", "S01C", "pm25_ug_m3"),
        ("ST03", "S03C", "temperature_c"),
        ("ST05", "S05D", "humidity_percent"),
        ("ST06", "S06C", "temperature_c"),
    }
    assert flagged_keys.isdisjoint(late_residual_keys)

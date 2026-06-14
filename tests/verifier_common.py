import json
import os
from pathlib import Path
from statistics import median

import pandas as pd # pyright: ignore[reportMissingModuleSource]

ROOT = Path(__file__).resolve().parents[1]

REQ = {
    "corrected_readings.csv",
    "flagged_sensors.csv",
    "summary.json",
    "per_sensor_validation.csv",
    "operational_triage.csv",
    "report.md",
}

MEAS = {
    "temperature_c": ("reference_temperature_c", "temperature_c_corrected", -50, 60, 1.5),
    "humidity_percent": ("reference_humidity_percent", "humidity_percent_corrected", 0, 100, 5.0),
    "pm25_ug_m3": ("reference_pm25_ug_m3", "pm25_ug_m3_corrected", 0, 1000, 7.0),
}


def pick_dir(env, fallbacks, names):
    for p in [Path(os.getenv(env, "")), *map(Path, fallbacks)]:
        if p and p.exists() and names.issubset({x.name for x in p.iterdir()}):
            return p
    raise AssertionError(f"Could not locate {env} directory")


DATA = pick_dir("DATA_DIR", [ROOT / "environment" / "data"], {"sensor_readings.csv"})
OUT = pick_dir("OUTPUT_DIR", [ROOT / "outputs"], REQ)


def csv(name):
    return pd.read_csv(OUT / name)


def raw(name):
    return pd.read_csv(DATA / name)


def read_summary():
    return json.loads((OUT / "summary.json").read_text())


def assert_close_columns(actual, expected, columns, tol=0.002):
    for col in columns:
        assert (actual[col] - expected[col]).abs().le(tol).all(), col


def good(series, meas):
    _, _, lo, hi, _ = MEAS[meas]
    return series.notna() & series.between(lo, hi)


def mad(vals):
    m = median(vals)
    return median(abs(v - m) for v in vals)


def post_step_biases(pairs):
    pairs = sorted(pairs)
    vals = [v for _, v in pairs]

    if len(vals) < 4:
        return None

    mean_val = sum(vals) / len(vals)
    total = sum((v - mean_val) ** 2 for v in vals)

    if total < 1e-9:
        return None

    best_sse = float("inf")
    best_index = None

    for i in range(2, len(vals) - 1):
        left = vals[:i]
        right = vals[i:]

        if len(right) < 4:
            continue

        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)

        sse = sum((v - left_mean) ** 2 for v in left)
        sse += sum((v - right_mean) ** 2 for v in right)

        if sse < best_sse:
            best_sse = sse
            best_index = i

    if best_index is None:
        return None

    post = [v for _, v in pairs[best_index:]]

    if best_sse < 0.3 * total and len(post) >= 4:
        return post

    return None


def expected_flags():
    readings = raw("sensor_readings.csv")
    refs = raw("reference_measurements.csv")

    calibration_refs = refs[refs["visit_type"] == "calibration"]
    joined = readings.merge(calibration_refs, on=["timestamp", "station_id"])

    out = []

    for (st, sid), group in joined.groupby(["station_id", "sensor_id"]): # pyright: ignore[reportGeneralTypeIssues]
        for meas, (ref_col, _, _, _, limit) in MEAS.items():
            valid = group[good(group[meas], meas)]
            valid = valid[valid[ref_col].notna()]

            pairs = []

            for _, row in valid.iterrows():
                timestamp_text = str(row["timestamp"])
                day = int(timestamp_text.split("T")[0].split("-")[2])
                bias = float(row[meas]) - float(row[ref_col])
                pairs.append((day, bias))

            if len(pairs) < 4:
                continue

            selected = post_step_biases(pairs)
            vals = selected if selected is not None else [v for _, v in sorted(pairs)]
            drift = round(median(vals), 4)

            if abs(drift) >= limit:
                out.append(
                    [
                        st,
                        sid,
                        meas,
                        drift,
                        f"median_bias_exceeds_{limit}",
                        len(vals),
                        round(mad(vals), 4),
                        "step_change" if selected is not None else "constant",
                    ]
                )

    cols = [
        "station_id",
        "sensor_id",
        "measurement_type",
        "estimated_drift",
        "flag_reason",
        "calibration_visit_count",
        "bias_mad",
        "drift_pattern",
    ]

    return pd.DataFrame(out, columns=cols).sort_values(cols[:3]).reset_index(drop=True)


def correction_map(flags):
    corrections = {}

    for _, row in flags.iterrows():
        key = (row["station_id"], row["sensor_id"], row["measurement_type"])
        corrections[key] = float(row["estimated_drift"])

    return corrections


def expected_validation(corrections):
    readings = raw("sensor_readings.csv")
    refs = raw("reference_measurements.csv")

    validation_refs = refs[refs["visit_type"] == "validation"]
    joined = readings.merge(validation_refs, on=["timestamp", "station_id"])

    rows = []

    for (st, sid), group in joined.groupby(["station_id", "sensor_id"]): # pyright: ignore[reportGeneralTypeIssues]
        for meas, (ref_col, _, _, _, limit) in MEAS.items():
            valid = group[good(group[meas], meas)]
            valid = valid[valid[ref_col].notna()]

            drift = corrections.get((st, sid, meas), 0.0)

            before = (valid[meas] - valid[ref_col]).abs().mean()
            after = (valid[meas] - drift - valid[ref_col]).abs().mean()

            rows.append(
                [
                    st,
                    sid,
                    meas,
                    len(valid),
                    round(before, 4),
                    round(after, 4),
                    str(after < before).lower(),
                    str(after > limit).lower(),
                ]
            )

    cols = [
        "station_id",
        "sensor_id",
        "measurement_type",
        "n_validation_matched",
        "mae_before_correction",
        "mae_after_correction",
        "mae_improved",
        "residual_exceeds_threshold",
    ]

    return pd.DataFrame(rows, columns=cols).sort_values(cols[:3]).reset_index(drop=True)


def expected_triage(flags, validation):
    readings = raw("sensor_readings.csv")
    metadata = raw("station_metadata.csv").set_index("station_id")
    health = raw("sensor_health.csv")

    notes = health["maintenance_notes"].fillna("None").astype(str).str.strip()
    health["maintenance_note_present"] = (notes != "") & (notes.str.lower() != "none")
    health = health.set_index(["station_id", "sensor_id"])

    corrections = correction_map(flags)
    rows = []

    for (st, sid), group in readings.groupby(["station_id", "sensor_id"]): # pyright: ignore[reportGeneralTypeIssues]
        sensor_flags = flags[(flags["station_id"] == st) & (flags["sensor_id"] == sid)]
        validation_rows = validation[
            (validation["station_id"] == st) & (validation["sensor_id"] == sid)
        ]

        n_flagged = len(sensor_flags)
        has_step = bool(n_flagged and (sensor_flags["drift_pattern"] == "step_change").any())

        median_battery = round(float(group["battery_voltage"].median()), 4)
        low_fraction = round(float((group["battery_voltage"] < 3.72).mean()), 4)

        uncorrected_high = 0

        for _, row in validation_rows.iterrows():
            key = (st, sid, row["measurement_type"])
            has_no_correction = corrections.get(key, 0.0) == 0.0
            exceeds = str(row["residual_exceeds_threshold"]).lower() == "true"

            if has_no_correction and exceeds:
                uncorrected_high += 1

        maintenance_present = bool(health.loc[(st, sid), "maintenance_note_present"])

        score = 3 * n_flagged
        score += 2 * uncorrected_high
        score += 2 if has_step else 0
        score += 1 if maintenance_present else 0
        score += 1 if low_fraction >= 0.25 else 0

        if score >= 6:
            priority = "high"
        elif score >= 3:
            priority = "medium"
        else:
            priority = "low"

        action = {
            "high": "urgent_field_visit",
            "medium": "schedule_recalibration",
            "low": "routine_monitoring",
        }[priority]

        meta = metadata.loc[st]

        rows.append(
            [
                st,
                sid,
                meta["location_type"],
                meta["sensor_model"],
                meta["deployment_batch"],
                str(maintenance_present).lower(),
                median_battery,
                low_fraction,
                n_flagged,
                str(has_step).lower(),
                round(float(validation_rows["mae_after_correction"].max()), 4),
                uncorrected_high,
                score,
                priority,
                action,
            ]
        )

    cols = [
        "station_id",
        "sensor_id",
        "location_type",
        "sensor_model",
        "deployment_batch",
        "maintenance_note_present",
        "median_battery_voltage",
        "low_battery_fraction",
        "n_flagged_measurements",
        "has_step_change",
        "max_validation_residual_mae",
        "uncorrected_high_residual_count",
        "priority_score",
        "priority_class",
        "recommended_action",
    ]

    return pd.DataFrame(rows, columns=cols).sort_values(
        ["priority_score", "station_id", "sensor_id"],
        ascending=[False, True, True],
    ).reset_index(drop=True)

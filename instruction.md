# Sequoia Sensor Calibration Instructions

You are helping a materials testing lab decide which exposure-chamber sensors can be corrected in software and which ones need a bench inspection before their readings are used to interpret polymer, coating, and composite aging studies. The lab has seven exposure stations, each with four sensors measuring chamber temperature, humidity, airborne particulate load, and battery voltage every four hours. Use the files in `/app/data/` and write all final artifacts to `/app/outputs/`.

A reference instrument visited the exposure stations during the campaign. Rows with `visit_type == "calibration"` are the only rows available for estimating sensor bias and deciding which station/sensor/measurement pairs should be corrected. Rows with `visit_type == "validation"` are held out for checking whether the corrections helped; a validation-only failure should appear in the validation and triage results, not in the drift flagging decision. Do not use validation visits to flag sensors or estimate drift.

The `calibration_protocol.csv` file gives the physical ranges and action limits for `temperature_c`, `humidity_percent`, and `pm25_ug_m3`. If those values are needed directly, use the following measurement rules: temperature valid range is -50 to 60 with action limit 1.5, humidity valid range is 0 to 100 with action limit 5.0, and PM2.5 valid range is 0 to 1000 with action limit 7.0. `battery_voltage` is context for triage only and should not be corrected.

Screen bad chamber readings before using them in drift estimates or validation metrics. Missing or physically invalid source values should not contribute to calibration or validation statistics. Corrected readings for those fields should be blank. For rows with no missing or invalid temperature, humidity, or PM2.5 values, `quality_flag` must be exactly `valid`. For rows with missing or physically invalid values, `quality_flag` must name the affected fields using semicolon-separated tokens in this measurement order when present: `temperature_c;humidity_percent;pm25_ug_m3`. Missing values must use the token format `missing_<measurement_name>`, such as `missing_temperature_c`. Physically invalid values must use the token format `invalid_<measurement_name>`, such as `invalid_pm25_ug_m3`. Do not leave `quality_flag` blank or null.

Estimate bias as `raw chamber value - reference value`, matching chamber and reference rows by exact `timestamp` and `station_id`. A station/sensor/measurement pair needs at least four valid calibration matches before it can be flagged. The drift estimate should be a robust median bias.

For step-change detection, use a deterministic single-split search over the chronological valid calibration-bias sequence. A candidate split is valid only if both sides contain at least two valid bias values and the post-change side contains at least four valid bias values. Choose the split that gives the largest reduction in total within-segment variance compared with the unsplit sequence. Use `step_change` only when the selected split reduces the total within-segment variance to less than 30% of the unsplit variance and the post-change side has at least four valid biases. Otherwise use `constant`. When `step_change` is selected, compute `estimated_drift`, `calibration_visit_count`, and `bias_mad` from the post-change calibration biases only, but apply that drift correction to every valid row for that station/sensor/measurement in the full sensor record.

Corrections should subtract the estimated drift from valid readings for the same station/sensor/measurement and keep corrected values inside the physical range.

Produce exactly these six deliverables with these exact filenames:

* `flagged_sensors.csv`
* `corrected_readings.csv`
* `per_sensor_validation.csv`
* `operational_triage.csv`
* `summary.json`
* `report.md`

`flagged_sensors.csv`: columns `station_id, sensor_id, measurement_type, estimated_drift, flag_reason, calibration_visit_count, bias_mad, drift_pattern`.

Allowed `measurement_type` values are exactly `temperature_c`, `humidity_percent`, and `pm25_ug_m3`.

Flag a station/sensor/measurement pair when the absolute value of the selected median bias is greater than or equal to that measurement's action limit.

`estimated_drift` and `bias_mad` should be rounded to four decimals.

`flag_reason` must use exactly one of these snake_case coded strings:

* `median_bias_exceeds_1.5` for `temperature_c`
* `median_bias_exceeds_5.0` for `humidity_percent`
* `median_bias_exceeds_7.0` for `pm25_ug_m3`

Do not write natural-language `flag_reason` values such as `drift exceeds 1.5`.

`calibration_visit_count` should count the selected calibration biases used for the drift estimate. For `constant`, count all valid calibration biases used. For `step_change`, count only the valid post-change calibration biases used.

`bias_mad` is `median(abs(bias_i - median(selected_biases)))`, using the same selected bias values used for the drift estimate.

`drift_pattern` must be exactly `constant` or `step_change`.

Sort `flagged_sensors.csv` by `station_id`, then `sensor_id`, then `measurement_type`.

`corrected_readings.csv`: one row per original sensor reading, columns `timestamp, station_id, sensor_id, temperature_c_corrected, humidity_percent_corrected, pm25_ug_m3_corrected, quality_flag, correction_applied`.

Use wide format with the three `*_corrected` columns.

For each valid corrected measurement, write `raw_value - estimated_drift`, rounded to four decimals and clamped inside that measurement's physical range.

If a measurement has no flagged drift correction, write the valid raw value rounded to four decimals.

If the raw source value is missing or physically invalid, leave that corrected measurement value blank and include the appropriate `missing_<measurement_name>` or `invalid_<measurement_name>` token in `quality_flag`.

For rows with no missing or invalid temperature, humidity, or PM2.5 values, `quality_flag` must be exactly `valid`.

`correction_applied` must be the lowercase string `true` when at least one valid measurement on that row received a nonzero drift correction, otherwise `false`.

Keep `corrected_readings.csv` in the same row order as the original sensor readings.

`per_sensor_validation.csv`: one row for every station/sensor/measurement combination with at least one valid validation match, columns `station_id, sensor_id, measurement_type, n_validation_matched, mae_before_correction, mae_after_correction, mae_improved, residual_exceeds_threshold`.

A valid validation match requires a valid raw chamber value and a valid reference value for the same `timestamp`, `station_id`, and measurement type.

`mae_before_correction` is the mean absolute error between raw chamber values and held-out validation reference values.

`mae_after_correction` is the mean absolute error between corrected chamber values and held-out validation reference values.

MAE values should be rounded to four decimals.

`mae_improved` must be the lowercase string `true` when `mae_after_correction` is less than `mae_before_correction`, otherwise `false`.

`residual_exceeds_threshold` must be the lowercase string `true` when `mae_after_correction` is greater than the measurement's action limit, otherwise `false`.

Sort `per_sensor_validation.csv` by `station_id`, then `sensor_id`, then `measurement_type`.

`operational_triage.csv`: one row per physical sensor, columns `station_id, sensor_id, location_type, sensor_model, deployment_batch, maintenance_note_present, median_battery_voltage, low_battery_fraction, n_flagged_measurements, has_step_change, max_validation_residual_mae, uncorrected_high_residual_count, priority_score, priority_class, recommended_action`.

Use every station/sensor pair present in the source sensor readings.

Join `location_type`, `sensor_model`, and `deployment_batch` from `station_metadata.csv`. Join maintenance notes from `sensor_health.csv`.

`maintenance_note_present` must be the lowercase string `true` when the maintenance note is present and is not blank and is not `None` case-insensitively. Otherwise use `false`.

`median_battery_voltage` is the median battery voltage for that station/sensor, rounded to four decimals.

`low_battery_fraction` is the fraction of that station/sensor's battery readings below 3.72 volts, rounded to four decimals.

`n_flagged_measurements` is the count of rows in `flagged_sensors.csv` for that station/sensor.

`has_step_change` must be the lowercase string `true` when any flagged measurement for that station/sensor has `drift_pattern == "step_change"`, otherwise `false`.

`max_validation_residual_mae` is the maximum `mae_after_correction` across that station/sensor's rows in `per_sensor_validation.csv`, rounded to four decimals.

`uncorrected_high_residual_count` is the count of measurement types for that station/sensor where `residual_exceeds_threshold == "true"` in `per_sensor_validation.csv` and that station/sensor/measurement does not appear in `flagged_sensors.csv`.

Compute `priority_score` exactly as:

`3 * n_flagged_measurements + 2 * uncorrected_high_residual_count + 2 * has_step_change_indicator + 1 * maintenance_note_indicator + 1 * low_battery_indicator`

Where:

* `has_step_change_indicator` is `1` when `has_step_change == "true"`, otherwise `0`.
* `maintenance_note_indicator` is `1` when `maintenance_note_present == "true"`, otherwise `0`.
* `low_battery_indicator` is `1` when `low_battery_fraction >= 0.25`, otherwise `0`.

Assign `priority_class` exactly as:

* `high` when `priority_score >= 6`
* `medium` when `priority_score >= 3` and less than 6
* `low` when `priority_score < 3`

Assign `recommended_action` exactly as:

* `urgent_field_visit` for `high`
* `schedule_recalibration` for `medium`
* `routine_monitoring` for `low`

Sort `operational_triage.csv` by descending `priority_score`, then ascending `station_id`, then ascending `sensor_id`.

`summary.json`: include exactly these keys:

* `stations_analyzed`
* `total_sensors_analyzed`
* `sensors_flagged`
* `calibration_visits_used`
* `validation_visits_used`
* `mean_absolute_error_before_validation`
* `mean_absolute_error_after_validation`
* `validation_passed`
* `high_residual_uncorrected_count`
* `high_priority_sensor_count`
* `low_battery_sensor_count`
* `maintenance_linked_priority_count`
* `correction_method`

`stations_analyzed` is the count of unique stations analyzed.

`total_sensors_analyzed` is the count of unique station/sensor pairs analyzed.

`sensors_flagged` is the count of unique station/sensor pairs with at least one flagged measurement in `flagged_sensors.csv`.

`calibration_visits_used` is the count of rows in the reference file with `visit_type == "calibration"`.

`validation_visits_used` is the count of rows in the reference file with `visit_type == "validation"`.

`mean_absolute_error_before_validation` is the aggregate validation MAE before correction, computed only from valid validation matches across temperature, humidity, and PM2.5.

`mean_absolute_error_after_validation` is the aggregate validation MAE after correction, computed only from valid validation matches across temperature, humidity, and PM2.5.

Round both aggregate MAE values to four decimals.

`validation_passed` must be a JSON boolean. Use `true` when `mean_absolute_error_after_validation` is less than or equal to `mean_absolute_error_before_validation`, otherwise `false`.

`high_residual_uncorrected_count` is the total number of station/sensor/measurement rows in `per_sensor_validation.csv` where `residual_exceeds_threshold == "true"` and the same station/sensor/measurement does not appear in `flagged_sensors.csv`.

`high_priority_sensor_count` is the number of rows in `operational_triage.csv` with `priority_class == "high"`.

`low_battery_sensor_count` is the number of rows in `operational_triage.csv` where `low_battery_fraction >= 0.25`.

`maintenance_linked_priority_count` is the number of rows in `operational_triage.csv` where `maintenance_note_present == "true"` and `priority_class` is either `high` or `medium`.

`correction_method` should be a short string describing the deterministic robust median-bias correction with validation held out.

Do not invent different summary key names. The keys must match the list above exactly.

`report.md`: write at least 300 words in a lab-operations voice.

Include:

* the aggregate before-correction validation MAE
* the aggregate after-correction validation MAE
* whether validation improved after correction
* the drifted sensors from `flagged_sensors.csv`
* every step-change station/sensor/measurement
* every uncorrected high-residual validation station/sensor/measurement pair and its residual MAE
* concrete maintenance or recalibration recommendations
* every high-priority station/sensor from `operational_triage.csv` with its exact `recommended_action`

When naming recommended actions in `report.md`, include the exact snake_case `recommended_action` values verbatim, such as `urgent_field_visit`, `schedule_recalibration`, and `routine_monitoring`. Do not only rewrite them as natural-language phrases.

Before finishing, verify that all six required artifacts exist in `/app/outputs/` with the exact filenames and required columns:

* `flagged_sensors.csv`
* `corrected_readings.csv`
* `per_sensor_validation.csv`
* `operational_triage.csv`
* `summary.json`
* `report.md`

Everything should be deterministic from the supplied CSV files. Do not use validation visits to flag sensors or estimate drift. Prioritize producing the required output files directly; do not spend excessive time on exploratory analysis before writing artifacts.

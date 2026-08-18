"""Garmin Connect API tools.

All @mcp.tool wrappers for the Garmin device / cloud APIs:
- Session / auth: check-session, garmin-login
- Profile: get-user-profile
- Activities: list-activities, get-last-run, get-activity(-splits/-details/-hr-zones/-weather/-split-summaries), get-last-activity, download-fit
- Daily wellness: get-daily-summary / -heart-rate / -stress / -intensity-minutes / -respiration
- Body/recovery: get-sleep, get-body-battery, get-hrv, get-weight, get-hydration
- Performance: get-vo2max, get-training-readiness, get-training-status, get-personal-records, get-fitness-stats
- Goals/badges: get-goals, get-badges
- Workouts: list-workouts, get-workout, download-workout-fit, create-workout, schedule-workout, delete-workout, unschedule-workout

Zero behavior changes from pre-split server.py.
"""
from __future__ import annotations
import base64
import json
from datetime import date
from typing import Any

from garminconnect import Garmin
from db_common import _get_client, _wrap_401, _dumps


def register_garmin_tools(mcp) -> None:
    """Register all Garmin API tools on the given FastMCP instance."""

    # =========================================================================
    # Session / auth
    # =========================================================================

    @mcp.tool(name="check-session", description="Check if the saved Garmin OAuth session is still valid.")
    @_wrap_401
    def check_session() -> str:
        c = _get_client()
        summary = c.get_user_summary(date.today().isoformat())
        return _dumps({
            "status": "ok",
            "date": date.today().isoformat(),
            "steps": summary.get("totalSteps"),
            "resting_hr": summary.get("restingHeartRate"),
        })

    @mcp.tool(name="garmin-login", description="Instructions for OAuth setup (one-time).")
    def garmin_login() -> str:
        return (
            "Garmin OAuth setup (one-time):\n"
            "  1. python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\setup_credentials.py\n"
            "  2. python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\test_login.py\n"
            "OAuth1 lives ~1 year. Verify with check-session."
        )

    # =========================================================================
    # Profile
    # =========================================================================

    @mcp.tool(name="get-user-profile", description="Get user profile + settings.")
    @_wrap_401
    def get_user_profile() -> str:
        c = _get_client()
        return _dumps({
            "profile": c.get_user_profile(),
            "settings": c.get_userprofile_settings(),
        })

    # =========================================================================
    # Activities
    # =========================================================================

    @mcp.tool(name="list-activities", description="List Garmin activities, paginated. Optional activityType filter (e.g. 'running', 'strength_training', 'cycling') — server-side, much faster than filtering the full list.")
    @_wrap_401
    def list_activities(limit: int = 20, start: int = 0, activityType: str | None = None) -> str:
        c = _get_client()
        return _dumps(c.get_activities(start, limit, activityType))

    @mcp.tool(name="get-last-run", description="Get the most recent running activity (server-side type filter — use this instead of get-last-activity when you specifically need a run).")
    @_wrap_401
    def get_last_run() -> str:
        c = _get_client()
        runs = c.get_activities(0, 1, "running")
        if not runs:
            return _dumps({"status": "no_runs_found"})
        return _dumps(runs[0])

    @mcp.tool(name="get-activity", description="Get full activity summary.")
    @_wrap_401
    def get_activity(activityId: str) -> str:
        c = _get_client()
        return _dumps(c.get_activity(activityId))

    @mcp.tool(name="get-activity-splits", description="Get lap/split data (includes GCT balance, cadence).")
    @_wrap_401
    def get_activity_splits(activityId: str) -> str:
        c = _get_client()
        return _dumps(c.get_activity_splits(activityId))

    @mcp.tool(name="get-activity-details", description="Time-series metrics (HR, cadence, elevation).")
    @_wrap_401
    def get_activity_details(activityId: str, maxChartSize: int = 2000) -> str:
        c = _get_client()
        return _dumps(c.get_activity_details(activityId, maxChartSize))

    @mcp.tool(name="get-activity-hr-zones", description="Heart rate time-in-zone breakdown for an activity.")
    @_wrap_401
    def get_activity_hr_zones(activityId: str) -> str:
        c = _get_client()
        return _dumps(c.get_activity_hr_in_timezones(activityId))

    @mcp.tool(name="get-activity-weather", description="Weather conditions during an activity.")
    @_wrap_401
    def get_activity_weather(activityId: str) -> str:
        c = _get_client()
        return _dumps(c.get_activity_weather(activityId))

    @mcp.tool(name="get-activity-split-summaries", description="Split summaries (running walk splits, climb splits, etc.)")
    @_wrap_401
    def get_activity_split_summaries(activityId: str) -> str:
        c = _get_client()
        return _dumps(c.get_activity_split_summaries(activityId))

    @mcp.tool(name="get-last-activity", description="Get the most recent activity summary.")
    @_wrap_401
    def get_last_activity() -> str:
        c = _get_client()
        return _dumps(c.get_last_activity())

    @mcp.tool(name="download-fit", description="Download activity as FIT. Returns base64 bytes and a suggested filename.")
    @_wrap_401
    def download_fit(activityId: str) -> str:
        c = _get_client()
        data = c.download_activity(activityId, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
        return _dumps({
            "activityId": activityId,
            "filename": f"activity_{activityId}.fit",
            "data_base64": base64.b64encode(data).decode("ascii"),
            "size_bytes": len(data),
        })

    # =========================================================================
    # Daily wellness
    # =========================================================================

    @mcp.tool(name="get-daily-summary", description="Daily summary: steps, calories, distance, intensity, floors.")
    @_wrap_401
    def get_daily_summary(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_stats(dateStr))

    @mcp.tool(name="get-daily-heart-rate", description="HR timeline for a date.")
    @_wrap_401
    def get_daily_heart_rate(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_heart_rates(dateStr))

    @mcp.tool(name="get-daily-stress", description="Stress level throughout the day.")
    @_wrap_401
    def get_daily_stress(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_stress_data(dateStr))

    @mcp.tool(name="get-daily-intensity-minutes", description="Intensity minutes earned for a date.")
    @_wrap_401
    def get_daily_intensity_minutes(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_intensity_minutes_data(dateStr))

    @mcp.tool(name="get-daily-respiration", description="Respiration rate for a date.")
    @_wrap_401
    def get_daily_respiration(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_respiration_data(dateStr))

    # =========================================================================
    # Body / recovery
    # =========================================================================

    @mcp.tool(name="get-sleep", description="Sleep data (score, stages, HRV) for a date.")
    @_wrap_401
    def get_sleep(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_sleep_data(dateStr))

    @mcp.tool(name="get-body-battery", description="Body battery charged/drained values for a date range.")
    @_wrap_401
    def get_body_battery(startDate: str, endDate: str | None = None) -> str:
        c = _get_client()
        return _dumps(c.get_body_battery(startDate, endDate))

    @mcp.tool(name="get-hrv", description="Heart rate variability (HRV) data for a date.")
    @_wrap_401
    def get_hrv(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_hrv_data(dateStr))

    @mcp.tool(name="get-weight", description="Weight measurements over a date range.")
    @_wrap_401
    def get_weight(startDate: str, endDate: str) -> str:
        c = _get_client()
        return _dumps(c.get_weigh_ins(startDate, endDate))

    @mcp.tool(name="get-hydration", description="Daily hydration for a date.")
    @_wrap_401
    def get_hydration(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_hydration_data(dateStr))

    # =========================================================================
    # Performance
    # =========================================================================

    @mcp.tool(name="get-vo2max", description="VO2 Max / fitness level estimate for a date.")
    @_wrap_401
    def get_vo2max(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_max_metrics(dateStr))

    @mcp.tool(name="get-training-readiness", description="Training readiness score for a date.")
    @_wrap_401
    def get_training_readiness(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_training_readiness(dateStr))

    @mcp.tool(name="get-training-status", description="Training status (productive, maintaining, detraining) for a date.")
    @_wrap_401
    def get_training_status(dateStr: str) -> str:
        c = _get_client()
        return _dumps(c.get_training_status(dateStr))

    @mcp.tool(name="get-personal-records", description="All personal records with history.")
    @_wrap_401
    def get_personal_records() -> str:
        c = _get_client()
        return _dumps(c.get_personal_record())

    @mcp.tool(name="get-fitness-stats", description="Aggregated fitness stats by activity type over a date range.")
    @_wrap_401
    def get_fitness_stats(startDate: str, endDate: str, metric: str = "distance", groupByActivities: bool = True) -> str:
        c = _get_client()
        return _dumps(c.get_progress_summary_between_dates(startDate, endDate, metric, groupByActivities))

    # =========================================================================
    # Goals & badges
    # =========================================================================

    @mcp.tool(name="get-goals", description="Active goals (status: active/completed/past).")
    @_wrap_401
    def get_goals(status: str = "active", start: int = 0, limit: int = 30) -> str:
        c = _get_client()
        return _dumps(c.get_goals(status, start, limit))

    @mcp.tool(name="get-badges", description="Earned badges.")
    @_wrap_401
    def get_badges() -> str:
        c = _get_client()
        return _dumps(c.get_earned_badges())

    # =========================================================================
    # Workouts
    # =========================================================================

    @mcp.tool(name="list-workouts", description="List saved workouts (paginated).")
    @_wrap_401
    def list_workouts(start: int = 0, limit: int = 100) -> str:
        c = _get_client()
        return _dumps(c.get_workouts(start, limit))

    @mcp.tool(name="get-workout", description="Get a single workout by ID with full step details.")
    @_wrap_401
    def get_workout(workoutId: str) -> str:
        c = _get_client()
        return _dumps(c.get_workout_by_id(workoutId))

    @mcp.tool(name="download-workout-fit", description="Download workout as FIT bytes (base64).")
    @_wrap_401
    def download_workout_fit(workoutId: str) -> str:
        c = _get_client()
        data = c.download_workout(workoutId)
        return _dumps({
            "workoutId": workoutId,
            "filename": f"workout_{workoutId}.fit",
            "data_base64": base64.b64encode(data).decode("ascii"),
            "size_bytes": len(data),
        })

    @mcp.tool(name="create-workout", description="Upload a workout from JSON. Argument workout: dict or JSON string.")
    @_wrap_401
    def create_workout(workout: Any) -> str:
        c = _get_client()
        if isinstance(workout, str):
            try:
                workout = json.loads(workout)
            except Exception:
                pass
        return _dumps(c.upload_workout(workout))

    @mcp.tool(name="schedule-workout", description="Schedule an existing workout to a date (YYYY-MM-DD).")
    @_wrap_401
    def schedule_workout(workoutId: str, date: str) -> str:
        c = _get_client()
        return _dumps(c.schedule_workout(workoutId, date))

    @mcp.tool(name="delete-workout", description="Delete a workout from Garmin.")
    @_wrap_401
    def delete_workout(workoutId: str) -> str:
        c = _get_client()
        return _dumps(c.delete_workout(workoutId))

    @mcp.tool(name="unschedule-workout", description="Remove a scheduled workout from the calendar.")
    @_wrap_401
    def unschedule_workout(workoutId: str) -> str:
        c = _get_client()
        return _dumps(c.unschedule_workout(workoutId))

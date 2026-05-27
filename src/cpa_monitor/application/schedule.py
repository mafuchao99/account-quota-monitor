from __future__ import annotations


def cron_kwargs(expression: str) -> dict[str, str]:
    parts = expression.split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        return {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    if len(parts) == 6:
        second, minute, hour, day, month, day_of_week = parts
        return {
            "second": second,
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    raise ValueError(f"Cron expression must have 5 or 6 fields: {expression}")

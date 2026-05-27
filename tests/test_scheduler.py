from cpa_monitor.application.schedule import cron_kwargs


def test_cron_kwargs_accepts_six_field_cron():
    assert cron_kwargs("0 */30 * * * *") == {
        "second": "0",
        "minute": "*/30",
        "hour": "*",
        "day": "*",
        "month": "*",
        "day_of_week": "*",
    }

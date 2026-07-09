"""
test_usage_report_dates.py — aritmética de "mes calendario anterior" usada
por los reportes mensuales (reviews-analitica-colaboracion, ítem 7).

Función pura, sin BD — cubre especialmente el rollover de año (enero -> diciembre
del año anterior), que es el caso más propenso a un off-by-one.
"""
import datetime

from services.core.usage_report_service import _previous_month_period


def test_mid_year_month():
    now = datetime.datetime(2026, 7, 9, 15, 30, 45)
    start, end = _previous_month_period(now)
    assert start == datetime.datetime(2026, 6, 1, 0, 0, 0)
    assert end == datetime.datetime(2026, 7, 1, 0, 0, 0)


def test_january_rolls_back_to_december_previous_year():
    now = datetime.datetime(2026, 1, 15, 8, 0, 0)
    start, end = _previous_month_period(now)
    assert start == datetime.datetime(2025, 12, 1, 0, 0, 0)
    assert end == datetime.datetime(2026, 1, 1, 0, 0, 0)


def test_march_rolls_back_to_february_even_in_leap_year():
    now = datetime.datetime(2028, 3, 1, 0, 0, 0)  # 2028 es bisiesto
    start, end = _previous_month_period(now)
    assert start == datetime.datetime(2028, 2, 1, 0, 0, 0)
    assert end == datetime.datetime(2028, 3, 1, 0, 0, 0)


def test_time_of_day_is_zeroed_out():
    now = datetime.datetime(2026, 5, 20, 23, 59, 59, 999999)
    start, end = _previous_month_period(now)
    assert start.hour == 0 and start.minute == 0 and start.second == 0 and start.microsecond == 0
    assert end.hour == 0 and end.minute == 0 and end.second == 0 and end.microsecond == 0


def test_period_is_exactly_one_month_wide_regardless_of_day_of_month():
    # now cae el día 31; el mes anterior puede tener menos días (ej. abril=30) —
    # period_start/period_end no deben verse afectados por el día de `now`.
    now = datetime.datetime(2026, 5, 31, 12, 0, 0)
    start, end = _previous_month_period(now)
    assert start == datetime.datetime(2026, 4, 1, 0, 0, 0)
    assert end == datetime.datetime(2026, 5, 1, 0, 0, 0)

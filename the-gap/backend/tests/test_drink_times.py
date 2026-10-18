from routers.checkin import CheckInRequest
from utils import drink_times


def test_one_or_several_times_are_kept_in_clock_order():
    assert drink_times.clean("evening") == "evening"
    assert drink_times.clean("late,afternoon,evening") == "afternoon,evening,late"
    assert drink_times.clean(["evening", "morning"]) == "morning,evening"
    assert drink_times.clean(" Evening , evening ") == "evening"


def test_unknown_or_empty_values_are_dropped():
    assert drink_times.clean(None) is None
    assert drink_times.clean("") is None
    assert drink_times.clean("midnight-ish") is None
    assert drink_times.clean("evening,midnight-ish") == "evening"


def test_adding_a_time_keeps_the_ones_already_there():
    assert drink_times.add(None, "evening") == "evening"
    assert drink_times.add("afternoon", "evening") == "afternoon,evening"
    assert drink_times.add("afternoon,evening", "evening") == "afternoon,evening"
    assert drink_times.add("late", "afternoon") == "afternoon,late"


def test_a_check_in_accepts_several_drinking_times_and_still_rejects_nonsense():
    body = CheckInRequest(date="2026-10-18", alcohol_drinks=4, alcohol_time="evening,afternoon,late")
    assert body.alcohol_time == "afternoon,evening,late"
    assert CheckInRequest(date="2026-10-18", alcohol_drinks=1, alcohol_time="whenever").alcohol_time is None
    # The other "when" questions still take exactly one answer.
    assert CheckInRequest(date="2026-10-18", energy_drinks=1, energy_drink_time="evening,late").energy_drink_time is None

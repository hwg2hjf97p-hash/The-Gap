import pytest

from utils import manual_sync as ms


@pytest.fixture(autouse=True)
def clean():
    ms._last_finished.clear()
    ms._running.clear()
    yield
    ms._last_finished.clear()
    ms._running.clear()


def test_the_first_sync_may_start():
    assert ms.check("u1", now=1000.0) is None


def test_a_second_sync_while_one_is_running_is_refused():
    ms.start("u1")
    assert ms.check("u1", now=1000.0) == {"status": "running"}


def test_a_sync_straight_after_the_last_one_is_refused_and_says_how_long_ago():
    ms.start("u1")
    ms.finish("u1", now=1000.0)
    assert ms.check("u1", now=1005.0) == {"status": "recent", "seconds_ago": 5}


def test_a_sync_after_the_gap_is_allowed():
    ms.start("u1")
    ms.finish("u1", now=1000.0)
    assert ms.check("u1", now=1000.0 + ms.MIN_GAP_SECONDS) is None


def test_one_persons_sync_never_blocks_another():
    ms.start("u1")
    ms.finish("u1", now=1000.0)
    assert ms.check("u2", now=1001.0) is None


def test_a_failed_sync_still_releases_the_person():
    ms.start("u1")
    ms.finish("u1", now=1000.0)  # finish is called from a finally, success or not
    assert "u1" not in ms._running


def test_the_memory_does_not_grow_for_ever():
    for n in range(ms._MAX_TRACKED + 10):
        ms.finish(f"user-{n}", now=float(n))
    assert len(ms._last_finished) <= ms._MAX_TRACKED

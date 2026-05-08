import pytest
import App


@pytest.fixture(autouse=True)
def reset_tracker():
    App._stub_tracker.clear()
    yield
    App._stub_tracker.clear()


def test_tracker_inactive_before_set_mission():
    App._stub_tracker.record("SomeMethod")
    assert App._stub_tracker.report() == []


def test_tracker_counts_calls_per_mission():
    App._stub_tracker.set_mission("mission_a")
    App._stub_tracker.record("Foo")
    App._stub_tracker.record("Foo")
    App._stub_tracker.set_mission("mission_b")
    App._stub_tracker.record("Foo")
    rows = App._stub_tracker.report()
    assert len(rows) == 1
    name, mission_count, total_calls = rows[0]
    assert name == "Foo"
    assert mission_count == 2
    assert total_calls == 3

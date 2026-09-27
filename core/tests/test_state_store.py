from app.engine.state_store import RiskState, StateStore


def test_load_returns_defaults_when_fresh(tmp_path):
    store = StateStore(tmp_path / "state.db")
    state = store.load()

    assert state.kill_switch_active is False
    assert state.kill_switch_reason is None
    assert state.day is None
    assert state.day_start_equity is None


def test_save_and_load_round_trip(tmp_path):
    store = StateStore(tmp_path / "state.db")
    store.save(
        RiskState(
            kill_switch_active=True,
            kill_switch_reason="manual halt",
            day="2026-09-26",
            day_start_equity=1000.0,
            last_equity=950.0,
        )
    )

    state = store.load()

    assert state.kill_switch_active is True
    assert state.kill_switch_reason == "manual halt"
    assert state.day == "2026-09-26"
    assert state.day_start_equity == 1000.0
    assert state.last_equity == 950.0


def test_state_persists_across_separate_store_instances_same_file(tmp_path):
    """A new StateStore pointed at the same file recovers prior state - simulating a process restart."""
    db_path = tmp_path / "state.db"

    store_a = StateStore(db_path)
    store_a.save(RiskState(kill_switch_active=True, kill_switch_reason="halted for the day"))

    store_b = StateStore(db_path)
    state = store_b.load()

    assert state.kill_switch_active is True
    assert state.kill_switch_reason == "halted for the day"


def test_creates_parent_directory_if_missing(tmp_path):
    nested_path = tmp_path / "nested" / "dir" / "state.db"
    store = StateStore(nested_path)

    assert nested_path.exists()
    assert store.load().kill_switch_active is False

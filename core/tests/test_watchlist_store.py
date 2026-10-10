from app.engine.watchlist_store import WatchlistStore


def test_list_is_empty_initially(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.db")
    assert store.list() == []


def test_add_normalizes_symbol_and_returns_the_item(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.db")

    item = store.add("  aapl ")

    assert item.symbol == "AAPL"
    assert [i.symbol for i in store.list()] == ["AAPL"]


def test_add_is_idempotent_for_the_same_symbol(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.db")

    store.add("AAPL")
    store.add("aapl")

    assert len(store.list()) == 1


def test_remove_returns_true_when_the_symbol_existed(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.db")
    store.add("AAPL")

    assert store.remove("aapl") is True
    assert store.list() == []


def test_remove_returns_false_when_the_symbol_was_missing(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.db")
    assert store.remove("ZZZZ") is False


def test_state_persists_across_separate_store_instances_same_file(tmp_path):
    db_path = tmp_path / "watchlist.db"
    WatchlistStore(db_path).add("AAPL")

    store_b = WatchlistStore(db_path)

    assert [i.symbol for i in store_b.list()] == ["AAPL"]


def test_creates_parent_directory_if_missing(tmp_path):
    nested_path = tmp_path / "nested" / "dir" / "watchlist.db"
    store = WatchlistStore(nested_path)

    assert nested_path.exists()
    assert store.list() == []

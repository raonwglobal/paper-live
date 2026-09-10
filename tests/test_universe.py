from paper_live.universe import Security, SecurityMaster


def test_universe_is_deterministic_and_batches():
    master = SecurityMaster([
        Security("000002", "B", "KRX"),
        Security("000001", "A", "KRX"),
        Security("000003", "C", "KRX", active=False),
    ])
    assert master.symbols() == ("000001", "000002")
    assert [[x.symbol for x in b] for b in master.batch(1)] == [["000001"], ["000002"]]


def test_duplicate_universe_rejected():
    try:
        SecurityMaster([Security("1", "A", "KRX"), Security("1", "A2", "KRX")])
        assert False
    except ValueError:
        assert True

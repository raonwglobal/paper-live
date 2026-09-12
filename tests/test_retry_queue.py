from paper_live.retry_queue import RetryItem, RetryQueue


def test_retry_queue_deduplicates_and_bounds_attempts():
    q = RetryQueue(max_attempts=2)
    item = RetryItem("KR", "005930", "2026-09-10", "2026-09-10")
    assert q.enqueue(item)
    assert not q.enqueue(item)
    assert q.record_failure(item, RuntimeError("temporary"))
    assert len(q) == 1
    failed = q.pop_all()
    assert failed[0].attempts == 1
    assert failed[0].last_error == "RuntimeError"
    assert q.record_failure(failed[0], RuntimeError("again")) is False
    assert len(q) == 0

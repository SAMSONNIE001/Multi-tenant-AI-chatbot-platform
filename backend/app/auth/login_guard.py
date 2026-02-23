from collections import defaultdict, deque
from datetime import datetime, timedelta

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
LOCK_SECONDS = 15 * 60

_failures = defaultdict(deque)
_locked_until: dict[str, datetime] = {}


def _prune(key: str, now: datetime) -> None:
    q = _failures[key]
    cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    while q and q[0] < cutoff:
        q.popleft()


def is_locked(key: str) -> datetime | None:
    now = datetime.utcnow()
    locked_until = _locked_until.get(key)
    if not locked_until:
        return None
    if locked_until <= now:
        _locked_until.pop(key, None)
        return None
    return locked_until


def register_failure(key: str) -> datetime | None:
    now = datetime.utcnow()
    _prune(key, now)

    q = _failures[key]
    q.append(now)

    if len(q) >= MAX_FAILURES:
        locked_until = now + timedelta(seconds=LOCK_SECONDS)
        _locked_until[key] = locked_until
        q.clear()
        return locked_until

    return None


def clear_failures(key: str) -> None:
    _failures.pop(key, None)
    _locked_until.pop(key, None)

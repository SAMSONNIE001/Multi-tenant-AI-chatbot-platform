import time
from collections import defaultdict, deque

WINDOW_SECONDS = 60
MAX_PER_TENANT_PER_WINDOW = 60
MAX_PER_USER_PER_WINDOW = 30

_tenant_hits = defaultdict(deque)
_user_hits = defaultdict(deque)


def _prune(q: deque, now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()


def check_rate_limit(*, tenant_id: str, user_id: str) -> tuple[bool, str | None]:
    now = time.time()

    tq = _tenant_hits[tenant_id]
    _prune(tq, now)
    if len(tq) >= MAX_PER_TENANT_PER_WINDOW:
        return False, "rate_limit:tenant"
    tq.append(now)

    uq = _user_hits[user_id]
    _prune(uq, now)
    if len(uq) >= MAX_PER_USER_PER_WINDOW:
        return False, "rate_limit:user"
    uq.append(now)

    return True, None
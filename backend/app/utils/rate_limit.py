"""Small in-memory rate limiters (per process).

Each limiter blocks a key after `max_events` in a sliding `window_seconds`.
Good enough for a single-process deployment; use a shared store such as Redis
if the API runs as multiple processes.
"""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[tuple, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key, now):
        q = self._events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, key) -> int:
        """Seconds until the key may act again (0 = allowed)."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, now)
            if len(q) < self.max_events:
                return 0
            return int(self.window - (now - q[0])) + 1

    def hit(self, key) -> None:
        with self._lock:
            self._events[key].append(time.monotonic())

    def check_and_hit(self, key) -> int:
        """Record an event unless limited. Returns seconds to wait (0 = recorded)."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, now)
            if len(q) >= self.max_events:
                return int(self.window - (now - q[0])) + 1
            q.append(now)
            return 0

    def reset(self, key) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    # Backwards-compatible name used by the login flow.
    fail = hit


# Failed sign-ins per (ip, email).
login_throttle = RateLimiter(max_events=5, window_seconds=900)
# Forgot-password / resend-verification requests.
email_action_per_address = RateLimiter(max_events=3, window_seconds=900)   # per (ip, email)
email_action_per_ip = RateLimiter(max_events=20, window_seconds=3600)      # per ip
# New registrations per IP.
signup_per_ip = RateLimiter(max_events=10, window_seconds=3600)
# Invitation-code / token guessing per IP.
token_attempts_per_ip = RateLimiter(max_events=30, window_seconds=900)

ALL_LIMITERS = (login_throttle, email_action_per_address, email_action_per_ip,
                signup_per_ip, token_attempts_per_ip)


def clear_all() -> None:
    for limiter in ALL_LIMITERS:
        limiter.clear()


# Kept for code that imported the old class name.
LoginThrottle = RateLimiter

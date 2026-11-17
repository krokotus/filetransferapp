import secrets
import time
from dataclasses import dataclass

import config


@dataclass
class Session:
    token: str
    created_at: float
    expires_at: float


class SecurityManager:
    """Управляет временным PIN-кодом и сессиями в памяти процесса."""

    def __init__(self):
        self.pin = ""
        self.pin_expires_at = 0.0
        self.sessions: dict[str, Session] = {}
        self.pin_attempts: dict[str, int] = {}
        self._rotate_pin()

    def _rotate_pin(self):
        self.pin = f"{secrets.randbelow(10**6):06d}"
        self.pin_expires_at = time.time() + config.PIN_TTL_SECONDS
        self.pin_attempts.clear()

    def current_pin(self) -> tuple[str, float]:
        if time.time() >= self.pin_expires_at:
            self._rotate_pin()
        return self.pin, self.pin_expires_at

    def verify_pin(self, ip: str, candidate: str) -> bool:
        if time.time() >= self.pin_expires_at:
            self._rotate_pin()
            return False

        attempts = self.pin_attempts.get(ip, 0)
        if attempts >= config.MAX_PIN_ATTEMPTS:
            return False

        if secrets.compare_digest(candidate.strip(), self.pin):
            self.pin_attempts[ip] = 0
            return True

        self.pin_attempts[ip] = attempts + 1
        return False

    def create_session(self) -> Session:
        now = time.time()
        session = Session(
            token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + config.SESSION_TTL_SECONDS,
        )
        self.sessions[session.token] = session
        return session

    def validate_session(self, token: str | None) -> Session | None:
        if not token:
            return None
        session = self.sessions.get(token)
        if session is None:
            return None
        if time.time() >= session.expires_at:
            self.sessions.pop(token, None)
            return None
        return session

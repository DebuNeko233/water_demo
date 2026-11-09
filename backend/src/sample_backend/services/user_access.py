"""Local operator/admin access and persistent admin-owned detector settings.

The program always starts as an operator. An administrator chooses a password
once, then logs in for an in-memory session. Only the backend can save detector
settings or accept an explicit detector override; the UI alone is not an
authorization boundary. This is device-local access control, not OS security.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from sample_backend.core.config import data_directory
from sample_backend.services.water_session import DetectorSettings

_ITERATIONS = 310_000
_FAILED_LIMIT = 5
_LOCKOUT_SECONDS = 30.0


class AccessDenied(Exception):
    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class LocalUserAccess:
    def __init__(self, path: Path | None = None):
        self._path = path or data_directory() / 'users' / 'admin.json'
        self._lock = threading.RLock()
        self._record: dict | None = None
        self._token: str | None = None
        self._failures = 0
        self._locked_until = 0.0
        if self._path.is_file():
            self._record = json.loads(self._path.read_text(encoding='utf-8'))
            # Fail closed on corrupt credentials and settings; never silently
            # replace an administrator-created profile with open defaults.
            for key in ('salt', 'password_hash', 'settings'):
                if key not in self._record:
                    raise ValueError('Invalid saved administrator credentials')
            DetectorSettings.model_validate(self._record['settings'])

    def _settings(self) -> DetectorSettings:
        if self._record is None:
            return DetectorSettings()
        return DetectorSettings.model_validate(self._record['settings'])

    def public_status(self) -> dict:
        with self._lock:
            return {'role': 'operator', 'admin_configured': self._record is not None,
                    'settings': self._settings().model_dump()}

    @staticmethod
    def _digest(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                  salt, _ITERATIONS)

    def _persist(self) -> None:
        assert self._record is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Restrict the on-disk password hash and settings to the current OS user.
        temporary = self._path.with_name(self._path.name + '.' + secrets.token_hex(6) + '.tmp')
        descriptor = os.open(str(temporary),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(self._record, output, ensure_ascii=False, indent=2)
            os.replace(temporary, self._path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def configure(self, password: str) -> dict:
        if not 8 <= len(password) <= 128:
            raise AccessDenied(422, 'PASSWORD_LENGTH')
        with self._lock:
            if self._record is not None:
                raise AccessDenied(409, 'ADMIN_ALREADY_CONFIGURED')
            salt = secrets.token_bytes(16)
            self._record = {
                'version': 1,
                'salt': base64.b64encode(salt).decode('ascii'),
                'password_hash': base64.b64encode(self._digest(password, salt)).decode('ascii'),
                'settings': DetectorSettings().model_dump(),
            }
            try:
                self._persist()
            except Exception:
                self._record = None
                raise
            self._token = secrets.token_urlsafe(32)
            self._failures = 0
            return {'role': 'admin', 'admin_token': self._token,
                    'settings': self._settings().model_dump()}

    def login(self, password: str) -> dict:
        with self._lock:
            if self._record is None:
                raise AccessDenied(409, 'ADMIN_NOT_CONFIGURED')
            if time.monotonic() < self._locked_until:
                raise AccessDenied(429, 'LOGIN_LOCKED')
            salt = base64.b64decode(self._record['salt'], validate=True)
            expected = base64.b64decode(self._record['password_hash'], validate=True)
            if not hmac.compare_digest(self._digest(password, salt), expected):
                self._failures += 1
                if self._failures >= _FAILED_LIMIT:
                    self._locked_until = time.monotonic() + _LOCKOUT_SECONDS
                    raise AccessDenied(429, 'LOGIN_LOCKED')
                raise AccessDenied(401, 'WRONG_PASSWORD')
            self._failures = 0
            self._locked_until = 0
            # Only one privileged session at a time; another login invalidates
            # any previous administrator session.
            self._token = secrets.token_urlsafe(32)
            return {'role': 'admin', 'admin_token': self._token,
                    'settings': self._settings().model_dump()}

    def _check(self, token: str | None) -> None:
        if (not token or self._token is None
                or not hmac.compare_digest(token, self._token)):
            raise AccessDenied(403, 'ADMIN_REQUIRED')

    def logout(self, token: str) -> dict:
        with self._lock:
            self._check(token)
            self._token = None
            return {'role': 'operator'}

    def approved_settings(self, token: str) -> DetectorSettings:
        """Only authenticated administrators may back up device settings."""
        with self._lock:
            self._check(token)
            return self._settings().model_copy()

    def update_settings(self, token: str, settings: DetectorSettings) -> dict:
        with self._lock:
            self._check(token)
            assert self._record is not None
            old = self._record['settings']
            self._record['settings'] = settings.model_dump()
            try:
                self._persist()
            except Exception:
                self._record['settings'] = old
                raise
            return {'settings': self._settings().model_dump()}

    def resolve_detector(self, requested: DetectorSettings | None,
                         token: str | None = None) -> DetectorSettings:
        with self._lock:
            if requested is not None:
                self._check(token)
                return requested.model_copy()
            # Operators always use the last administrator-approved settings;
            # supplying no detector override is allowed without logging in.
            return self._settings()

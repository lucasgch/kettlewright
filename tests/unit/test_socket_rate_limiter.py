import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.lib.socket_rate_limiter import is_allowed, rate_limited


def unique_key(prefix='test'):
    """Build a unique key so tests don't interfere via the shared storage."""
    return f'{prefix}:{uuid.uuid4()}'


class TestIsAllowed:

    def test_allows_calls_within_limit(self):
        """Calls within the configured limit are allowed."""
        key = unique_key()
        assert is_allowed(key, '3/10seconds') is True
        assert is_allowed(key, '3/10seconds') is True
        assert is_allowed(key, '3/10seconds') is True

    def test_blocks_calls_over_limit(self):
        """Calls beyond the limit in the same window are blocked."""
        key = unique_key()
        assert is_allowed(key, '2/10seconds') is True
        assert is_allowed(key, '2/10seconds') is True
        assert is_allowed(key, '2/10seconds') is False

    def test_allows_again_after_window_expires(self):
        """The limit resets once the window expires."""
        key = unique_key()
        assert is_allowed(key, '1/1second') is True
        assert is_allowed(key, '1/1second') is False
        time.sleep(1.1)
        assert is_allowed(key, '1/1second') is True

    def test_keys_are_independent(self):
        """One user exhausting their limit does not affect another user."""
        key_a = unique_key('user_a')
        key_b = unique_key('user_b')
        assert is_allowed(key_a, '1/10seconds') is True
        assert is_allowed(key_a, '1/10seconds') is False
        assert is_allowed(key_b, '1/10seconds') is True


class TestRateLimitedDecorator:

    @pytest.fixture
    def fake_user(self):
        """Fake authenticated user with a unique id per test."""
        user = MagicMock()
        user.is_authenticated = True
        user.id = str(uuid.uuid4())
        return user

    def test_calls_handler_within_limit(self, fake_user):
        """The decorated handler runs normally while within the limit."""
        calls = []

        @rate_limited('2/10seconds', 'roll_dice')
        def handler(data):
            calls.append(data)

        with patch('app.lib.socket_rate_limiter.current_user', fake_user), \
                patch('app.lib.socket_rate_limiter.emit') as mock_emit:
            handler({'roll': 5})

        assert calls == [{'roll': 5}]
        mock_emit.assert_not_called()

    def test_blocks_handler_and_emits_when_over_limit(self, fake_user):
        """Over the limit the handler is skipped and rate_limited is emitted."""
        calls = []

        @rate_limited('2/10seconds', 'roll_dice')
        def handler(data):
            calls.append(data)

        with patch('app.lib.socket_rate_limiter.current_user', fake_user), \
                patch('app.lib.socket_rate_limiter.emit') as mock_emit:
            handler({'roll': 1})
            handler({'roll': 2})
            handler({'roll': 3})

        assert calls == [{'roll': 1}, {'roll': 2}]
        mock_emit.assert_called_once_with('rate_limited', {'event': 'roll_dice'})

    def test_falls_back_to_sid_for_anonymous_user(self):
        """Unauthenticated clients are keyed by their socket sid."""
        calls = []

        @rate_limited('1/10seconds', 'connect')
        def handler():
            calls.append(True)

        anonymous = MagicMock()
        anonymous.is_authenticated = False
        fake_request = MagicMock()
        fake_request.sid = str(uuid.uuid4())

        with patch('app.lib.socket_rate_limiter.current_user', anonymous), \
                patch('app.lib.socket_rate_limiter.request', fake_request), \
                patch('app.lib.socket_rate_limiter.emit') as mock_emit:
            handler()
            handler()

        assert calls == [True]
        mock_emit.assert_called_once_with('rate_limited', {'event': 'connect'})

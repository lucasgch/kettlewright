import sys
from functools import wraps

from flask import request
from flask_login import current_user
from flask_socketio import emit
from limits import parse
from limits.storage import MemoryStorage, RedisStorage
from limits.strategies import MovingWindowRateLimiter

# Imported lazily via app.socket_events (inside create_app), so use_redis and
# redis_url are already defined. Do not star-import this module from
# app/lib/__init__.py: app/__init__.py imports app.lib before defining them.
from app import use_redis, redis_url

storage = RedisStorage(redis_url) if use_redis else MemoryStorage()
limiter = MovingWindowRateLimiter(storage)


def is_allowed(key: str, rate: str) -> bool:
    return limiter.hit(parse(rate), key)


def rate_limited(rate: str, key_prefix: str):
    def decorator(handler):
        @wraps(handler)
        def wrapper(*args, **kwargs):
            if current_user.is_authenticated:
                key = f'{key_prefix}:{current_user.id}'
            else:
                key = f'{key_prefix}:{request.sid}'

            if not is_allowed(key, rate):
                print(f'Rate limit exceeded for {key}', file=sys.stderr)
                emit('rate_limited', {'event': key_prefix})
                return

            return handler(*args, **kwargs)
        return wrapper
    return decorator

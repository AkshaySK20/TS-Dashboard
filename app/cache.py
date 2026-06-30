from datetime import datetime, timedelta

_cache = {}


def get_cache(key):
    item = _cache.get(key)

    if not item:
        return None

    value, created_at, expires_at = item

    if datetime.now() >= expires_at:
        _cache.pop(key, None)
        return None

    return {
        "value": value,
        "created_at": created_at,
        "expires_at": expires_at,
    }


def set_cache(key, value, ttl_seconds=600):
    created_at = datetime.now()
    expires_at = created_at + timedelta(seconds=ttl_seconds)

    _cache[key] = (value, created_at, expires_at)


def get_cache_meta(key):
    item = _cache.get(key)

    if not item:
        return None

    _, created_at, expires_at = item

    return {
        "created_at": created_at,
        "expires_at": expires_at,
    }


def clear_cache():
    _cache.clear()
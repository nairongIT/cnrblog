import time

import redis
from django.conf import settings


def _get_client():
    return redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        db=getattr(settings, 'REDIS_DB', 0),
        password=getattr(settings, 'REDIS_PASSWORD', None),
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _get_request_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return (request.META.get('REMOTE_ADDR') or '').strip() or 'unknown'


def should_count_site_visit(request):
    """按 IP 1 小时去重统计访问。"""
    ttl = int(getattr(settings, 'SITE_VISIT_LIMIT_SECONDS', 3600))
    ip = _get_request_ip(request)
    redis_key = f"blog:site:visit:{ip}"
    try:
        created = _get_client().set(redis_key, 1, ex=ttl, nx=True)
        return bool(created)
    except Exception:
        # Redis 故障时降级 session 去重
        now_ts = int(time.time())
        history = request.session.get('site_visit_history', {})
        last_ts = int(history.get(ip, 0))
        if now_ts - last_ts < ttl:
            return False
        history[ip] = now_ts
        request.session['site_visit_history'] = history
        return True


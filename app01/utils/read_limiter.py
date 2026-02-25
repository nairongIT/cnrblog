import hashlib
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
    return (request.META.get('REMOTE_ADDR') or '').strip()


def _build_identity(request):
    if request.user.is_authenticated:
        return f"user:{request.user.id}"

    # 匿名用户：IP + UA 指纹，允许同一网络下不同设备分别计数
    ip = _get_request_ip(request) or 'unknown'
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ua_hash = hashlib.md5(user_agent.encode('utf-8')).hexdigest()[:12]
    return f"anon:{ip}:{ua_hash}"


def should_increase_read_count(request, article_id):
    ttl = int(getattr(settings, 'ARTICLE_READ_LIMIT_SECONDS', 3600))
    identity = _build_identity(request)
    redis_key = f"blog:article:read:{article_id}:{identity}"

    try:
        # set nx ex：key 不存在才写入并设置过期时间
        created = _get_client().set(redis_key, 1, ex=ttl, nx=True)
        return bool(created)
    except Exception:
        # Redis 不可用时，降级到 session 防刷，避免功能中断
        now_ts = int(time.time())
        history = request.session.get('article_read_history', {})
        last_ts = int(history.get(str(article_id), 0))
        if now_ts - last_ts < ttl:
            return False
        history[str(article_id)] = now_ts
        request.session['article_read_history'] = history
        return True

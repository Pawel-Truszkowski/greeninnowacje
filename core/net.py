from django.conf import settings


def client_ip(request):
    """Return the real client IP, honouring only the configured number of trusted proxies.

    Each trusted proxy appends the address it received the request from to
    X-Forwarded-For, so the entry `TRUSTED_PROXY_HOPS` positions from the right is the
    client. Anything further left is client-controlled and must not be trusted.
    """
    hops = settings.TRUSTED_PROXY_HOPS
    if hops:
        forwarded = [
            part.strip()
            for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
            if part.strip()
        ]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.META["REMOTE_ADDR"]

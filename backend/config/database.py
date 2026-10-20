from urllib.parse import urlsplit, unquote, parse_qs
from django.core.exceptions import ImproperlyConfigured

def postgres_from_url(value):
    try:
        url=urlsplit(value)
        if url.scheme not in ('postgres','postgresql') or not url.hostname or not url.username or not url.password or not url.path.strip('/'):
            raise ValueError()
        sslmode=parse_qs(url.query).get('sslmode',['require'])[0]
        if sslmode not in ('require','verify-ca','verify-full'): raise ValueError()
        return {'ENGINE':'django.db.backends.postgresql','NAME':unquote(url.path.lstrip('/')),'USER':unquote(url.username),'PASSWORD':unquote(url.password),'HOST':url.hostname,'PORT':url.port or 5432,'OPTIONS':{'sslmode':sslmode,'connect_timeout':10},'CONN_MAX_AGE':0,'DISABLE_SERVER_SIDE_CURSORS':True}
    except (ValueError,TypeError):
        # Never echo a connection string containing credentials.
        raise ImproperlyConfigured('DATABASE_URL must be a complete PostgreSQL URL with TLS enabled.') from None

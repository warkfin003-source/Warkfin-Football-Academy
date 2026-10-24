"""Use the direct database endpoint for migrations; runtime uses the pooled URL."""
import os
from .settings import *  # noqa: F403
from .database import postgres_from_url

if os.environ.get('DATABASE_URL_UNPOOLED'):
    DATABASES = {'default': postgres_from_url(os.environ['DATABASE_URL_UNPOOLED'])}

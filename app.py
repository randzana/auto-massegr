"""Entry point for hosting the web page (Vercel, gunicorn): exposes `app`.

Set WEB_PASSWORD and your provider's keys in the host's environment variables.
"""

from massegr.web import create_app

app = create_app()

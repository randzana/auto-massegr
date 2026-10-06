"""Web page for sending one message to many numbers: python -m massegr.web

The page checks the pasted numbers, then sends to them one by one through
/api/send, so you can watch progress and stop at any time.
"""

import argparse
import hmac
import os
import sys
import threading
import webbrowser
from dataclasses import asdict
from urllib.parse import urlsplit

from flask import Flask, Response, abort, jsonify, request

from .config import load_env
from .contacts import Contact, InvalidNumber, load_optouts, normalize_phone, parse_contacts
from .providers import PROVIDERS, get_provider, is_configured
from .sender import render, send_to_contact

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def _hostname(host):
    return host if host.endswith("]") else host.rsplit(":", 1)[0]


def _error(message, status=400):
    return jsonify(error=message), status


def _body():
    data = request.get_json()  # 415 unless the request is JSON
    if not isinstance(data, dict):
        abort(400)
    return data


def create_app():
    load_env()
    app = Flask(__name__)
    password = os.environ.get("WEB_PASSWORD", "")
    providers = {}

    def optouts(country_code):
        path = os.environ.get("OPTOUT_FILE", "")
        return load_optouts(path, country_code) if path and os.path.exists(path) else set()

    @app.before_request
    def protect():
        if password:
            auth = request.authorization
            given = (auth.password or "") if auth else ""
            if not hmac.compare_digest(given.encode(), password.encode()):
                return Response("Password required", 401,
                                {"WWW-Authenticate": 'Basic realm="auto-massegr"'})
        elif _hostname(request.host) not in LOCAL_HOSTS:
            # Without a password the page only answers on this computer.
            return Response("Set WEB_PASSWORD to use this page from another device.", 403)
        origin = request.headers.get("Origin")
        if request.method == "POST" and origin and urlsplit(origin).netloc != request.host:
            return _error("Cross-site request refused", 403)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/config")
    def config():
        return jsonify(
            providers=[{"id": name, "ready": is_configured(name)} for name in PROVIDERS],
            provider=os.environ.get("PROVIDER", "dry-run"),
            country_code=os.environ.get("DEFAULT_COUNTRY_CODE", ""),
            delay=float(os.environ.get("SEND_DELAY", "1")),
        )

    @app.post("/api/check")
    def check():
        data = _body()
        country_code = str(data.get("country_code", "")).strip()
        contacts, errors = parse_contacts(str(data.get("numbers", "")), country_code)
        if not contacts:
            return _error("No valid phone numbers found.")
        try:
            preview = render(str(data.get("message", "")).strip(), contacts[0])
        except (ValueError, IndexError) as e:
            return _error(f"Bad message text ({e}). Use {{name}} for names "
                          "and {{{{ }}}} for curly braces.")
        blocked = optouts(country_code)
        return jsonify(
            contacts=[{"phone": c.phone, "name": c.name, "optout": c.phone in blocked}
                      for c in contacts],
            errors=errors,
            preview=preview,
        )

    @app.post("/api/send")
    def send():
        data = _body()
        name = data.get("provider", "")
        if name not in PROVIDERS:
            return _error(f"Unknown provider {name!r}")
        if not is_configured(name):
            return _error(f"{name} is not set up yet: add its keys to .env")
        if name not in providers:
            providers[name] = get_provider(name)
        provider = providers[name]

        message = str(data.get("message", "")).strip()
        if not message and not provider.allows_empty_body:
            return _error("The message is empty.")
        country_code = str(data.get("country_code", "")).strip()
        try:
            phone = normalize_phone(data.get("phone", ""), country_code)
        except InvalidNumber as e:
            return _error(str(e))
        contact = Contact(phone, str(data.get("name", "")), {"name": str(data.get("name", ""))})
        try:
            result = send_to_contact(provider, contact, message, optouts=optouts(country_code))
        except (ValueError, IndexError) as e:
            return _error(f"Bad message text ({e})")
        return jsonify(asdict(result))

    return app


def main(argv=None):
    load_env()
    p = argparse.ArgumentParser(prog="massegr.web", description=__doc__.splitlines()[0])
    p.add_argument("--host", default="127.0.0.1",
                   help="use 0.0.0.0 to open it from your phone on the same Wi-Fi "
                        "(needs WEB_PASSWORD)")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = p.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("WEB_PASSWORD"):
        sys.exit("Set WEB_PASSWORD in .env before opening the page to other devices.")

    url = f"http://127.0.0.1:{args.port}/"
    print(f"auto-massegr is running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    create_app().run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()

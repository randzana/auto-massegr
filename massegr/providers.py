"""Messaging back-ends. Each provider sends one message to one number."""

import os

import requests

TIMEOUT = 30


class SendError(Exception):
    """A message could not be sent. `retryable` marks rate limits / outages."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def _require_env(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            "Missing settings: " + ", ".join(missing) + " (put them in .env)"
        )
    return [os.environ[n] for n in names]


def _check_response(resp):
    if resp.status_code == 429 or resp.status_code >= 500:
        raise SendError(f"HTTP {resp.status_code}: {resp.text[:300]}", retryable=True)
    if resp.status_code >= 400:
        raise SendError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


class DryRunProvider:
    """Prints messages instead of sending them. Use it to test your list."""

    name = "dry-run"
    allows_empty_body = False

    def send(self, to, body):
        print(f"  [dry-run] -> {to}: {body!r}")
        return "dry-run"


class TwilioProvider:
    """SMS or WhatsApp through Twilio (https://www.twilio.com)."""

    def __init__(self, whatsapp=False, session=None):
        self.name = "twilio-whatsapp" if whatsapp else "twilio-sms"
        self.allows_empty_body = False
        self.whatsapp = whatsapp
        sid, token = _require_env("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
        from_var = "TWILIO_WHATSAPP_FROM" if whatsapp else "TWILIO_FROM"
        (self.sender,) = _require_env(from_var)
        self.url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        self.session = session or requests.Session()
        self.session.auth = (sid, token)

    def _addr(self, number):
        if self.whatsapp and not number.startswith("whatsapp:"):
            return "whatsapp:" + number
        return number

    def send(self, to, body):
        try:
            resp = self.session.post(
                self.url,
                data={"To": self._addr(to), "From": self._addr(self.sender), "Body": body},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise SendError(str(e), retryable=True) from e
        return _check_response(resp).get("sid", "")


class WhatsAppCloudProvider:
    """WhatsApp Business Cloud API from Meta (https://developers.facebook.com/docs/whatsapp).

    WhatsApp only lets businesses start a conversation with an approved
    template. Set WHATSAPP_TEMPLATE to send one (the message text, if any,
    fills its {{1}} variable); otherwise a plain text message is sent, which
    only works with people who wrote to you in the last 24 hours.
    """

    name = "whatsapp-cloud"

    def __init__(self, session=None):
        token, phone_id = _require_env("WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID")
        version = os.environ.get("WHATSAPP_API_VERSION", "v21.0")
        self.url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
        self.template = os.environ.get("WHATSAPP_TEMPLATE", "")
        self.language = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en_US")
        self.allows_empty_body = bool(self.template)
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def payload(self, to, body):
        data = {"messaging_product": "whatsapp", "to": to.lstrip("+")}
        if self.template:
            data["type"] = "template"
            data["template"] = {"name": self.template, "language": {"code": self.language}}
            if body:
                data["template"]["components"] = [
                    {"type": "body", "parameters": [{"type": "text", "text": body}]}
                ]
        else:
            data["type"] = "text"
            data["text"] = {"body": body}
        return data

    def send(self, to, body):
        try:
            resp = self.session.post(self.url, json=self.payload(to, body), timeout=TIMEOUT)
        except requests.RequestException as e:
            raise SendError(str(e), retryable=True) from e
        messages = _check_response(resp).get("messages") or [{}]
        return messages[0].get("id", "")


PROVIDERS = {
    "dry-run": DryRunProvider,
    "twilio-sms": lambda: TwilioProvider(whatsapp=False),
    "twilio-whatsapp": lambda: TwilioProvider(whatsapp=True),
    "whatsapp-cloud": WhatsAppCloudProvider,
}


def get_provider(name):
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise SystemExit(f"Unknown provider {name!r}. Choose: {', '.join(PROVIDERS)}")

import base64
import os
import tempfile
import unittest
from unittest import mock

from massegr.web import create_app

PROVIDER_VARS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "TWILIO_WHATSAPP_FROM",
                 "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_TEMPLATE",
                 "WEB_PASSWORD", "OPTOUT_FILE", "PROVIDER", "DEFAULT_COUNTRY_CODE")


class WebTests(unittest.TestCase):
    def client(self, **env):
        clean = {k: v for k, v in os.environ.items() if k not in PROVIDER_VARS}
        patcher = mock.patch.dict(os.environ, {**clean, **env}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        with mock.patch("massegr.web.load_env"):
            return create_app().test_client()

    def test_page_and_config(self):
        c = self.client(DEFAULT_COUNTRY_CODE="964")
        with c.get("/") as page:
            self.assertIn(b"auto-massegr", page.data)
        cfg = c.get("/api/config").get_json()
        ready = {p["id"]: p["ready"] for p in cfg["providers"]}
        self.assertTrue(ready["dry-run"])
        self.assertFalse(ready["twilio-sms"])
        self.assertEqual(cfg["country_code"], "964")

    def test_check(self):
        c = self.client()
        r = c.post("/api/check", json={
            "numbers": "0750 123 4567, Ali\nnot a number\n0750-123-4567\n0770 111 2222 , 0771 111 2222",
            "message": "Silaw {name}!", "country_code": "964"})
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["phone"] for x in data["contacts"]],
                         ["+9647501234567", "+9647701112222", "+9647711112222"])
        self.assertEqual(data["preview"], "Silaw Ali!")
        self.assertEqual(len(data["errors"]), 1)

    def test_check_errors(self):
        c = self.client()
        self.assertEqual(c.post("/api/check", json={"numbers": "", "message": "hi"}).status_code, 400)
        r = c.post("/api/check", json={"numbers": "+9647501234567", "message": "Hi {"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Bad message", r.get_json()["error"])

    def test_send_dry_run(self):
        c = self.client()
        with mock.patch("builtins.print"):
            r = c.post("/api/send", json={"phone": "0750 123 4567", "name": "Ali",
                                          "message": "Hi {name}", "provider": "dry-run",
                                          "country_code": "964"})
        self.assertEqual(r.get_json(), {"phone": "+9647501234567", "name": "Ali",
                                        "status": "sent", "message_id": "dry-run", "error": ""})

    def test_send_optout(self):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as f:
            f.write("0750 123 4567\n")
        self.addCleanup(os.remove, path)
        c = self.client(OPTOUT_FILE=path)
        r = c.post("/api/send", json={"phone": "+9647501234567", "message": "Hi",
                                      "provider": "dry-run", "country_code": "964"})
        self.assertEqual(r.get_json()["status"], "skipped")

    def test_send_rejects_bad_requests(self):
        c = self.client()
        ok = {"phone": "+9647501234567", "message": "Hi", "provider": "dry-run"}
        self.assertEqual(c.post("/api/send", json={**ok, "provider": "nope"}).status_code, 400)
        self.assertEqual(c.post("/api/send", json={**ok, "provider": "twilio-sms"}).status_code, 400)
        self.assertEqual(c.post("/api/send", json={**ok, "phone": "123"}).status_code, 400)
        self.assertEqual(c.post("/api/send", json={**ok, "message": " "}).status_code, 400)
        self.assertEqual(c.post("/api/send", data="phone=1").status_code, 415)
        self.assertEqual(c.post("/api/send", json=ok,
                                headers={"Origin": "https://evil.example"}).status_code, 403)

    def test_without_password_only_local(self):
        c = self.client()
        self.assertEqual(c.get("/", base_url="http://192.168.1.5:8000").status_code, 403)
        with c.get("/", base_url="http://127.0.0.1:8000") as page:
            self.assertEqual(page.status_code, 200)

    def test_password(self):
        c = self.client(WEB_PASSWORD="secret")
        self.assertEqual(c.get("/", base_url="http://192.168.1.5:8000").status_code, 401)
        token = base64.b64encode(b"me:secret").decode()
        with c.get("/", base_url="http://192.168.1.5:8000",
                   headers={"Authorization": "Basic " + token}) as page:
            self.assertEqual(page.status_code, 200)
        wrong = base64.b64encode(b"me:nope").decode()
        self.assertEqual(c.get("/", headers={"Authorization": "Basic " + wrong}).status_code, 401)


if __name__ == "__main__":
    unittest.main()

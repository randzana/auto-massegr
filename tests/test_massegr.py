import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from massegr.__main__ import main
from massegr.contacts import Contact, InvalidNumber, load_contacts, normalize_phone
from massegr.providers import SendError, TwilioProvider, WhatsAppCloudProvider
from massegr.sender import render, send_all


def write_tmp(test, text, suffix=".csv"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    test.addCleanup(os.remove, path)
    return path


class NormalizeTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(normalize_phone("+964 750 123 4567"), "+9647501234567")
        self.assertEqual(normalize_phone("009647501234567"), "+9647501234567")
        self.assertEqual(normalize_phone("0750-123-4567", "964"), "+9647501234567")
        self.assertEqual(normalize_phone("9647501234567", "964"), "+9647501234567")

    def test_invalid(self):
        for bad in ("hello", "0750123", "07501234567", "+0123456789"):
            with self.assertRaises(InvalidNumber, msg=bad):
                normalize_phone(bad)


class LoadContactsTests(unittest.TestCase):
    def test_csv_with_header_dedup_and_errors(self):
        path = write_tmp(self, "Phone,Name,City\n+9647501234567,Ali,Erbil\n"
                               "0750 123 4567,Dup,\nnope,Bad,\n\n0770 111 2222,Sara\n")
        contacts, errors = load_contacts(path, "964")
        self.assertEqual([c.phone for c in contacts], ["+9647501234567", "+9647701112222"])
        self.assertEqual(contacts[0].fields["city"], "Erbil")
        self.assertEqual(len(errors), 1)

    def test_plain_list(self):
        path = write_tmp(self, "+9647501234567\n# comment\n+9647701112222,Sara\n", ".txt")
        contacts, errors = load_contacts(path)
        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[1].name, "Sara")
        self.assertEqual(errors, [])


class FakeProvider:
    name = "fake"

    def __init__(self, failures=None):
        self.failures = dict(failures or {})
        self.sent = []

    def send(self, to, body):
        err = self.failures.get(to)
        if err:
            if err.retryable:
                self.failures.pop(to)
            raise err
        self.sent.append((to, body))
        return "id-" + to


class SendAllTests(unittest.TestCase):
    def test_render(self):
        c = Contact("+9647501234567", "Ali", {"city": "Erbil"})
        self.assertEqual(render("Hi {name} from {city}{missing}", c), "Hi Ali from Erbil")

    def test_send_retry_optout_and_failure(self):
        contacts = [Contact("+1000000001", "A"), Contact("+1000000002", "B"),
                    Contact("+1000000003", "C"), Contact("+1000000004", "D")]
        provider = FakeProvider({
            "+1000000002": SendError("429", retryable=True),
            "+1000000003": SendError("bad number"),
        })
        sleeps = []
        report = write_tmp(self, "")
        results = send_all(contacts, "Hi {name}", provider, delay=0.5, optouts={"+1000000004"},
                           report_path=report, sleep=sleeps.append, log=lambda *_: None)

        self.assertEqual([r.status for r in results], ["sent", "sent", "failed", "skipped"])
        self.assertEqual(provider.sent, [("+1000000001", "Hi A"), ("+1000000002", "Hi B")])
        self.assertEqual(sleeps, [0.5, 2, 0.5, 0.5])
        with open(report, encoding="utf-8") as f:
            self.assertEqual(len(f.read().strip().splitlines()), 5)


class ProviderTests(unittest.TestCase):
    def response(self, status, payload):
        resp = mock.Mock(status_code=status, text=str(payload))
        resp.json.return_value = payload
        return resp

    def test_twilio_whatsapp(self):
        env = {"TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "t",
               "TWILIO_WHATSAPP_FROM": "+14155238886"}
        session = mock.Mock()
        session.post.return_value = self.response(201, {"sid": "SM1"})
        with mock.patch.dict(os.environ, env):
            provider = TwilioProvider(whatsapp=True, session=session)
        self.assertEqual(provider.send("+9647501234567", "hi"), "SM1")
        data = session.post.call_args.kwargs["data"]
        self.assertEqual(data["To"], "whatsapp:+9647501234567")
        self.assertEqual(data["From"], "whatsapp:+14155238886")

    def test_twilio_errors(self):
        env = {"TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "t", "TWILIO_FROM": "+1555"}
        session = mock.Mock()
        with mock.patch.dict(os.environ, env):
            provider = TwilioProvider(session=session)
        session.post.return_value = self.response(429, {})
        with self.assertRaises(SendError) as ctx:
            provider.send("+9647501234567", "hi")
        self.assertTrue(ctx.exception.retryable)
        session.post.return_value = self.response(400, {"message": "bad"})
        with self.assertRaises(SendError) as ctx:
            provider.send("+9647501234567", "hi")
        self.assertFalse(ctx.exception.retryable)

    def test_whatsapp_cloud_text_and_template(self):
        env = {"WHATSAPP_TOKEN": "tok", "WHATSAPP_PHONE_NUMBER_ID": "123"}
        session = mock.Mock(headers={})
        session.post.return_value = self.response(200, {"messages": [{"id": "wamid.1"}]})
        with mock.patch.dict(os.environ, env):
            provider = WhatsAppCloudProvider(session=session)
        self.assertEqual(provider.send("+9647501234567", "hi"), "wamid.1")
        sent = session.post.call_args.kwargs["json"]
        self.assertEqual(sent["to"], "9647501234567")
        self.assertEqual(sent["text"], {"body": "hi"})
        self.assertFalse(provider.allows_empty_body)

        with mock.patch.dict(os.environ, {**env, "WHATSAPP_TEMPLATE": "hello_world"}):
            provider = WhatsAppCloudProvider(session=session)
        self.assertTrue(provider.allows_empty_body)
        self.assertNotIn("components", provider.payload("+1", "")["template"])
        params = provider.payload("+1", "Ali")["template"]["components"][0]["parameters"]
        self.assertEqual(params, [{"type": "text", "text": "Ali"}])


class CliTests(unittest.TestCase):
    def test_dry_run(self):
        contacts = write_tmp(self, "phone,name\n0750 123 4567,Ali\nbad,X\n")
        report = write_tmp(self, "")
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("massegr.__main__.load_env"), \
                mock.patch("sys.stderr", io.StringIO()):
            code = main(["--contacts", contacts, "--message", "Silaw {name}",
                         "--provider", "dry-run", "--country-code", "964",
                         "--delay", "0", "--report", report])
        self.assertEqual(code, 0)
        self.assertIn("+9647501234567: 'Silaw Ali'", out.getvalue())
        self.assertIn("1 sent, 0 failed", out.getvalue())


if __name__ == "__main__":
    unittest.main()

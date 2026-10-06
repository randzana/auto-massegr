# auto-massegr

A small Python bot that sends one message to a whole list of phone numbers
in one go, by **SMS** or **WhatsApp**, through official APIs (Twilio or
Meta's WhatsApp Cloud API).

- Reads numbers from a CSV (`phone,name,...`) or a plain list, one per line
- Fixes number formats: `0750 123 4567`, `00964...` and `+964...` all work
- Personalises each message: `Silaw {name}!` (any CSV column can be used)
- Drops duplicate and invalid numbers, skips anyone on an opt-out list
- Waits between messages and retries on rate limits / network errors
- Shows a preview and asks before sending; saves results to `report.csv`
- `dry-run` mode prints the messages without sending, to test your list
- A **web page**: paste all your numbers, write the message, press Send

## Bo Kurdi (ba kurti)

1. Python 3.9 yan nwetr dabmazrena, pashan: `pip install -r requirements.txt`
2. `.env.example` kopi bka bo `.env`, w zanyariakani Twilio yan WhatsApp-i
   tya bnusa.

**Ba web (asantrin rega):**

```
python -m massegr.web
```

Browser khoy dakretawa (`http://127.0.0.1:8000`). Hamuw raqamakan la
sandwqi yakam paste bka (har raqamek la heleki), namaka bnusa, "Check
numbers" w pashan "Send" dabgra. Har raqamek dabinit nardra yan na.

**Ba command line:**

3. Listi raqamakan la `contacts.csv` dabne (wak `contacts.example.csv`).
4. Sarata taqi bkarawa - hich nanert, tanha nishani dadat:

   ```
   python -m massegr --contacts contacts.csv --message "Silaw {name}!"
   ```

5. Bo nardni rastaqina, `--provider` diari bka:

   ```
   python -m massegr --contacts contacts.csv --message-file message.txt --provider twilio-sms
   ```

Tanha nama bo kasanek bnera ka razin. Raqami awanai nayanawet nama
wargrn la `optout.txt` dabne w `--optout optout.txt` bakarbhena.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env              # then fill in your provider's keys
cp contacts.example.csv contacts.csv
cp message.example.txt message.txt
```

## Web page

```bash
python -m massegr.web
```

Your browser opens `http://127.0.0.1:8000`. Paste the numbers (one per line,
optionally `number, name`), write the message, press **Check numbers** to see
how many are valid plus a preview, then **Send**. Each number shows `sent` or
`failed` as it goes, you can **Stop** at any time, and **Download report**
saves the results as CSV. Pick `dry-run` under "Send with" to try it without
sending anything.

The page only answers on your own computer. To open it from your phone on the
same Wi-Fi, set `WEB_PASSWORD` in `.env` and run
`python -m massegr.web --host 0.0.0.0`, then visit `http://<computer-ip>:8000`.
Anyone with that password can send messages on your account, so choose a
strong one.

## Command line

Test first with the default `dry-run` provider (nothing is sent):

```bash
python -m massegr --contacts contacts.csv --message "Silaw {name}!"
```

Then send for real:

```bash
python -m massegr --contacts contacts.csv --message-file message.txt --provider twilio-sms
```

| Option | Meaning |
| --- | --- |
| `--contacts FILE` | CSV with a `phone` column, or one number per line |
| `--message TEXT` / `--message-file FILE` | The text; `{name}`, `{phone}` and other CSV columns are filled in |
| `--provider` | `dry-run`, `twilio-sms`, `twilio-whatsapp`, `whatsapp-cloud` (default `$PROVIDER` or `dry-run`) |
| `--country-code 964` | Prefix for local numbers starting with `0` (default `$DEFAULT_COUNTRY_CODE`) |
| `--delay 1` | Seconds between messages |
| `--retries 3` | Retries on HTTP 429 / 5xx / network errors |
| `--optout FILE` | Numbers that must never be messaged |
| `--report report.csv` | Per-number result: `sent`, `failed` or `skipped` |
| `-y` | Don't ask for confirmation |

Press `Ctrl+C` to stop; the report still lists everything sent so far.

## Providers

**Twilio SMS / WhatsApp** — create an account at twilio.com and set
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM` (SMS) or
`TWILIO_WHATSAPP_FROM` (WhatsApp). A trial account can only send to numbers
you have verified in the Twilio console.

**WhatsApp Cloud API (Meta)** — set `WHATSAPP_TOKEN` and
`WHATSAPP_PHONE_NUMBER_ID` from your Meta developer app. WhatsApp only lets a
business start a conversation with an **approved template**: set
`WHATSAPP_TEMPLATE` (and `WHATSAPP_TEMPLATE_LANG`). The message text, if
given, fills the template's `{{1}}` variable; for a template without
variables use `--message ""`. Without a template, plain text only reaches
people who messaged you in the last 24 hours.

## Use it responsibly

Only message people who agreed to hear from you, and honour opt-outs.
Carriers and WhatsApp block senders that get reported as spam. This bot uses
official APIs on purpose: tools that automate WhatsApp Web get the sending
number banned.

## Tests

```bash
python -m unittest -v
```

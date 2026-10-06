"""Command line: python -m massegr --contacts contacts.csv --message "Hello {name}" """

import argparse
import os
import sys

from .contacts import load_contacts, load_optouts
from .providers import PROVIDERS, get_provider
from .sender import render, send_all


def load_env(path=".env"):
    """Minimal .env reader: KEY=value lines; real environment variables win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="massegr",
        description="Send one message to a list of phone numbers.",
    )
    p.add_argument("--contacts", required=True,
                   help="CSV with a 'phone' column (and optional 'name', ...) "
                        "or a text file with one number per line")
    msg = p.add_mutually_exclusive_group(required=True)
    msg.add_argument("--message", help="message text; {name} etc. are filled from the CSV")
    msg.add_argument("--message-file", help="read the message text from this file")
    p.add_argument("--provider", choices=list(PROVIDERS),
                   default=os.environ.get("PROVIDER", "dry-run"),
                   help="where to send through (default: $PROVIDER or dry-run)")
    p.add_argument("--country-code", default=os.environ.get("DEFAULT_COUNTRY_CODE", ""),
                   help="added to local numbers that start with 0, e.g. 964")
    p.add_argument("--delay", type=float, default=float(os.environ.get("SEND_DELAY", "1")),
                   help="seconds to wait between messages (default 1)")
    p.add_argument("--retries", type=int, default=3,
                   help="retries on rate limits / network errors (default 3)")
    p.add_argument("--optout", help="file of numbers that must not be messaged")
    p.add_argument("--report", default="report.csv",
                   help="where to save the per-number results (default report.csv)")
    p.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    return p.parse_args(argv)


def main(argv=None):
    load_env()
    args = parse_args(argv)

    if args.message_file:
        with open(args.message_file, encoding="utf-8") as f:
            template = f.read().strip()
    else:
        template = args.message.strip()

    contacts, errors = load_contacts(args.contacts, args.country_code)
    for err in errors:
        print(f"Skipping {err}", file=sys.stderr)
    if not contacts:
        sys.exit("No valid phone numbers found.")

    optouts = load_optouts(args.optout, args.country_code) if args.optout else set()
    provider = get_provider(args.provider)

    if not template and not provider.allows_empty_body:
        sys.exit("The message is empty.")
    try:
        preview = render(template, contacts[0])
    except (ValueError, IndexError) as e:
        sys.exit(f"Bad message text ({e}). Use {{name}} for fields and {{{{ }}}} for braces.")

    to_send = sum(c.phone not in optouts for c in contacts)
    print(f"Provider : {provider.name}")
    print(f"Numbers  : {to_send} to send, {len(contacts) - to_send} opted out, "
          f"{len(errors)} invalid")
    print(f"Preview  : {preview}")
    if not args.yes and provider.name != "dry-run":
        if input("Send now? [y/N] ").strip().lower() not in ("y", "yes"):
            sys.exit("Cancelled.")

    results = send_all(contacts, template, provider, delay=args.delay,
                       retries=args.retries, optouts=optouts, report_path=args.report)

    counts = {s: sum(r.status == s for r in results) for s in ("sent", "failed", "skipped")}
    print(f"\nDone: {counts['sent']} sent, {counts['failed']} failed, "
          f"{counts['skipped']} skipped. Report: {args.report}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

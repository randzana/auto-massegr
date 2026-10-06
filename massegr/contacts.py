"""Load and normalise the list of phone numbers to message."""

import csv
import re
from dataclasses import dataclass, field

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class InvalidNumber(ValueError):
    pass


@dataclass
class Contact:
    phone: str
    name: str = ""
    fields: dict = field(default_factory=dict)


def normalize_phone(raw, default_country_code=""):
    """Return `raw` in E.164 form (+9647501234567) or raise InvalidNumber.

    Local numbers that start with a single 0 (e.g. 0750 123 4567) get
    `default_country_code` (e.g. "964") in place of the 0.
    """
    number = re.sub(r"[\s\-().]", "", str(raw))
    if number.startswith("00"):
        number = "+" + number[2:]
    elif number.startswith("0") and default_country_code:
        number = "+" + default_country_code.lstrip("+") + number[1:]
    elif not number.startswith("+") and default_country_code and number.isdigit():
        if not number.startswith(default_country_code.lstrip("+")):
            raise InvalidNumber(f"{raw!r}: start it with + and the country code")
        number = "+" + number
    if not E164_RE.match(number):
        raise InvalidNumber(f"{raw!r} is not a valid phone number")
    return number


PHONE_CHARS_RE = re.compile(r"^[+\d\s\-().]+$")


def load_contacts(path, default_country_code=""):
    """Read contacts from a CSV file; see parse_contacts."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return parse_contacts(f.read(), default_country_code)


def parse_contacts(text, default_country_code=""):
    """Read contacts from CSV text with a `phone` column (other columns optional).

    Plain text with one number per line (optionally `number, name`) also works.
    Returns (contacts, errors): duplicates are dropped, bad rows go to errors.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return [], []

    header = [h.strip().lower() for h in next(csv.reader([lines[0]]))]
    if "phone" in header:
        rows = [
            {k: (v or "").strip() for k, v in row.items() if k is not None}
            for row in csv.DictReader(lines[1:], fieldnames=header)
        ]
    else:
        rows = []
        for cols in csv.reader(lines):
            cols = [c.strip() for c in cols if c.strip()]
            if len(cols) > 1 and all(PHONE_CHARS_RE.match(c) for c in cols):
                rows.extend({"phone": c, "name": ""} for c in cols)
            elif cols:
                rows.append({"phone": cols[0], "name": cols[1] if len(cols) > 1 else ""})

    contacts, errors, seen = [], [], set()
    for line_no, row in enumerate(rows, start=1):
        raw = row.get("phone", "")
        if not raw or raw.startswith("#"):
            continue
        try:
            phone = normalize_phone(raw, default_country_code)
        except InvalidNumber as e:
            errors.append(f"row {line_no}: {e}")
            continue
        if phone in seen:
            continue
        seen.add(phone)
        contacts.append(Contact(phone=phone, name=row.get("name", ""), fields=row))
    return contacts, errors


def load_optouts(path, default_country_code=""):
    """Numbers (one per line) that must never be messaged."""
    optouts = set()
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                optouts.add(normalize_phone(line, default_country_code))
            except InvalidNumber:
                pass
    return optouts

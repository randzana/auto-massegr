"""Send one message to every contact, politely and with a report."""

import csv
import time
from dataclasses import dataclass

from .providers import SendError


class _Blank(dict):
    def __missing__(self, key):
        return ""


def render(template, contact):
    """Fill {name}, {phone} and any other CSV column into the message."""
    values = _Blank(contact.fields)
    values.update(phone=contact.phone, name=contact.name)
    return template.format_map(values)


@dataclass
class Result:
    phone: str
    name: str
    status: str  # sent | failed | skipped
    message_id: str = ""
    error: str = ""


def send_one(provider, to, body, retries, sleep=time.sleep):
    """Send with exponential back-off on rate limits and outages."""
    for attempt in range(retries + 1):
        try:
            return provider.send(to, body)
        except SendError as e:
            if not e.retryable or attempt == retries:
                raise
            sleep(2 ** attempt * 2)


def send_to_contact(provider, contact, template, retries=3, optouts=(), sleep=time.sleep):
    """Send the message to one contact and return a Result (never raises SendError)."""
    if contact.phone in optouts:
        return Result(contact.phone, contact.name, "skipped", error="opted out")
    try:
        message_id = send_one(provider, contact.phone, render(template, contact),
                              retries, sleep)
    except SendError as e:
        return Result(contact.phone, contact.name, "failed", error=str(e))
    return Result(contact.phone, contact.name, "sent", message_id)


def send_all(contacts, template, provider, delay=1.0, retries=3, optouts=(),
             report_path=None, sleep=time.sleep, log=print):
    results = []
    total = len(contacts)
    try:
        for i, contact in enumerate(contacts, start=1):
            result = send_to_contact(provider, contact, template, retries, optouts, sleep)
            results.append(result)
            if result.status == "sent":
                log(f"[{i}/{total}] {contact.phone} sent")
            elif result.status == "skipped":
                log(f"[{i}/{total}] {contact.phone} skipped ({result.error})")
                continue
            else:
                log(f"[{i}/{total}] {contact.phone} FAILED: {result.error}")
            if delay and i < total:
                sleep(delay)
    except KeyboardInterrupt:
        log("\nStopped by user.")
    finally:
        if report_path:
            write_report(report_path, results)
    return results


def write_report(path, results):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["phone", "name", "status", "message_id", "error"])
        for r in results:
            writer.writerow([r.phone, r.name, r.status, r.message_id, r.error])

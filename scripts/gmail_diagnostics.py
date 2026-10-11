"""Safe Gmail/IMAP diagnostics; never fetches bodies or executes requests."""

import imaplib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import database


def yes_no(value):
    return "yes" if value else "no"


def main():
    print("Gmail/IMAP configuration")
    print("  listener enabled:", yes_no(config.INBOUND_EMAIL_ENABLED))
    print("  host configured:", yes_no(config.IMAP_HOST))
    print("  username configured:", yes_no(config.IMAP_USERNAME))
    print("  password configured:", yes_no(config.IMAP_PASSWORD))
    print("  allowed requesters:", len(config.EMAIL_REQUEST_SENDERS))
    print("  allowed approvers:", len(config.EMAIL_APPROVERS))
    print("  polling interval:", config.INBOUND_EMAIL_POLL_SECONDS, "seconds")

    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT status, details, last_heartbeat
                FROM ops_agent.component_health WHERE component = 'inbound_email'""")
            row = cursor.fetchone()
            print("  listener heartbeat:", row if row else "not recorded")

    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as mailbox:
        mailbox.login(config.IMAP_USERNAME, config.IMAP_PASSWORD)
        status, _ = mailbox.select(config.IMAP_FOLDER, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Cannot select IMAP folder {config.IMAP_FOLDER!r}")
        status, data = mailbox.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("IMAP unread-message search failed")
        print("  mailbox connection: successful")
        print("  unread messages waiting:", len(data[0].split()))
        print("No message bodies were fetched and no action was executed.")


if __name__ == "__main__":
    main()

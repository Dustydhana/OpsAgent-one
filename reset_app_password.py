"""Interactive local recovery for an existing OpsAgent application account."""

from getpass import getpass

import auth


def main():
    username = input("Existing username: ").strip()
    password = getpass("New password: ")
    confirmation = getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    auth.reset_password(username, password, actor="local-recovery")
    print(f"Password reset successfully for {username}.")


if __name__ == "__main__":
    main()

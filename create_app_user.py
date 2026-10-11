"""Interactively create an OpsAgent Streamlit user in PostgreSQL."""

import getpass

import auth


def main():
    print("Create an A2Z OpsAgent application user")
    username = input("Username: ").strip()
    display_name = input("Display name: ").strip()
    role = input("Role [Admin/Operator/Viewer] (Admin): ").strip() or "Admin"
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match; no user was created.")
    user = auth.create_user(
        username, password, role, display_name=display_name, created_by="local-bootstrap"
    )
    print(f"Created {user['username']} with role {user['role']}.")


if __name__ == "__main__":
    main()

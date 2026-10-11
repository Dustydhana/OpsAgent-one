"""Fail deployment early when essential production settings are unsafe."""
import os
import sys
from urllib.parse import urlparse


def flag(name):
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def validate():
    errors, warnings = [], []
    database_url = os.getenv("DATABASE_URL", "").strip()
    frontend = os.getenv("OPSAGENT_FRONTEND_URL", "").strip()
    callback = os.getenv("OPSAGENT_OAUTH_CALLBACK_BASE", "").strip()
    secret = os.getenv("OPSAGENT_API_SECRET", "")
    origins = [x.strip() for x in os.getenv("OPSAGENT_CORS_ORIGINS", "").split(",") if x.strip()]

    if urlparse(database_url).scheme not in {"postgres", "postgresql"}:
        errors.append("DATABASE_URL must be a PostgreSQL connection URL")
    if len(secret) < 48:
        errors.append("OPSAGENT_API_SECRET must contain at least 48 characters")
    for name, value in (("OPSAGENT_FRONTEND_URL", frontend), ("OPSAGENT_OAUTH_CALLBACK_BASE", callback)):
        if not value.startswith("https://"):
            errors.append(f"{name} must use https://")
    if frontend and frontend not in origins:
        errors.append("OPSAGENT_CORS_ORIGINS must contain OPSAGENT_FRONTEND_URL exactly")
    if not flag("OPSAGENT_COOKIE_SECURE"):
        errors.append("OPSAGENT_COOKIE_SECURE must be true")
    if flag("APP_SIGNUP_ENABLED"):
        warnings.append("APP_SIGNUP_ENABLED is public; keep false unless intentional")
    if not flag("AWS_DRY_RUN") or not flag("VMWARE_DRY_RUN") or not flag("SSM_OPERATIONS_DRY_RUN"):
        warnings.append("One or more infrastructure providers are enabled for live changes")
    if flag("OPSAGENT_CONNECTORS_IN_API"):
        warnings.append("Background connectors in the web process are unsuitable for multiple replicas")
    if not os.getenv("OPSAGENT_DEFAULT_ORGANIZATION_ID", "").strip():
        warnings.append("OPSAGENT_DEFAULT_ORGANIZATION_ID is unset; org-default will own legacy/background data")

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        raise SystemExit(1)
    print("Production environment validation passed")


if __name__ == "__main__":
    validate()

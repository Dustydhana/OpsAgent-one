"""OAuth/OIDC provider registry. Secrets are read only from server environment variables."""
import os
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()

PROVIDERS = {
    "google": {
        "label": "Google", "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        "client_kwargs": {"scope": "openid email profile"},
    },
    "microsoft": {
        "label": "Microsoft", "client_id": os.getenv("MICROSOFT_CLIENT_ID"),
        "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET"),
        "server_metadata_url": f"https://login.microsoftonline.com/{os.getenv('MICROSOFT_TENANT_ID','common')}/v2.0/.well-known/openid-configuration",
        "client_kwargs": {"scope": "openid email profile"},
    },
    "github": {
        "label": "GitHub", "client_id": os.getenv("GITHUB_CLIENT_ID"),
        "client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
        "authorize_url": "https://github.com/login/oauth/authorize",
        "access_token_url": "https://github.com/login/oauth/access_token",
        "api_base_url": "https://api.github.com/", "client_kwargs": {"scope": "read:user user:email"},
    },
}

for name, values in PROVIDERS.items():
    if values["client_id"] and values["client_secret"]:
        oauth.register(name=name, **{key: value for key, value in values.items() if key != "label"})

def public_registry():
    return [{"id": name, "label": values["label"], "configured": bool(values["client_id"] and values["client_secret"])} for name, values in PROVIDERS.items()]

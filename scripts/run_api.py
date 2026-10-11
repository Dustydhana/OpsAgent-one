"""Start the production API with explicit diagnostics for hosting platforms."""

import os
import sys
import traceback
from pathlib import Path


# When executed as ``python scripts/run_api.py``, Python otherwise places only
# the scripts directory on sys.path. Add the repository root so ``backend`` and
# the existing top-level application modules resolve inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting OpsAgent API on 0.0.0.0:{port}", flush=True)
    try:
        import uvicorn

        print("Uvicorn loaded; importing application", flush=True)
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=port,
            proxy_headers=True,
            forwarded_allow_ips="*",
            workers=1,
            log_level="info",
        )
    except BaseException:
        print("OpsAgent API startup failed:", file=sys.stderr, flush=True)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()

from __future__ import annotations

from app.vault_runtime.composition import build_local_app
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.local_api.server import serve


def main() -> None:
    config = VaultLocalApiConfig.from_env()
    serve(config, build_local_app(config))


if __name__ == "__main__":
    main()

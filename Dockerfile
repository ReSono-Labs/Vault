FROM node:22-bookworm-slim AS web-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS python-build
WORKDIR /build
RUN python -m pip install --no-cache-dir uv==0.8.14
COPY pyproject.toml uv.lock README.md LICENSE.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app/ app/
COPY plugin-kit/ /build/plugin-kit/
COPY docs/VAULT-PLUGIN-KIT.md /build/plugin-kit/GUIDE.md
RUN cp app/vault_runtime/extensions/standards/plugin.schema.json /build/plugin-kit/schemas/plugin.schema.json \
    && mkdir -p /build/plugin-downloads \
    && python -c "import hashlib,pathlib,shutil; out=pathlib.Path('/build/plugin-downloads'); shutil.make_archive(str(out/'resono-labs-vault-plugin-kit-0.1.0'),'zip',root_dir='/build',base_dir='plugin-kit'); [shutil.make_archive(str(out/f'resono-labs-vault-plugin-{lang}-starter-0.1.0'),'zip',root_dir='/build/plugin-kit/starters',base_dir=lang) for lang in ('python','typescript')]; files=sorted(out.glob('*.zip')); (out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\\n' for p in files))"
RUN uv sync --frozen --no-dev
COPY integrations/hermes-vault-memory/README.md integrations/hermes-vault-memory/pyproject.toml /build/adapter-packages/hermes-vault-memory/
COPY integrations/hermes-vault-memory/src/resono_vault_hermes/__init__.py integrations/hermes-vault-memory/src/resono_vault_hermes/pairing.py integrations/hermes-vault-memory/src/resono_vault_hermes/plugin.yaml /build/adapter-packages/hermes-vault-memory/src/resono_vault_hermes/
COPY integrations/openclaw-vault-memory/README.md integrations/openclaw-vault-memory/package.json integrations/openclaw-vault-memory/openclaw.plugin.json integrations/openclaw-vault-memory/index.js integrations/openclaw-vault-memory/pair.mjs /build/adapter-packages/openclaw-vault-memory/
COPY LICENSE.md /build/adapter-packages/hermes-vault-memory/LICENSE.md
COPY LICENSE.md /build/adapter-packages/openclaw-vault-memory/LICENSE.md
RUN mkdir -p /build/adapter-downloads \
    && python -c "import shutil; [shutil.make_archive('/build/adapter-downloads/resono-vault-' + name + '-memory-0.1.0', kind, root_dir='/build/adapter-packages', base_dir=name + '-vault-memory') for name in ('hermes', 'openclaw') for kind in ('zip', 'gztar')]"

FROM python:3.12-slim-bookworm AS runtime
ARG VAULT_UID=10001
ARG VAULT_GID=10001
RUN apt-get update \
    && apt-get install --no-install-recommends -y bubblewrap ca-certificates libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${VAULT_GID}" vault \
    && useradd --uid "${VAULT_UID}" --gid vault --home-dir /var/lib/resono-vault --create-home vault
WORKDIR /opt/resono-vault
COPY --from=python-build /build/.venv /opt/resono-vault/.venv
COPY --from=python-build /build/app /opt/resono-vault/app
COPY --from=web-build /build/frontend/dist /opt/resono-vault/web
COPY docs/PLATFORM-GUIDE.md /opt/resono-vault/web/platform-guide.md
COPY docs/WINDOWS-INSTALLATION.md /opt/resono-vault/web/windows-installation.md
COPY docs/VAULT-PLUGIN-KIT.md /opt/resono-vault/web/vault-plugin-kit.md
COPY docs/VAULT-MCP-PACKAGE-KIT.md /opt/resono-vault/web/vault-mcp-package-kit.md
COPY docs/RESONO-LABS-LINK.md /opt/resono-vault/web/resono-labs-link.md
COPY docs/LOCAL-CONNECTION-BRIDGE.md /opt/resono-vault/web/local-connection-bridge.md
COPY docs/HERMES-OPENCLAW-MEMORY.md /opt/resono-vault/web/hermes-openclaw-memory.md
COPY --from=python-build /build/adapter-downloads/ /opt/resono-vault/web/downloads/
COPY --from=python-build /build/plugin-downloads/ /opt/resono-vault/web/downloads/
COPY app /opt/resono-vault/help-source/codebase/app
COPY frontend/src /opt/resono-vault/help-source/codebase/frontend/src
COPY scripts /opt/resono-vault/help-source/codebase/scripts
COPY tests /opt/resono-vault/help-source/codebase/tests
COPY integrations /opt/resono-vault/help-source/codebase/integrations
COPY docs /opt/resono-vault/help-source/codebase/docs
COPY Dockerfile compose.yml pyproject.toml README.md LICENSE.md SECURITY.md CONTRIBUTING.md CHANGELOG.md CODE_OF_CONDUCT.md /opt/resono-vault/help-source/codebase/
COPY docs/PLATFORM-GUIDE.md /opt/resono-vault/help-source/platform-documents/platform-guide.md
COPY docs/WINDOWS-INSTALLATION.md /opt/resono-vault/help-source/platform-documents/windows-installation.md
COPY docs/VAULT-PLUGIN-KIT.md /opt/resono-vault/help-source/platform-documents/vault-plugin-kit.md
COPY docs/VAULT-MCP-PACKAGE-KIT.md /opt/resono-vault/help-source/platform-documents/vault-mcp-package-kit.md
COPY docs/RESONO-LABS-LINK.md /opt/resono-vault/help-source/platform-documents/resono-labs-link.md
COPY docs/LOCAL-CONNECTION-BRIDGE.md /opt/resono-vault/help-source/platform-documents/local-connection-bridge.md
COPY docs/HERMES-OPENCLAW-MEMORY.md /opt/resono-vault/help-source/platform-documents/hermes-openclaw-memory.md
RUN chmod -R a-w /opt/resono-vault/help-source
ENV PATH="/opt/resono-vault/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RESONO_VAULT_DATA_ROOT=/var/lib/resono-vault \
    RESONO_VAULT_WEB_ROOT=/opt/resono-vault/web
USER vault:vault
EXPOSE 8765
ENTRYPOINT ["python", "-m", "app.vault_runtime.package_runtime"]
CMD ["serve"]

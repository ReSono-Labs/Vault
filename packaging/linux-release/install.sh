#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' 'Run this installer with sudo.' >&2
  exit 1
fi

package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for program in systemctl runuser psql bwrap; do
  command -v "$program" >/dev/null 2>&1 || {
    printf 'Missing requirement: %s\n' "$program" >&2
    exit 1
  }
done
getent passwd postgres >/dev/null 2>&1 || {
  printf '%s\n' 'PostgreSQL is installed, but its postgres service account is unavailable.' >&2
  exit 1
}
if ! runuser -u postgres -- psql -tAc \
  "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1; then
  printf '%s\n' 'Install the pgvector extension for PostgreSQL before installing Vault.' >&2
  exit 1
fi

getent passwd resono-vault >/dev/null 2>&1 || useradd \
  --system --home-dir /var/lib/resono-vault --create-home --shell /usr/sbin/nologin resono-vault
install -d -o resono-vault -g resono-vault -m 0700 /var/lib/resono-vault
rm -rf /opt/resono-vault.new
install -d -m 0755 /opt/resono-vault.new
cp -a "$package_dir/vault/." /opt/resono-vault.new/
chown -R root:root /opt/resono-vault.new

if [ -d /opt/resono-vault ]; then
  rm -rf /opt/resono-vault.previous
  mv /opt/resono-vault /opt/resono-vault.previous
fi
mv /opt/resono-vault.new /opt/resono-vault

runuser -u resono-vault -- env \
  RESONO_VAULT_DATA_ROOT=/var/lib/resono-vault \
  RESONO_VAULT_PACKAGE_DATABASE_HOST=127.0.0.1 \
  RESONO_VAULT_PACKAGE_DATABASE_NAME=vault \
  RESONO_VAULT_PACKAGE_DATABASE_USER=vault_runtime \
  RESONO_VAULT_TLS_HOSTS=localhost,127.0.0.1 \
  /opt/resono-vault/runtime/bin/python3 -m app.vault_runtime.package_runtime initialize

password=$(cat /var/lib/resono-vault/postgres-password)
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='vault_runtime'" | grep -q 1; then
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "CREATE ROLE vault_runtime LOGIN PASSWORD '$password'"
else
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "ALTER ROLE vault_runtime PASSWORD '$password'"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='vault'" | grep -q 1; then
  runuser -u postgres -- createdb --owner=vault_runtime vault
fi
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d vault -c 'CREATE EXTENSION IF NOT EXISTS vector'

install -m 0755 "$package_dir/resono-vault" /usr/local/bin/resono-vault
install -m 0644 "$package_dir/resono-vault.service" /etc/systemd/system/resono-vault.service
systemctl daemon-reload
systemctl enable --now resono-vault.service
systemctl is-active --quiet resono-vault.service
printf '%s\n' 'Vault is ready at https://127.0.0.1:8765'
printf '%s\n' 'Run: resono-vault setup'

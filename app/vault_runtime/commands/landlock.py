"""Linux Landlock: limit a process (and everything it starts) to listed folders.

Unprivileged and stackable, so it works inside the Vault container as the runtime user
(no-new-privileges is already set, which Landlock requires). Only allow rules exist: any
path not listed is refused, including the rest of the computer's folders and Vault's data.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path

_SYS_CREATE_RULESET, _SYS_ADD_RULE, _SYS_RESTRICT_SELF = 444, 445, 446
_CREATE_RULESET_VERSION = 1
_RULE_PATH_BENEATH = 1

EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
REMOVE_DIR = 1 << 4
REMOVE_FILE = 1 << 5
MAKE_CHAR = 1 << 6
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
MAKE_SOCK = 1 << 9
MAKE_FIFO = 1 << 10
MAKE_BLOCK = 1 << 11
MAKE_SYM = 1 << 12
REFER = 1 << 13  # ABI 2
TRUNCATE = 1 << 14  # ABI 3
IOCTL_DEV = 1 << 15  # ABI 5

READ = EXECUTE | READ_FILE | READ_DIR
_WRITE_V1 = (WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_CHAR | MAKE_DIR | MAKE_REG
             | MAKE_SOCK | MAKE_FIFO | MAKE_BLOCK | MAKE_SYM)


class LandlockError(RuntimeError):
    pass


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _RulesetAttrV6(ctypes.Structure):
    # handled_access_net stays 0: network is allowed (owner decision). scoped blocks signals and
    # abstract unix sockets to processes outside the sandbox, so a command can't stop Vault itself.
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("handled_access_net", ctypes.c_uint64),
                ("scoped", ctypes.c_uint64)]


_SCOPE_ABSTRACT_UNIX_SOCKET = 1 << 0
_SCOPE_SIGNAL = 1 << 1
_RULE_NET_PORT = 2
NET_BIND_TCP = 1 << 0     # ABI 4
NET_CONNECT_TCP = 1 << 1  # ABI 4


class _RulesetAttrV4(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("handled_access_net", ctypes.c_uint64)]


class _NetPortAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("port", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def _libc():
    return ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)


def abi_version() -> int:
    """0 when Landlock isn't available (not Linux, disabled in the kernel, or blocked)."""
    if not hasattr(os, "uname") or os.uname().sysname != "Linux":
        return 0
    try:
        version = _libc().syscall(_SYS_CREATE_RULESET, None, ctypes.c_size_t(0), ctypes.c_uint32(_CREATE_RULESET_VERSION))
    except (OSError, AttributeError):
        return 0
    return max(0, int(version))


def _write_access(abi: int) -> int:
    access = _WRITE_V1
    if abi >= 2:
        access |= REFER
    if abi >= 3:
        access |= TRUNCATE
    if abi >= 5:
        access |= IOCTL_DEV
    return access


def access_for(kind: str, abi: int) -> int:
    """'read' (programs, files), 'write' (read + change), 'list' (see names only, open nothing)."""
    if kind == "list":
        return READ_DIR
    if kind == "read":
        return READ
    if kind == "write":
        return READ | _write_access(abi)
    raise LandlockError(f"Unknown access kind {kind!r}.")


_DIRECTORY_ONLY = READ_DIR | REMOVE_DIR | MAKE_DIR | MAKE_REG | MAKE_SYM | MAKE_SOCK | MAKE_FIFO | MAKE_CHAR \
    | MAKE_BLOCK | REMOVE_FILE | REFER


def restrict_self(rules: list[tuple[str, str]], *, network: tuple[list[int], list[int]] | None = None) -> bool:
    """Apply to the calling process (irreversible; call right before exec).

    Each rule is (path, kind). A rule covers the path and everything beneath it; paths not
    covered by any rule are refused. ``network`` is (TCP ports it may bind, TCP ports it may
    connect to); every other TCP bind or connect is refused. Network rules need ABI 4: on an
    older kernel they are skipped and this returns False.
    """
    abi = abi_version()
    if abi < 1:
        raise LandlockError("Landlock is not available.")
    libc = _libc()
    handled = READ | _write_access(abi)
    net = network is not None and abi >= 4
    handled_net = NET_BIND_TCP | NET_CONNECT_TCP if net else 0
    scope = _SCOPE_ABSTRACT_UNIX_SOCKET | _SCOPE_SIGNAL
    attr = (_RulesetAttrV6(handled, handled_net, scope) if abi >= 6
            else _RulesetAttrV4(handled, handled_net) if net else _RulesetAttr(handled))
    ruleset = libc.syscall(_SYS_CREATE_RULESET, ctypes.byref(attr), ctypes.c_size_t(ctypes.sizeof(attr)), ctypes.c_uint32(0))
    if ruleset < 0:
        raise LandlockError(f"Landlock ruleset failed ({ctypes.get_errno()}).")
    try:
        for path, kind in rules:
            if os.path.islink(path):
                continue  # Never follow a symlink into a rule.
            try:
                fd = os.open(path, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
            except OSError:
                continue
            try:
                access = access_for(kind, abi)
                if not os.path.isdir(path):
                    access &= ~_DIRECTORY_ONLY
                if not access:
                    continue
                rule = _PathBeneathAttr(access, fd)
                if libc.syscall(_SYS_ADD_RULE, ruleset, ctypes.c_int(_RULE_PATH_BENEATH), ctypes.byref(rule),
                                ctypes.c_uint32(0)) < 0:
                    raise LandlockError(f"Landlock rule for {path} failed ({ctypes.get_errno()}).")
            finally:
                os.close(fd)
        if net:
            bind, connect = network  # type: ignore[misc]
            for port in sorted(set(bind) | set(connect)):
                access = (NET_BIND_TCP if port in bind else 0) | (NET_CONNECT_TCP if port in connect else 0)
                rule_net = _NetPortAttr(access, port)
                if libc.syscall(_SYS_ADD_RULE, ruleset, ctypes.c_int(_RULE_NET_PORT), ctypes.byref(rule_net),
                                ctypes.c_uint32(0)) < 0:
                    raise LandlockError(f"Landlock network rule for port {port} failed ({ctypes.get_errno()}).")
        if libc.prctl(38, 1, 0, 0, 0) < 0:  # PR_SET_NO_NEW_PRIVS
            raise LandlockError("no_new_privs failed.")
        if libc.syscall(_SYS_RESTRICT_SELF, ruleset, ctypes.c_uint32(0)) < 0:
            raise LandlockError(f"Landlock restrict failed ({ctypes.get_errno()}).")
    finally:
        os.close(ruleset)
    return net

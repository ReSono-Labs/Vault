"""Vault's shared request errors (only the ones in use)."""

from app.core.exceptions.base import AppError, BadRequestError

__all__ = ["AppError", "BadRequestError"]

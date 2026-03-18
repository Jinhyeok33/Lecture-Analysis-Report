"""Backward-compatible wrapper for integration module."""

from src.integration.result_integrator import integrate, load_metadata, merge_analyses

__all__ = ["integrate", "load_metadata", "merge_analyses"]

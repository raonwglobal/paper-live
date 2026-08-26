"""Secure GitHub-sourced plugin lifecycle primitives."""

from .manifest import PluginManifest, PermissionPolicy, load_manifest
from .registry import PluginRegistry

__all__ = ["PluginManifest", "PermissionPolicy", "PluginRegistry", "load_manifest"]

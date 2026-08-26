"""Secure GitHub-sourced plugin lifecycle and runtime primitives."""

from .manifest import PluginManifest, PermissionPolicy, load_manifest
from .registry import PluginRegistry
from .integration import PluginExecutionRequest, PluginRuntime

__all__ = [
    "PluginManifest",
    "PermissionPolicy",
    "PluginRegistry",
    "PluginExecutionRequest",
    "PluginRuntime",
    "load_manifest",
]

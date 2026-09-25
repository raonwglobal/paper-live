"""Secure GitHub-sourced plugin lifecycle and runtime primitives."""

from .integration import PluginExecutionRequest, PluginRuntime
from .manifest import PermissionPolicy, PluginManifest, load_manifest
from .registry import PluginRegistry

__all__ = [
    "PluginManifest",
    "PermissionPolicy",
    "PluginRegistry",
    "PluginExecutionRequest",
    "PluginRuntime",
    "load_manifest",
]

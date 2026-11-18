"""Loaded by Python at start-up in the core container (mounted into site-packages).

Patches modules of the unmodified OpenShorts core right after they are first
imported, so our changes live in overrides/ instead of a fork:
  - screencast_layout.detect_content_ranges -> openrouter_vision (shot check
    through OpenRouter instead of a direct Gemini key).
"""
import importlib.abc
import importlib.machinery
import sys

PATCHES = {
    "screencast_layout": lambda module: setattr(
        module, "detect_content_ranges", __import__("openrouter_vision").detect_content_ranges),
    "camera_inset": lambda module: setattr(
        module, "present_in_scene", __import__("openrouter_vision").present_in_scene(module.present_in_scene)),
}


class _PatchingLoader(importlib.abc.Loader):
    def __init__(self, inner, patch):
        self.inner, self.patch = inner, patch

    def create_module(self, spec):
        return self.inner.create_module(spec)

    def exec_module(self, module):
        self.inner.exec_module(module)
        try:
            self.patch(module)
        except Exception as exc:  # a failed patch must never break the core
            print(f"sitecustomize: patching {module.__name__} failed: {exc}")


class _PatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name not in PATCHES:
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            spec = getattr(finder, "find_spec", lambda *a: None)(name, path, target)
            if spec and spec.loader:
                spec.loader = _PatchingLoader(spec.loader, PATCHES[name])
                return spec
        return None


sys.meta_path.insert(0, _PatchFinder())

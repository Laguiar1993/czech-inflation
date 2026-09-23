"""Read-only, module-local relocation of sealed R33/R34/R35 archive reads."""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import importlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import threading

ORIGINAL_ROOT = (
    "C:/Users/luis_/Documents/Codex/2026-09-05/"
    "c-users-luis-appdata-local-temp/work/cpi-independent"
)
_MODULES = (
    "tools.forecast_updates_r33.workflow",
    "tools.current_path_r34.inputs",
    "tools.momentum_r35.inputs",
)
_LOCK = threading.Lock()


def _parse(value):
    """Validate lexical paths before resolve() can erase traversal components."""
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or "\0" in raw:
        raise ValueError("relocation requires a nonempty text path")
    if raw.replace("\\", "/").startswith(("//?/", "//./")):
        raise ValueError("unsafe Windows device path")
    win = PureWindowsPath(raw)
    path = (win if os.name == "nt" or win.drive or raw.startswith("\\")
            else PurePosixPath(raw.replace("\\", "/")))
    if (path.drive or path.root) and not path.is_absolute():
        raise ValueError("unsafe drive-relative or root-relative path")
    parts = path.parts[1:] if path.anchor else path.parts
    for part in parts:
        if (part == ".." or part.endswith((".", " "))
                or any(c in part for c in ':*?"<>|')
                or PureWindowsPath(part).is_reserved()):
            raise ValueError(f"unsafe relocation path component: {part!r}")
    return path


class _Relocation:
    def __init__(self, root, old_root):
        _parse(root)
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("relocation root must be an existing checkout directory")
        self.current = _parse(self.root)
        self.old = _parse(old_root)
        if not self.old.is_absolute() or len(self.old.parts) < 2:
            raise ValueError("old_root must be an absolute repository path")
        if self.old != self.current and (self.old.is_relative_to(self.current)
                                         or self.current.is_relative_to(self.old)):
            raise ValueError("old and current roots must not overlap")
        self._mappings = {}

    @property
    def mappings(self):
        """Observed old-to-current mappings; no log files are written."""
        return tuple(self._mappings.items())

    def _relative(self, value):
        path = _parse(value)
        if not path.is_absolute():
            return path.parts, False
        if path.is_relative_to(self.old):
            return path.relative_to(self.old).parts, True
        if path.is_relative_to(self.current):
            return path.relative_to(self.current).parts, False
        raise ValueError(f"path outside relocation roots: {value}")

    def resolve(self, value):
        """Resolve under the current root only; never probe or fall back to old_root."""
        parts, archived = self._relative(value)
        candidate = self.root.joinpath(*parts).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError(f"unsafe relocation path escapes checkout: {value}")
        if archived:
            self._mappings[os.fspath(value)] = str(candidate)
        return candidate

    def identity(self, value):
        _, archived = self._relative(value)
        actual = self.resolve(value)
        return os.fspath(value) if archived else str(actual)

    def archived_identity(self, value):
        actual = self.resolve(value)
        return str(self.old.joinpath(*actual.relative_to(self.root).parts))

    def path(self, value=".", *parts):
        result = _ReadPath(self, self.resolve(value))
        for part in parts:
            result = result / part
        return result


class _ReadPath:
    """Only the pathlib surface used by the sealed read/verification functions.

    The shared R32 checked_files converts this via __fspath__, then performs its
    own unchanged manifest-member traversal, symlink and SHA-256 checks.
    """
    def __init__(self, relocation, path):
        self._relocation = relocation
        self._path = path

    def _checked(self):
        return self._relocation.resolve(self._path)

    def __fspath__(self):
        return str(self._checked())

    def __str__(self):
        return os.fspath(self)

    def __truediv__(self, other):
        child = _parse(other)
        if child.is_absolute():
            raise ValueError("unsafe absolute child path")
        return self._relocation.path(self._path.joinpath(*child.parts))

    def __eq__(self, other):
        if not isinstance(other, (_ReadPath, Path)):
            return NotImplemented
        return self._checked() == Path(other)

    @property
    def name(self):
        return self._path.name

    @property
    def parent(self):
        return self._relocation.path(self._path.parent)

    def resolve(self, strict=False):
        path = self._checked().resolve(strict=strict)
        return self._relocation.path(path)

    def is_relative_to(self, other):
        return self._checked().is_relative_to(Path(other))

    def exists(self):
        return self._checked().exists()

    def is_file(self):
        return self._checked().is_file()

    def is_dir(self):
        return self._checked().is_dir()

    def read_bytes(self):
        return self._checked().read_bytes()

    def read_text(self, encoding=None, errors=None):
        return self._checked().read_text(encoding=encoding, errors=errors)

    def open(self, mode="r", *args, **kwargs):
        if mode not in ("r", "rb", "rt"):
            raise PermissionError("relocation paths are read-only")
        return self._checked().open(mode, *args, **kwargs)


def _manifest_wrapper(original, relocation):
    @wraps(original)
    def manifest(path, *args, **kwargs):
        identity = relocation.identity(path)
        # The original helper still reads and hashes every manifest-listed byte.
        result = original(path, *args, **kwargs)
        info = dict(result[-1], path=identity)
        return (*result[:-1], info)
    return manifest


def _frozen_wrapper(original, relocation):
    @wraps(original)
    def frozen(package):
        _, archived = relocation._relative(package)
        result = original(package)  # Includes the unchanged extractor source hash check.
        if not archived:
            return result
        info = dict(result[-1])
        info["extractor_path"] = relocation.archived_identity(info["extractor_path"])
        return (*result[:-1], info)
    return frozen


@contextmanager
def relocations(root, old_root=ORIGINAL_ROOT):
    """Temporarily relocate sealed archive reads without rewriting any bytes.

    Use only with R33 workflow.load_run, R34 inputs.load_prepared and R35
    inputs.load_prepared (and their read helpers). Relative paths are relative
    to root, independent of cwd. Absolute paths must be descendants of root or
    old_root. Old metadata identities survive; actual reads stay under root.

    The three modules' Path bindings and manifest/frozen helpers are restored
    even after errors. This is a single-threaded verification context: nesting
    and overlapping contexts fail, and callers must not use the affected
    modules concurrently. No global filesystem functions or __file__ values
    are patched. Imports require the normal repository runtime; use python -B
    to prevent Python from writing import bytecode.
    """
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("relocation contexts cannot nest or overlap")
    saved = []
    try:
        relocation = _Relocation(root, old_root)
        # Import all modules before installing any overrides: import errors
        # must not leave a partially patched verification environment.
        modules = [importlib.import_module(name) for name in _MODULES]
        changes = [(module, "Path", relocation.path) for module in modules]
        changes.extend((module, "_manifest", _manifest_wrapper(module._manifest, relocation))
                       for module in modules[1:])
        changes.append((modules[2], "_frozen", _frozen_wrapper(modules[2]._frozen, relocation)))
        for module, name, value in changes:
            saved.append((module, name, getattr(module, name)))
            setattr(module, name, value)
        yield relocation
    finally:
        for module, name, value in reversed(saved):
            setattr(module, name, value)
        _LOCK.release()

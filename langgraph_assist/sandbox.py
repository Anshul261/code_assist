from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE = PROJECT_ROOT / "lg_workspace"


def slugify(value: str, fallback: str = "artifact") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug or fallback


@dataclass(frozen=True)
class Sandbox:
    root: Path = DEFAULT_WORKSPACE

    @property
    def uploads_dir(self) -> Path:
        return self.root / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def scratch_dir(self) -> Path:
        return self.root / "scratch"

    @property
    def db_path(self) -> Path:
        return self.root / "state" / "langgraph.sqlite"

    @property
    def memory_path(self) -> Path:
        return self.root / "state" / "memory.sqlite"

    def ensure(self) -> None:
        for path in [
            self.uploads_dir,
            self.outputs_dir,
            self.scratch_dir,
            self.db_path.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _resolve_under(self, base: Path, raw_path: str) -> Path:
        if not raw_path:
            raise ValueError("path is required")
        path = Path(raw_path)
        resolved = (path if path.is_absolute() else base / path).resolve()
        try:
            resolved.relative_to(base.resolve())
        except ValueError as exc:
            raise ValueError(f"path is outside sandbox: {raw_path}") from exc
        return resolved

    def resolve_read(self, raw_path: str) -> Path:
        self.ensure()
        path = Path(raw_path)
        if path.is_absolute():
            resolved = path.resolve()
            allowed = [self.uploads_dir.resolve(), self.outputs_dir.resolve(), self.scratch_dir.resolve()]
            if any(_is_relative_to(resolved, base) for base in allowed):
                return resolved
            raise ValueError(f"path is outside readable sandbox: {raw_path}")

        for base in [self.uploads_dir, self.outputs_dir, self.scratch_dir]:
            candidate = (base / raw_path).resolve()
            if candidate.exists():
                return candidate
        return self._resolve_under(self.uploads_dir, raw_path)

    def resolve_output(self, raw_path: str) -> Path:
        self.ensure()
        resolved = self._resolve_under(self.outputs_dir, raw_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def resolve_scratch(self, raw_path: str) -> Path:
        self.ensure()
        resolved = self._resolve_under(self.scratch_dir, raw_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def save_upload(self, filename: str, data: bytes) -> Path:
        self.ensure()
        safe_name = slugify(filename, "upload.bin")
        target = self.uploads_dir / safe_name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            index = 2
            while target.exists():
                target = self.uploads_dir / f"{stem}-{index}{suffix}"
                index += 1
        target.write_bytes(data)
        return target

    def list_outputs(self) -> list[dict[str, str | int]]:
        self.ensure()
        results: list[dict[str, str | int]] = []
        for path in sorted(self.outputs_dir.rglob("*")):
            if path.is_file():
                stat = path.stat()
                results.append(
                    {
                        "path": str(path.relative_to(self.outputs_dir)),
                        "absolute_path": str(path),
                        "download_url": f"/download/{path.relative_to(self.outputs_dir).as_posix()}",
                        "size": stat.st_size,
                    }
                )
        return results

    def copy_into_outputs(self, source: Path, output_name: str | None = None) -> Path:
        self.ensure()
        name = slugify(output_name or source.name)
        target = self.resolve_output(name)
        shutil.copy2(source, target)
        return target


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def sandbox_from_env() -> Sandbox:
    root = Path(os.getenv("LANGGRAPH_SANDBOX_DIR", str(DEFAULT_WORKSPACE))).resolve()
    sandbox = Sandbox(root=root)
    sandbox.ensure()
    return sandbox

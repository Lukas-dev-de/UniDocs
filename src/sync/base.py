"""Provider contract for cloud backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from sync.types import RemoteEntry


class SyncProviderError(Exception):
    """Base error for provider failures."""


class SyncAuthError(SyncProviderError):
    """Credentials missing, rejected or expired."""


class SyncNetworkError(SyncProviderError):
    """Transient network/server failure."""


class SyncNotFoundError(SyncProviderError):
    """Remote path or folder does not exist."""


class SyncConflictError(SyncProviderError):
    """A conditional write lost against a concurrent change."""


class BaseSyncProvider(ABC):
    """Uniform file interface used by the engine.

    All paths are POSIX relative paths below the provider's UniDocs root.
    """

    hash_kind: str | None = None  # "sha256" | "md5"
    supports_move: bool = False
    supports_dirs: bool = True

    @abstractmethod
    def test_connection(self) -> None:
        """Raise a SyncProviderError subclass if the backend is unreachable."""

    @abstractmethod
    def root_exists(self) -> bool:
        ...

    @abstractmethod
    def ensure_root(self) -> None:
        ...

    @abstractmethod
    def list_remote(self) -> dict[str, RemoteEntry]:
        """All files and directories, keyed by POSIX relative path."""

    @abstractmethod
    def read_text(self, rel: str, max_bytes: int = 65536) -> str:
        ...

    @abstractmethod
    def download_file(self, rel: str, local_path: Path) -> None:
        ...

    @abstractmethod
    def upload_file(
        self,
        local_path: Path,
        rel: str,
        expected_etag: str | None = None,
    ) -> RemoteEntry:
        ...

    @abstractmethod
    def create_dir(self, rel: str) -> RemoteEntry:
        ...

    @abstractmethod
    def move(self, src_rel: str, dst_rel: str, is_dir: bool) -> None:
        ...

    @abstractmethod
    def delete(self, rel: str, is_dir: bool, recursive: bool = False) -> None:
        ...

    def close(self) -> None:
        return None

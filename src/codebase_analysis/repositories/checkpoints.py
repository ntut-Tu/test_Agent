"""Manage SQLite checkpoint connections on the service's persistent volume."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


@contextmanager
def open_checkpoints(path: Path) -> Iterator[SqliteSaver]:
    """Open a saver for one execution; flush and close it before returning.

    The service's existing worker lock permits one executing worker per volume.
    Checkpoint state includes source evidence and belongs on trusted storage.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver

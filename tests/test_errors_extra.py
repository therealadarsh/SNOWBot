"""Cover remaining error subclasses."""

from snowbot.errors import FileOperationError


def test_file_operation_error() -> None:
    err = FileOperationError("disk full", details={"path": "/tmp/x"})
    assert err.code == "file_error"
    assert str(err) == "disk full"

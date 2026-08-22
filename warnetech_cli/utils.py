"""
Utility Functions Module
Provides helper functions for file IO, JSON, NDJSON, Parquet, and subprocess operations.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List


class FileUtils:
    """File input/output utilities."""

    @staticmethod
    def read_json(path: Path) -> Dict[str, Any]:
        """Read JSON file."""
        with open(path, "r") as f:
            return json.load(f)

    @staticmethod
    def write_json(path: Path, data: Dict[str, Any], indent: int = 2) -> None:
        """Write JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=indent, default=str)

    @staticmethod
    def read_ndjson(path: Path) -> List[Dict[str, Any]]:
        """Read NDJSON file."""
        records = []
        with open(path, "r") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        return records

    @staticmethod
    def write_ndjson(path: Path, records: List[Dict[str, Any]]) -> None:
        """Write NDJSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

    @staticmethod
    def read_bytes(path: Path) -> bytes:
        """Read binary file."""
        with open(path, "rb") as f:
            return f.read()

    @staticmethod
    def write_bytes(path: Path, data: bytes) -> None:
        """Write binary file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    @staticmethod
    def file_size(path: Path) -> int:
        """Get file size in bytes."""
        return path.stat().st_size if path.exists() else 0


class ParquetUtils:
    """Parquet file utilities."""

    @staticmethod
    def records_to_parquet(records: List[Dict[str, Any]], path: Path) -> None:
        """Convert records to Parquet format."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            raise RuntimeError("pyarrow library is required for Parquet support")

        table = pa.Table.from_pylist(records)
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, str(path))

    @staticmethod
    def parquet_to_records(path: Path) -> List[Dict[str, Any]]:
        """Convert Parquet file to records."""
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise RuntimeError("pyarrow library is required for Parquet support")

        table = pq.read_table(str(path))
        return table.to_pylist()


class SubprocessUtils:
    """Subprocess execution utilities."""

    @staticmethod
    def run_command(
        command: List[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run shell command.

        Args:
            command: Command list
            check: Raise exception if command fails
            capture_output: Capture stdout/stderr

        Returns:
            CompletedProcess result
        """
        return subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=True,
        )

    @staticmethod
    def get_command_output(command: List[str]) -> str:
        """Run command and return stdout."""
        result = SubprocessUtils.run_command(command)
        return result.stdout.strip()


class DataUtils:
    """Data manipulation utilities."""

    @staticmethod
    def calculate_checksum(data: bytes) -> str:
        """Calculate SHA-256 checksum."""
        import hashlib

        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def validate_checksum(data: bytes, checksum: str) -> bool:
        """Validate data against checksum."""
        return DataUtils.calculate_checksum(data) == checksum

    @staticmethod
    def format_size(size: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

    @staticmethod
    def format_time(milliseconds: float) -> str:
        """Format milliseconds to human-readable time."""
        if milliseconds < 1000:
            return f"{milliseconds:.1f}ms"
        elif milliseconds < 60000:
            return f"{milliseconds / 1000:.1f}s"
        else:
            return f"{milliseconds / 60000:.1f}m"

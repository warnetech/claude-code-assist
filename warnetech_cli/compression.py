"""
Compression Module
Implements LZ4, ZSTD-fast, ZSTD-medium, and ZSTD-max compression.
"""

from typing import Literal

try:
    import lz4.frame
    LZ4_AVAILABLE = True
except ImportError:
    LZ4_AVAILABLE = False

try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


CompressionType = Literal["lz4", "zstd-fast", "zstd-medium", "zstd-max"]


class CompressionManager:
    """Manages data compression and decompression."""

    COMPRESSION_LEVELS = {
        "lz4": 0,  # LZ4 doesn't use levels
        "zstd-fast": 1,
        "zstd-medium": 10,
        "zstd-max": 22,
    }

    @staticmethod
    def compress(data: bytes, method: CompressionType = "zstd-medium") -> bytes:
        """
        Compress data using specified method.

        Args:
            data: Data to compress
            method: Compression method (lz4, zstd-fast, zstd-medium, zstd-max)

        Returns:
            Compressed data
        """
        if method == "lz4":
            if not LZ4_AVAILABLE:
                raise RuntimeError("lz4 library is required")
            return lz4.frame.compress(data)

        elif method.startswith("zstd"):
            if not ZSTD_AVAILABLE:
                raise RuntimeError("zstandard library is required")

            level = CompressionManager.COMPRESSION_LEVELS[method]
            cctx = zstd.ZstdCompressor(level=level)
            return cctx.compress(data)

        else:
            raise ValueError(f"Unknown compression method: {method}")

    @staticmethod
    def decompress(compressed: bytes, method: CompressionType = "zstd-medium") -> bytes:
        """
        Decompress data using specified method.

        Args:
            compressed: Compressed data
            method: Compression method

        Returns:
            Decompressed data
        """
        if method == "lz4":
            if not LZ4_AVAILABLE:
                raise RuntimeError("lz4 library is required")
            return lz4.frame.decompress(compressed)

        elif method.startswith("zstd"):
            if not ZSTD_AVAILABLE:
                raise RuntimeError("zstandard library is required")

            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(compressed)

        else:
            raise ValueError(f"Unknown compression method: {method}")

    @staticmethod
    def get_compression_ratio(original_size: int, compressed_size: int) -> float:
        """
        Calculate compression ratio.

        Args:
            original_size: Original data size
            compressed_size: Compressed data size

        Returns:
            Compression ratio (original / compressed)
        """
        if compressed_size == 0:
            return 0.0
        return original_size / compressed_size

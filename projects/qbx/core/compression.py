# Compression module for QBX
# Supports LZ4 for fast compression

import lz4.frame
import hashlib
import struct

# Compression algorithms
COMPRESSION_NONE = 0
COMPRESSION_LZ4 = 1

# Thresholds  
HOT_SIZE_THRESHOLD = 32 * 1024  # 32KB - files smaller than this are "hot" (no LZ4)
COLD_SIZE_THRESHOLD = 5 * 1024 * 1024  # 5MB - files larger than this get LZ4

# Hot extensions (no compression)
HOT_EXTENSIONS = {'.dll', '.exe', '.sys', '.db', '.sqlite', '.bin', '.dat', '.iso', '.img'}


def should_compress(file_path: str, file_size: int) -> bool:
    """Determine if file should be compressed based on size and extension"""
    # Don't compress hot extensions
    import os
    ext = os.path.splitext(file_path)[1].lower()
    if ext in HOT_EXTENSIONS:
        return False
    
    # Compress files that are large enough (LZ4 needs some size to be effective)
    if file_size >= HOT_SIZE_THRESHOLD:
        return True
    
    return False


def compress_lz4(data: bytes) -> tuple:
    """
    Compress data using LZ4.
    Returns: (compressed_data, compression_algorithm)
    If compression doesn't help, returns original with NONE
    """
    if len(data) < 1024:
        # Too small to compress effectively
        return data, COMPRESSION_NONE
    
    try:
        compressed = lz4.frame.compress(data)
        if len(compressed) < len(data):
            return compressed, COMPRESSION_LZ4
        else:
            # Compression didn't help
            return data, COMPRESSION_NONE
    except Exception as e:
        # On error, return original
        return data, COMPRESSION_NONE


def decompress_lz4(data: bytes) -> bytes:
    """Decompress LZ4 data"""
    try:
        return lz4.frame.decompress(data)
    except Exception as e:
        raise ValueError(f"LZ4 decompression failed: {e}")


def compress_block(data: bytes, file_path: str = "") -> tuple:
    """
    Compress block data based on file characteristics.
    Returns: (compressed_data, compression_algorithm, original_size)
    """
    original_size = len(data)
    algorithm = COMPRESSION_NONE
    
    if should_compress(file_path, original_size):
        compressed, algorithm = compress_lz4(data)
        if algorithm == COMPRESSION_NONE:
            # Compression didn't help
            return data, COMPRESSION_NONE, original_size
        return compressed, algorithm, original_size
    
    return data, COMPRESSION_NONE, original_size


def decompress_block(data: bytes, algorithm: int) -> bytes:
    """Decompress block data based on algorithm"""
    if algorithm == COMPRESSION_NONE:
        return data
    elif algorithm == COMPRESSION_LZ4:
        return decompress_lz4(data)
    else:
        raise ValueError(f"Unknown compression algorithm: {algorithm}")

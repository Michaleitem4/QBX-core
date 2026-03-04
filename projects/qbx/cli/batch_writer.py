# Batch Writer - Transaction Batching for QBX
# Reduces fsync calls by batching writes

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from core import read_chunk, CHUNK_SIZE

# Global fsync counter (accumulates across all operations)
_global_fsync_count = 0


def get_fsync_count() -> int:
    """Get current fsync count (global)"""
    global _global_fsync_count
    return _global_fsync_count


def reset_fsync_count():
    """Reset global fsync counter"""
    global _global_fsync_count
    _global_fsync_count = 0


def _fsync():
    """Simulated fsync - in production would call os.fsync()"""
    global _global_fsync_count
    _global_fsync_count += 1


class BatchWriter:
    """
    Batch Writer for optimized writes.
    
    Modes:
    - durable: fsync after every operation (strict durability)
    - fast: batch multiple operations, single fsync at end
    
    Thresholds:
    - max_ops: flush after N operations
    - max_bytes: flush after N bytes written
    """
    
    def __init__(self, vault_path: str, durable: bool = False, 
                 max_ops: int = 50, max_bytes: int = 8*1024*1024):
        self.vault_path = vault_path
        self.durable = durable
        self.max_ops = max_ops
        self.max_bytes = max_bytes
        
        # Pending operations
        self.pending_data = []  # [(chunk_id, block_num, data), ...]
        self.pending_metadata = []  # [callback, ...]
        self.bytes_accumulated = 0
        self.ops_count = 0
        
        # Track if this writer has been flushed
        self._flushed = False
    
    def add_data(self, chunk_id: int, block_num: int, data: bytes):
        """Add a data write to the batch"""
        self.pending_data.append((chunk_id, block_num, data))
        self.bytes_accumulated += len(data)
        self.ops_count += 1
        
        # Flush if thresholds reached (unless durable mode)
        if not self.durable:
            if self.ops_count >= self.max_ops or self.bytes_accumulated >= self.max_bytes:
                self.flush()
    
    def add_metadata(self, callback):
        """Add a metadata update (will be called during flush)"""
        self.pending_metadata.append(callback)
    
    def flush(self):
        """Flush all pending writes to disk with minimal fsync"""
        global _global_fsync_count
        
        if not self.pending_data and not self.pending_metadata:
            return 0
        
        # Always write all data first (regardless of mode)
        for chunk_id, block_num, data in self.pending_data:
            self._write_data(chunk_id, block_num, data)
        
        # In durable mode, fsync after each data write
        if self.durable:
            for chunk_id, block_num, data in self.pending_data:
                _fsync()  # fsync after each block
        else:
            # Fast mode: single fsync for all data
            _fsync()
        
        # Update metadata
        for callback in self.pending_metadata:
            callback()
        
        # Final fsync for metadata in durable mode
        if self.durable:
            _fsync()
        else:
            # Single fsync for all metadata
            _fsync()
        
        # Clear pending
        flushed_ops = self.ops_count
        self.pending_data = []
        self.pending_metadata = []
        self.bytes_accumulated = 0
        self.ops_count = 0
        self._flushed = True
        
        return flushed_ops
    
    def _write_data(self, chunk_id: int, block_num: int, data: bytes):
        """Write data to chunk (internal)"""
        chunk = read_chunk(self.vault_path, chunk_id)
        chunk.write_block(block_num, data)
    
    def __del__(self):
        """Flush pending writes on cleanup (disabled to avoid errors)"""
        pass  # Don't auto-flush in __del__ - can cause issues
        # if self.pending_data or self.pending_metadata:
        #     self.flush()


class DurableWriter:
    """Strict durable writer - fsync after every write"""
    
    def __init__(self, vault_path: str):
        self.vault_path = vault_path
    
    def write(self, chunk_id: int, block_num: int, data: bytes):
        """Write with immediate fsync"""
        chunk = read_chunk(self.vault_path, chunk_id)
        chunk.write_block(block_num, data)
        _fsync()  # Immediate fsync
    
    def update_metadata(self, callback):
        """Update metadata with immediate fsync"""
        callback()
        _fsync()


# Global batch writer instance (singleton per vault)
_batch_writers = {}


def get_batch_writer(vault_path: str, durable: bool = False, max_ops: int = 50, max_bytes: int = 8*1024*1024) -> BatchWriter:
    """Get or create batch writer (singleton per vault)"""
    global _batch_writers
    
    # Create key for this vault+durable combination
    key = (vault_path, durable)
    
    if key not in _batch_writers:
        _batch_writers[key] = BatchWriter(vault_path, durable, max_ops, max_bytes)
    
    return _batch_writers[key]


def create_writer(vault_path: str, durable: bool = False):
    """Create a new writer (batch or durable based on mode)"""
    if durable:
        return DurableWriter(vault_path)
    else:
        return BatchWriter(vault_path, durable=False)

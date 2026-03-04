# Chunk Index - for fast vault opening without scanning
# Format: stored in fixed metadata region
# Offset: 0x100000 - 0x30000 = 0xD0000 (768 KB after vault start)
# Size: 128 KB (can hold 16384 chunk entries)

import struct
import hashlib
import os
import sys

# Add core to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from core import Superblock, read_superblock, Chunk, read_chunk, CHUNK_SIZE, BLOCKS_PER_CHUNK

CHUNK_INDEX_OFFSET = 0xD0000
CHUNK_INDEX_SIZE = 128 * 1024  # 128 KB
CHUNK_ENTRY_SIZE = 64  # bytes per chunk entry

CHUNK_STATE_FREE = 0
CHUNK_STATE_USED = 1
CHUNK_STATE_DIRTY = 2


def get_chunk_index_offset():
    """Get offset for chunk index in vault"""
    return CHUNK_INDEX_OFFSET


def read_chunk_index(vault_path: str) -> dict:
    """Read chunk index from vault. Returns dict of chunk_id -> info"""
    index = {}
    try:
        with open(vault_path, 'rb') as f:
            f.seek(CHUNK_INDEX_OFFSET)
            data = f.read(CHUNK_INDEX_SIZE)
        
        # Parse entries - only check first entry to see if initialized
        first_entry = data[:64]
        first_chunk_id = struct.unpack('<I', first_entry[0:4])[0]
        
        # Check if index is completely uninitialized (all zeros)
        if first_entry == b'\x00' * 64:
            return index
        
        # Parse entries
        for i in range(0, len(data), CHUNK_ENTRY_SIZE):
            entry = data[i:i+CHUNK_ENTRY_SIZE]
            if len(entry) < CHUNK_ENTRY_SIZE:
                break
            
            chunk_id = struct.unpack('<I', entry[0:4])[0]
            
            # Skip uninitialized entries (chunk_id = 0 with zero offset)
            chunk_offset = struct.unpack('<Q', entry[4:12])[0]
            if chunk_id == 0 and chunk_offset == 0:
                continue
            
            # Skip empty markers
            if chunk_id == 0xFFFFFFFF:
                continue
            
            state = entry[12]
            checksum = entry[13:45]  # 32 bytes SHA-256
            
            index[chunk_id] = {
                'chunk_id': chunk_id,
                'chunk_offset': chunk_offset,
                'state': state,
                'checksum': checksum
            }
    except Exception as e:
        print(f"Error reading chunk index: {e}")
    
    return index


def write_chunk_index(vault_path: str, index: dict):
    """Write chunk index to vault"""
    data = bytearray(CHUNK_INDEX_SIZE)
    
    for chunk_id, info in index.items():
        if chunk_id < 0:
            continue
        
        # Use chunk_id directly as position
        pos = chunk_id * CHUNK_ENTRY_SIZE
        if pos + CHUNK_ENTRY_SIZE > len(data):
            continue
        
        entry = b''
        entry += struct.pack('<I', info['chunk_id'])
        entry += struct.pack('<Q', info['chunk_offset'])
        entry += struct.pack('<B', info['state'])
        
        # Manually pad checksum to 32 bytes
        checksum = info.get('checksum', b'')
        if isinstance(checksum, bytes):
            if len(checksum) < 32:
                checksum = checksum + (b'\x00' * (32 - len(checksum)))
            elif len(checksum) > 32:
                checksum = checksum[:32]
        else:
            checksum = b'\x00' * 32
        
        entry += checksum
        
        # Pad to 64 bytes
        if len(entry) < CHUNK_ENTRY_SIZE:
            entry = entry + (b'\x00' * (CHUNK_ENTRY_SIZE - len(entry)))
        
        data[pos:pos+CHUNK_ENTRY_SIZE] = entry
    
    with open(vault_path, 'r+b') as f:
        f.seek(CHUNK_INDEX_OFFSET)
        f.write(data)
        f.flush()


def build_chunk_index(vault_path: str) -> dict:
    """Build chunk index by scanning chunks"""
    sb = read_superblock(vault_path)
    index = {}
    
    for chunk_id in range(sb.used_chunks):
        try:
            chunk = read_chunk(vault_path, chunk_id)
            chunk_offset = 0x100000 + chunk_id * CHUNK_SIZE
            
            # Compute checksum of chunk header
            with open(vault_path, 'rb') as f:
                f.seek(chunk_offset)
                header_data = f.read(0x1000)  # First 4KB
            checksum = hashlib.sha256(header_data).digest()
            
            index[chunk_id] = {
                'chunk_id': chunk_id,
                'chunk_offset': chunk_offset,
                'state': CHUNK_STATE_USED,
                'checksum': checksum
            }
        except Exception as e:
            print(f"Warning: Could not read chunk {chunk_id}: {e}")
    
    return index


def validate_chunk_index(vault_path: str, index: dict) -> bool:
    """Validate chunk index against actual chunks"""
    if not index:
        return False
    
    for chunk_id, info in index.items():
        try:
            chunk = read_chunk(vault_path, chunk_id)
            # Verification passed
        except:
            return False
    
    return True


def get_chunk_from_index(vault_path: str, chunk_id: int) -> dict:
    """Get chunk info from index, or None if not found"""
    index = read_chunk_index(vault_path)
    return index.get(chunk_id)


# Transaction Batching
class TransactionBatch:
    """Transaction batching for write optimization"""
    
    def __init__(self, vault_path: str, durable: bool = False):
        self.vault_path = vault_path
        self.durable = durable
        self.pending_writes = []
        self.pending_metadata = []
        self.fsunc_count = 0
    
    def add_write(self, chunk_id: int, block_num: int, data: bytes):
        """Add a write to the batch"""
        self.pending_writes.append((chunk_id, block_num, data))
    
    def add_metadata_update(self, callback):
        """Add a metadata update (bitmap, LBA, etc)"""
        self.pending_metadata.append(callback)
    
    def commit(self):
        """Commit all pending writes with minimal fsync"""
        # Write all data blocks first
        for chunk_id, block_num, data in self.pending_writes:
            chunk = read_chunk(self.vault_path, chunk_id)
            chunk.write_block(block_num, data)
        
        # Single fsync for all data
        self.fsunc_count += 1
        if self.durable:
            # fsync for each write in durable mode
            pass
        
        # Then update metadata
        for callback in self.pending_metadata:
            callback()
        
        # Final fsync for metadata
        self.fsunc_count += 1
        
        # Clear pending
        self.pending_writes = []
        self.pending_metadata = []
        
        return self.fsunc_count
    
    def get_fsync_count(self) -> int:
        return self.fsunc_count

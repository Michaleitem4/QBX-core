"""Core object table operations - no CLI dependencies."""
import struct
import os
from dataclasses import dataclass
from typing import List, Optional
from .constants import CHUNK_SIZE


# Stub classes for backward compatibility (used by __init__.py)
@dataclass
class ObjectTableEntry:
    """Legacy entry format - kept for compatibility."""
    inode: int
    path: str
    size: int
    blocks: int
    checksum: bytes
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ObjectTableEntry':
        return cls(
            inode=data.get('inode', 0),
            path=data.get('path', ''),
            size=data.get('size', 0),
            blocks=data.get('blocks', 0),
            checksum=data.get('checksum', b'')
        )


class ObjectTable:
    """Legacy object table - kept for compatibility."""
    
    def __init__(self, vault_path: str):
        self.vault_path = vault_path
        self.objects = list_objects(vault_path)
    
    def list_all(self) -> List[dict]:
        return self.objects


def read_object_table(vault_path: str) -> ObjectTable:
    """Legacy function - returns ObjectTable."""
    return ObjectTable(vault_path)


def list_objects(vault_path):
    """
    List all objects in vault - CORE VERSION (no CLI dependencies).
    
    Returns list of dicts with:
    - inode, path, size, blocks, blocks_list, checksum, hash_alg, hash_len
    """
    objects = []
    offset = 0x100000 + CHUNK_SIZE + 0x60000
    
    # Entry size: 96 bytes (v5 format with encryption)
    entry_size = 96
    
    try:
        with open(vault_path, 'rb') as f:
            f.seek(offset)
            data = f.read(entry_size * 1000)
        
        for i in range(0, len(data), entry_size):
            entry = data[i:i+entry_size]
            if len(entry) < 64:
                break
            
            ent_inode = struct.unpack('<I', entry[0:4])[0]
            if ent_inode == 0:
                continue
                
            size = struct.unpack('<I', entry[4:8])[0]
            block_count = struct.unpack('<H', entry[8:10])[0]
            
            # Hash info
            hash_alg = entry[10] if len(entry) > 10 else 1
            hash_len = entry[11] if len(entry) > 11 else 20
            
            created = struct.unpack('<Q', entry[12:20])[0]
            
            if hash_len == 32:
                checksum = entry[20:52]
            else:
                checksum = entry[20:40]
            
            # Block refs
            blocks_list = []
            max_blocks = 12 if hash_len == 20 else 6
            for j in range(min(block_count, max_blocks)):
                ref_offset = 40 + j*2 if hash_len == 20 else 52 + j*2
                if ref_offset + 2 <= len(entry):
                    ref = struct.unpack('<H', entry[ref_offset:ref_offset+2])[0]
                    chunk_id = ref >> 11
                    lba = ref & 0x7FF
                    blocks_list.append((chunk_id, lba))
            
            # Compression metadata
            compression = 0
            stored_size = size
            if hash_len == 32 and len(entry) >= 72:
                compression = struct.unpack('<H', entry[64:66])[0]
                stored_size = struct.unpack('<I', entry[66:70])[0]
            
            # Encryption metadata
            encryption = 0
            salt = b''
            if hash_len == 32 and len(entry) >= 80:
                encryption = entry[70]
                salt_len = entry[71]
                if salt_len > 0 and salt_len <= 16:
                    salt = entry[72:72+salt_len]
            
            # Get path from path table
            path = _get_path(vault_path, ent_inode)
            
            objects.append({
                'inode': ent_inode, 
                'path': path, 
                'size': size, 
                'blocks': block_count,
                'blocks_list': blocks_list,
                'checksum': checksum,
                'hash_alg': hash_alg,
                'hash_len': hash_len,
                'compression': compression,
                'stored_size': stored_size,
                'encryption': encryption,
                'salt': salt
            })
    except Exception as e:
        pass  # Return empty list on error
    
    return objects


def _get_path(vault_path, inode):
    """Get path for inode from vault path table."""
    offset = 0x100000 + CHUNK_SIZE + 0x80000
    try:
        with open(vault_path, 'rb') as f:
            f.seek(offset)
            data = f.read(65536)
        
        text = data.decode('utf-8', errors='ignore')
        for line in text.split('\n'):
            if '|' in line:
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    try:
                        if int(parts[0]) == inode:
                            return parts[1]
                    except:
                        pass
    except:
        pass
    return f"/file_{inode}"


def list_objects(vault_path):
    """
    List all objects in vault - CORE VERSION (no CLI dependencies).
    
    Returns list of dicts with:
    - inode, path, size, blocks, blocks_list, checksum, hash_alg, hash_len
    """
    objects = []
    offset = 0x100000 + CHUNK_SIZE + 0x60000
    
    # Entry size: 96 bytes (v5 format with encryption)
    entry_size = 96
    
    try:
        with open(vault_path, 'rb') as f:
            f.seek(offset)
            data = f.read(entry_size * 1000)
        
        for i in range(0, len(data), entry_size):
            entry = data[i:i+entry_size]
            if len(entry) < 64:
                break
            
            ent_inode = struct.unpack('<I', entry[0:4])[0]
            if ent_inode == 0:
                continue
                
            size = struct.unpack('<I', entry[4:8])[0]
            block_count = struct.unpack('<H', entry[8:10])[0]
            
            # Hash info
            hash_alg = entry[10] if len(entry) > 10 else 1
            hash_len = entry[11] if len(entry) > 11 else 20
            
            created = struct.unpack('<Q', entry[12:20])[0]
            
            if hash_len == 32:
                checksum = entry[20:52]
            else:
                checksum = entry[20:40]
            
            # Block refs
            blocks_list = []
            max_blocks = 12 if hash_len == 20 else 6
            for j in range(min(block_count, max_blocks)):
                ref_offset = 40 + j*2 if hash_len == 20 else 52 + j*2
                if ref_offset + 2 <= len(entry):
                    ref = struct.unpack('<H', entry[ref_offset:ref_offset+2])[0]
                    chunk_id = ref >> 11
                    lba = ref & 0x7FF
                    blocks_list.append((chunk_id, lba))
            
            # Compression metadata
            compression = 0
            stored_size = size
            if hash_len == 32 and len(entry) >= 72:
                compression = struct.unpack('<H', entry[64:66])[0]
                stored_size = struct.unpack('<I', entry[66:70])[0]
            
            # Encryption metadata
            encryption = 0
            salt = b''
            if hash_len == 32 and len(entry) >= 80:
                encryption = entry[70]
                salt_len = entry[71]
                if salt_len > 0 and salt_len <= 16:
                    salt = entry[72:72+salt_len]
            
            # Get path from path table
            path = _get_path(vault_path, ent_inode)
            
            objects.append({
                'inode': ent_inode, 
                'path': path, 
                'size': size, 
                'blocks': block_count,
                'blocks_list': blocks_list,
                'checksum': checksum,
                'hash_alg': hash_alg,
                'hash_len': hash_len,
                'compression': compression,
                'stored_size': stored_size,
                'encryption': encryption,
                'salt': salt
            })
    except Exception as e:
        pass  # Return empty list on error
    
    return objects


def _get_path(vault_path, inode):
    """Get path for inode from vault path table."""
    offset = 0x100000 + CHUNK_SIZE + 0x80000
    try:
        with open(vault_path, 'rb') as f:
            f.seek(offset)
            data = f.read(65536)
        
        text = data.decode('utf-8', errors='ignore')
        for line in text.split('\n'):
            if '|' in line:
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    try:
                        if int(parts[0]) == inode:
                            return parts[1]
                    except:
                        pass
    except:
        pass
    return f"/file_{inode}"

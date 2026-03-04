"""
QBX Vault - Superblock implementation
"""

import struct
import hashlib
import uuid
import time
from typing import Optional
from dataclasses import dataclass
from .constants import (
    MAGIC_SUPERBLOCK, SUPERBLOCK_SIZE, SUPERBLOCK_BACKUP_OFFSET,
    BLOCK_SIZE, CHUNK_SIZE, VERSION_MAJOR, VERSION_MINOR,
    STATUS_CLEAN, STATUS_DIRTY
)
from .errors import IntegrityError


@dataclass
class Superblock:
    """Superblock del vault - primer y último bloque del archivo"""
    version: int = VERSION_MAJOR
    block_size: int = BLOCK_SIZE
    chunk_size: int = CHUNK_SIZE
    total_chunks: int = 0
    used_chunks: int = 0
    vault_uuid: str = ""
    creation_time: int = 0
    last_modified: int = 0
    root_chunk: int = 0
    root_offset: int = 0
    features: int = 0
    status: int = STATUS_CLEAN
    max_snapshots: int = 16  # Default 16 snapshots
    
    def __post_init__(self):
        if not self.vault_uuid:
            self.vault_uuid = str(uuid.uuid4())
        if not self.creation_time:
            self.creation_time = int(time.time())
        if not self.last_modified:
            self.last_modified = self.creation_time
    
    def pack(self) -> bytes:
        """Serializa el superblock a bytes"""
        # Reserved space - pad to 516 total
        # Fields: magic(8) + ver(4) + block(4) + chunk(4) + total(8) + used(8) + uuid(16) + 
        #         created(8) + modified(8) + root(8) + root_off(8) + feat(4) + status(4) + 
        #         max_snap(4) = 96
        # Reserved = 516 - 96 - 32 = 388
        reserved = b'\x00' * 388
        
        data = (
            MAGIC_SUPERBLOCK +
            struct.pack('<I', self.version) +
            struct.pack('<I', self.block_size) +
            struct.pack('<I', self.chunk_size) +
            struct.pack('<Q', self.total_chunks) +
            struct.pack('<Q', self.used_chunks) +
            (self.vault_uuid.encode()[:16] + b'\x00' * 16)[:16] +
            struct.pack('<Q', self.creation_time) +
            struct.pack('<Q', self.last_modified) +
            struct.pack('<Q', self.root_chunk) +
            struct.pack('<Q', self.root_offset) +
            struct.pack('<I', self.features) +
            struct.pack('<I', self.status) +
            struct.pack('<I', self.max_snapshots) +  # NEW: max snapshots
            b'\x00' * 32 +  # checksum placeholder
            reserved
        )
        
        # Calculate checksum (SHA-256 of everything except 32-byte checksum field)
        # Checksum field is at 0x54-0x74
        # We hash: bytes 0-83 (everything before checksum) + bytes 116+ (everything after)
        checksum = hashlib.sha256(data[:0x54] + data[0x74:]).digest()
        
        # Replace checksum
        return data[:0x54] + checksum + data[0x74:]
    
    @classmethod
    def unpack(cls, data: bytes) -> 'Superblock':
        """Deserializa desde bytes"""
        if len(data) < SUPERBLOCK_SIZE:
            raise ValueError(f"Data too small: {len(data)} < {SUPERBLOCK_SIZE}")
        
        magic = data[:8]
        if magic != MAGIC_SUPERBLOCK:
            raise ValueError(f"Invalid magic: {magic}")
        
        # Verify checksum
        stored_checksum = data[0x54:0x74]
        calculated = hashlib.sha256(data[:0x54] + data[0x74:]).digest()
        
        if stored_checksum != calculated:
            raise IntegrityError("Superblock checksum mismatch")
        
        version = struct.unpack('<I', data[0x08:0x0C])[0]
        block_size = struct.unpack('<I', data[0x0C:0x10])[0]
        chunk_size = struct.unpack('<I', data[0x10:0x14])[0]
        total_chunks = struct.unpack('<Q', data[0x14:0x1C])[0]
        used_chunks = struct.unpack('<Q', data[0x1C:0x24])[0]
        vault_uuid = data[0x24:0x34].rstrip(b'\x00').decode()
        creation_time = struct.unpack('<Q', data[0x34:0x3C])[0]
        last_modified = struct.unpack('<Q', data[0x3C:0x44])[0]
        root_chunk = struct.unpack('<Q', data[0x44:0x4C])[0]
        root_offset = struct.unpack('<Q', data[0x4C:0x54])[0]
        features = struct.unpack('<I', data[0x54:0x58])[0]
        status = struct.unpack('<I', data[0x58:0x5C])[0]
        
        # Backward compatibility: max_snapshots added in version 3
        # Old vaults have garbage at 0x5C - default to 16
        max_snapshots = 16  # Default
        if version >= 3 and len(data) >= 0x60:
            max_snapshots = struct.unpack('<I', data[0x5C:0x60])[0]
        
        return cls(
            version=version,
            block_size=block_size,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            used_chunks=used_chunks,
            vault_uuid=vault_uuid,
            creation_time=creation_time,
            last_modified=last_modified,
            root_chunk=root_chunk,
            root_offset=root_offset,
            features=features,
            status=status,
            max_snapshots=max_snapshots
        )
    
    def verify(self) -> bool:
        """Verifica integridad del superblock"""
        try:
            data = self.pack()
            stored = data[0x54:0x74]
            calculated = hashlib.sha256(data[:0x54] + data[0x74:]).digest()
            return stored == calculated
        except:
            return False


def create_superblock(total_chunks: int = 0) -> Superblock:
    """Crea un nuevo superblock"""
    return Superblock(total_chunks=total_chunks)


def read_superblock(path: str, backup: bool = False) -> Superblock:
    """Lee el superblock desde archivo"""
    offset = SUPERBLOCK_BACKUP_OFFSET if backup else 0
    
    with open(path, 'rb') as f:
        f.seek(offset)
        data = f.read(SUPERBLOCK_SIZE)
    
    return Superblock.unpack(data)


def write_superblock(path: str, sb: Superblock, sync: bool = True) -> None:
    """Escribe el superblock (primary y backup)"""
    sb.last_modified = int(time.time())
    data = sb.pack()
    
    # Write primary
    with open(path, 'r+b') as f:
        f.seek(0)
        f.write(data)
        if sync:
            f.flush()
    
    # Write backup
    with open(path, 'r+b') as f:
        f.seek(SUPERBLOCK_BACKUP_OFFSET)
        f.write(data)
        if sync:
            f.flush()

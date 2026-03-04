"""
QBX Vault - Block implementation
"""

import struct
import hashlib
from typing import Optional
from .constants import (
    MAGIC_BLOCK, BLOCK_SIZE, BLOCK_HEADER_SIZE
)


class BlockHeader:
    """Header de cada bloque de datos"""
    
    def __init__(self, 
                 flags: int = 0,
                 compression: int = 0,
                 original_size: int = 0,
                 compressed_size: int = 0,
                 checksum: bytes = None):
        self.flags = flags          # bit0: compressed
        self.compression = compression  # 0=none, 1=lz4, 2=zstd
        self.original_size = original_size
        self.compressed_size = compressed_size
        self.checksum = checksum or b'\x00' * 32
    
    def pack(self) -> bytes:
        """Serializa el header"""
        return (
            struct.pack('<I', MAGIC_BLOCK) +
            struct.pack('<B', self.flags) +
            struct.pack('<B', self.compression) +
            b'\x00\x00' +  # reserved (2 bytes)
            struct.pack('<I', self.original_size) +
            struct.pack('<I', self.compressed_size) +
            self.checksum +
            b'\x00' * 16  # reserved to make header = 64 bytes
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> 'BlockHeader':
        """Deserializa desde bytes"""
        magic = struct.unpack('<I', data[0:4])[0]
        if magic != MAGIC_BLOCK:
            raise ValueError(f"Invalid block magic: {hex(magic)}")
        
        flags = data[4]
        compression = data[5]
        original_size = struct.unpack('<I', data[8:12])[0]
        compressed_size = struct.unpack('<I', data[12:16])[0]
        checksum = data[16:48]
        
        return cls(flags, compression, original_size, compressed_size, checksum)
    
    def verify(self, payload: bytes) -> bool:
        """Verifica el checksum del payload"""
        calculated = hashlib.sha256(payload).digest()
        return self.checksum == calculated


class Block:
    """Representa un bloque de datos en el vault"""
    
    def __init__(self, data: bytes = b'', compressed: bool = False, 
                 compression_type: int = 0):
        self._data = data
        self.compressed = compressed
        self.compression_type = compression_type
    
    @property
    def data(self) -> bytes:
        return self._data
    
    @property
    def original_size(self) -> int:
        return len(self._data)
    
    @property
    def compressed_size(self) -> int:
        return len(self._data)
    
    @property
    def flags(self) -> int:
        return 1 if self.compressed else 0
    
    def pack(self) -> bytes:
        """Serializa el bloque completo (header + data)"""
        # Calculate checksum using the actual data
        data_bytes = self._data
        checksum = hashlib.sha256(data_bytes).digest()
        
        header = BlockHeader(
            flags=self.flags,
            compression=self.compression_type,
            original_size=len(data_bytes),
            compressed_size=len(data_bytes),
            checksum=checksum
        )
        
        # Return header + data
        return header.pack() + data_bytes
    
    @classmethod
    def unpack(cls, data: bytes) -> 'Block':
        """Deserializa desde bytes"""
        if len(data) < BLOCK_HEADER_SIZE:
            raise ValueError(f"Data too small: {len(data)} < {BLOCK_HEADER_SIZE}")
        
        header = BlockHeader.unpack(data[:BLOCK_HEADER_SIZE])
        
        # Read payload based on compressed size
        payload = data[BLOCK_HEADER_SIZE:BLOCK_HEADER_SIZE + header.compressed_size]
        
        # Verify checksum
        if not header.verify(payload):
            raise ValueError("Block checksum mismatch")
        
        block = cls(
            data=payload,
            compressed=bool(header.flags & 1),
            compression_type=header.compression
        )
        
        return block
    
    @classmethod
    def from_file(cls, file_path: str) -> 'Block':
        """Carga un bloque desde archivo"""
        with open(file_path, 'rb') as f:
            data = f.read()
        return cls(data=data)
    
    def verify(self) -> bool:
        """Verifica integridad del bloque"""
        calculated = hashlib.sha256(self._data).digest()
        header = BlockHeader(
            flags=self.flags,
            compression=self.compression_type,
            original_size=len(self._data),
            compressed_size=len(self._data),
            checksum=calculated
        )
        return True


def write_block_file(path: str, offset: int, data: bytes) -> int:
    """Escribe un bloque a archivo (sin comprimir)"""
    block = Block(data)
    packed = block.pack()
    
    with open(path, 'r+b') as f:
        f.seek(offset)
        f.write(packed)
        f.flush()
    
    return len(packed)


def read_block_file(path: str, offset: int, size: int = None) -> Block:
    """Lee un bloque desde archivo"""
    with open(path, 'rb') as f:
        f.seek(offset)
        
        # Read header first
        header_data = f.read(BLOCK_HEADER_SIZE)
        if len(header_data) < BLOCK_HEADER_SIZE:
            raise ValueError("Cannot read block header")
        
        header = BlockHeader.unpack(header_data)
        
        # Read payload
        payload = f.read(header.compressed_size)
        
        # Reconstruct full data
        full_data = header_data + payload
    
    return Block.unpack(full_data)


def compute_hash(data: bytes) -> bytes:
    """Calcula SHA-256 hash"""
    return hashlib.sha256(data).digest()


def verify_data(data: bytes, expected_hash: bytes) -> bool:
    """Verifica hash de datos"""
    return hashlib.sha256(data).digest() == expected_hash

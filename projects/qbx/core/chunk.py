"""
QBX Vault - Chunk implementation
"""

import struct
import hashlib
import time
from typing import Optional, List
from dataclasses import dataclass
from .constants import (
    MAGIC_CHUNK, MAGIC_FOOTER,
    CHUNK_HEADER_SIZE, CHUNK_HEADER_OFFSET,
    CHUNK_BITMAP_SIZE, CHUNK_BITMAP_OFFSET,
    CHUNK_LBA_TABLE_SIZE, CHUNK_LBA_TABLE_OFFSET,
    CHUNK_OBJECT_TABLE_SIZE,
    CHUNK_DATA_OFFSET, CHUNK_SIZE,
    BLOCK_SIZE, BLOCKS_PER_CHUNK, BLOCK_HEADER_SIZE
)


@dataclass
class ChunkHeader:
    """Header de cada chunk"""
    chunk_index: int = 0
    epoch: int = 0
    object_count: int = 0
    free_space: int = CHUNK_DATA_OFFSET  # Starts at data offset
    root_pointer: int = 0  # Offset of root tree within chunk
    
    def pack(self) -> bytes:
        """Serializa el header"""
        data = (
            struct.pack('<I', MAGIC_CHUNK) +
            struct.pack('<I', self.chunk_index) +
            struct.pack('<Q', self.epoch) +
            struct.pack('<Q', self.object_count) +
            struct.pack('<Q', self.free_space) +
            struct.pack('<Q', self.root_pointer) +
            b'\x00' * 32 +  # checksum placeholder
            b'\x00' * 208   # reserved
        )
        
        # Calculate checksum
        checksum = hashlib.sha256(data[:0x48]).digest()
        
        return data[:0x28] + checksum + data[0x48:]
    
    @classmethod
    def unpack(cls, data: bytes) -> 'ChunkHeader':
        """Deserializa desde bytes"""
        magic = struct.unpack('<I', data[0:4])[0]
        if magic != MAGIC_CHUNK:
            raise ValueError(f"Invalid chunk magic: {hex(magic)}")
        
        chunk_index = struct.unpack('<I', data[4:8])[0]
        epoch = struct.unpack('<Q', data[8:16])[0]
        object_count = struct.unpack('<Q', data[0x10:0x18])[0]
        free_space = struct.unpack('<Q', data[0x18:0x20])[0]
        root_pointer = struct.unpack('<Q', data[0x20:0x28])[0]
        
        return cls(
            chunk_index=chunk_index,
            epoch=epoch,
            object_count=object_count,
            free_space=free_space,
            root_pointer=root_pointer
        )
    
    def verify(self, data: bytes) -> bool:
        """Verifica checksum"""
        stored = data[0x28:0x48]
        calculated = hashlib.sha256(data[:0x28] + data[0x48:]).digest()
        return stored == calculated


@dataclass
class ChunkFooter:
    """Footer del chunk para verificación"""
    chunk_index: int = 0
    epoch: int = 0
    object_count: int = 0
    
    def pack(self) -> bytes:
        return (
            struct.pack('<I', MAGIC_FOOTER) +
            struct.pack('<I', self.chunk_index) +
            struct.pack('<Q', self.epoch) +
            struct.pack('<Q', self.object_count) +
            b'\x00' * 40
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> 'ChunkFooter':
        magic = struct.unpack('<I', data[0:4])[0]
        if magic != MAGIC_FOOTER:
            raise ValueError(f"Invalid footer magic: {hex(magic)}")
        
        return cls(
            chunk_index=struct.unpack('<I', data[4:8])[0],
            epoch=struct.unpack('<Q', data[8:16])[0],
            object_count=struct.unpack('<Q', data[0x10:0x18])[0]
        )


class Chunk:
    """Gestión de un chunk individual"""
    
    def __init__(self, vault_path: str, chunk_index: int, create: bool = False):
        self.vault_path = vault_path
        self.chunk_index = chunk_index
        self.offset = 0x100000 + (chunk_index * CHUNK_SIZE)
        
        if create:
            self._create()
        else:
            self._load()
    
    def _create(self):
        """Crea un chunk vacío"""
        # Inicializar bitmap (todos libres)
        self.bitmap = bytearray(CHUNK_BITMAP_SIZE)
        
        # LBA table (todos 0xFF = no asignado)
        self.lba_table = [0xFFFFFFFFFFFFFFFF] * BLOCKS_PER_CHUNK
        
        # Object table vacío
        self.objects = []
        
        # Header inicial
        self.header = ChunkHeader(
            chunk_index=self.chunk_index,
            epoch=1,
            object_count=0,
            free_space=CHUNK_DATA_OFFSET,
            root_pointer=CHUNK_LBA_TABLE_OFFSET
        )
        
        self._save_all()
    
    def _load(self):
        """Carga el chunk desde disco"""
        # Inicializar objects para evitar errores
        self.objects = []
        
        with open(self.vault_path, 'rb') as f:
            f.seek(self.offset)
            
            # Read header
            header_data = f.read(CHUNK_HEADER_SIZE)
            self.header = ChunkHeader.unpack(header_data)
            
            # Read bitmap
            f.seek(self.offset + CHUNK_BITMAP_OFFSET)
            self.bitmap = bytearray(f.read(CHUNK_BITMAP_SIZE))
            
            # Read LBA table
            f.seek(self.offset + CHUNK_LBA_TABLE_OFFSET)
            lba_data = f.read(CHUNK_LBA_TABLE_SIZE)
            self.lba_table = list(struct.unpack('<' + 'Q'*BLOCKS_PER_CHUNK, lba_data))
    
    def _save_all(self):
        """Guarda todo el chunk (header, bitmap, LBA table)"""
        # Calculate data offset
        data_offset = self.offset + CHUNK_DATA_OFFSET
        
        # Calculate free space
        used_blocks = sum(1 for x in self.lba_table if x != 0xFFFFFFFFFFFFFFFF)
        self.header.free_space = CHUNK_DATA_OFFSET + (BLOCKS_PER_CHUNK - used_blocks) * BLOCK_SIZE
        self.header.object_count = len(self.objects)
        
        with open(self.vault_path, 'r+b') as f:
            # Write header
            f.seek(self.offset)
            f.write(self.header.pack())
            
            # Write bitmap
            f.seek(self.offset + CHUNK_BITMAP_OFFSET)
            f.write(self.bitmap)
            
            # Write LBA table
            f.seek(self.offset + CHUNK_LBA_TABLE_OFFSET)
            lba_data = struct.pack('<' + 'Q'*BLOCKS_PER_CHUNK, *self.lba_table)
            f.write(lba_data)
            
            f.flush()
    
    def allocate_block(self) -> Optional[int]:
        """Busca un bloque libre y lo marca usado"""
        for i in range(BLOCKS_PER_CHUNK):
            byte_idx = i // 8
            bit_idx = i % 8
            
            if not (self.bitmap[byte_idx] & (1 << bit_idx)):
                # Marcar como usado
                self.bitmap[byte_idx] |= (1 << bit_idx)
                self._save_all()
                return i
        
        return None
    
    def free_block(self, block_num: int):
        """Libera un bloque"""
        byte_idx = block_num // 8
        bit_idx = block_num % 8
        self.bitmap[byte_idx] &= ~(1 << bit_idx)
        self._save_all()
    
    def get_block_offset(self, block_num: int) -> int:
        """Obtiene el offset físico de un bloque"""
        return self.offset + CHUNK_DATA_OFFSET + (block_num * BLOCK_SIZE)
    
    def write_block(self, block_num: int, data: bytes) -> int:
        """Escribe datos en un bloque específico"""
        if block_num >= BLOCKS_PER_CHUNK:
            raise ValueError(f"Block number out of range: {block_num}")
        
        offset = self.get_block_offset(block_num)
        
        with open(self.vault_path, 'r+b') as f:
            f.seek(offset)
            f.write(data)
            f.flush()
        
        # Update LBA
        self.lba_table[block_num] = len(data)
        
        # Mark bitmap
        byte_idx = block_num // 8
        bit_idx = block_num % 8
        self.bitmap[byte_idx] |= (1 << bit_idx)
        
        self._save_all()
        
        return len(data)
    
    def read_block(self, block_num: int, size: int = BLOCK_SIZE) -> bytes:
        """Lee un bloque"""
        offset = self.get_block_offset(block_num)
        
        with open(self.vault_path, 'rb') as f:
            f.seek(offset)
            return f.read(size)


def create_chunk(vault_path: str, chunk_index: int) -> Chunk:
    """Crea un nuevo chunk"""
    return Chunk(vault_path, chunk_index, create=True)


def read_chunk(vault_path: str, chunk_index: int) -> Chunk:
    """Lee un chunk existente"""
    return Chunk(vault_path, chunk_index, create=False)

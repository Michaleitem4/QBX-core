"""
QBX Vault - Bitmap Allocator
"""

from .constants import BLOCKS_PER_CHUNK, CHUNK_BITMAP_SIZE


class Bitmap:
    """Bitmap de asignación de bloques"""
    
    def __init__(self, data: bytearray = None):
        if data:
            self.data = data
        else:
            self.data = bytearray(CHUNK_BITMAP_SIZE)
    
    def allocate(self) -> int:
        """Busca primer bloque libre y lo marca"""
        for i in range(BLOCKS_PER_CHUNK):
            byte_idx = i // 8
            bit_idx = i % 8
            
            if not (self.data[byte_idx] & (1 << bit_idx)):
                self.data[byte_idx] |= (1 << bit_idx)
                return i
        
        return -1  # No hay bloques libres
    
    def free(self, block_num: int):
        """Libera un bloque"""
        if 0 <= block_num < BLOCKS_PER_CHUNK:
            byte_idx = block_num // 8
            bit_idx = block_num % 8
            self.data[byte_idx] &= ~(1 << bit_idx)
    
    def is_allocated(self, block_num: int) -> bool:
        """Verifica si un bloque está asignado"""
        byte_idx = block_num // 8
        bit_idx = block_num % 8
        return bool(self.data[byte_idx] & (1 << bit_idx))
    
    def count_free(self) -> int:
        """Cuenta bloques libres"""
        free = 0
        for i in range(BLOCKS_PER_CHUNK):
            if not self.is_allocated(i):
                free += 1
        return free
    
    def count_used(self) -> int:
        """Cuenta bloques usados"""
        return BLOCKS_PER_CHUNK - self.count_free()
    
    def get_free_blocks(self) -> list:
        """Retorna lista de bloques libres"""
        return [i for i in range(BLOCKS_PER_CHUNK) if not self.is_allocated(i)]
    
    def dump(self) -> bytes:
        """Exporta el bitmap"""
        return bytes(self.data)
    
    @classmethod
    def load(cls, data: bytes) -> 'Bitmap':
        """Importa un bitmap"""
        return cls(bytearray(data))


class ChunkBitmap(Bitmap):
    """Bitmap específico para un chunk"""
    
    def __init__(self, chunk_index: int, data: bytearray = None):
        super().__init__(data)
        self.chunk_index = chunk_index
    
    def get_physical_offset(self, block_num: int) -> int:
        """Calcula offset físico del bloque"""
        # Por ahora, asume que el chunk está en el vault
        # El offset físico se calcula en el nivel de Chunk
        return block_num * 65536  # 64KB por bloque


def test_bitmap():
    """Test del bitmap"""
    bm = Bitmap()
    
    # Allocate 3 blocks
    b1 = bm.allocate()
    b2 = bm.allocate()
    b3 = bm.allocate()
    
    print(f"Allocated: {b1}, {b2}, {b3}")
    print(f"Used: {bm.count_used()}")
    print(f"Free: {bm.count_free()}")
    
    # Free middle
    bm.free(b2)
    print(f"After free b2: used={bm.count_used()}, free={bm.count_free()}")
    
    # Allocate again
    b4 = bm.allocate()
    print(f"Reallocated: {b4} (should be {b2})")


if __name__ == "__main__":
    test_bitmap()

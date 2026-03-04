"""Tests for superblock module."""
import pytest
import os
import tempfile
import hashlib
from core.superblock import Superblock, create_superblock, read_superblock
from core.errors import IntegrityError


def test_superblock_checksum_roundtrip():
    """Test that pack/unpack preserves all fields including checksum."""
    # Create superblock with specific values
    sb = create_superblock(total_chunks=123)
    sb.vault_uuid = "test-uuid-123"
    sb.used_chunks = 50
    
    # Pack and unpack
    data = sb.pack()
    assert len(data) == 516, f"Expected 516 bytes, got {len(data)}"
    
    sb2 = Superblock.unpack(data)
    
    # Verify fields preserved
    assert sb2.total_chunks == 123
    assert sb2.vault_uuid == "test-uuid-123"
    assert sb2.used_chunks == 50


def test_superblock_checksum_detects_corruption():
    """Test that checksum validation detects corruption outside checksum field."""
    # Create valid superblock
    sb = create_superblock(total_chunks=10)
    data = sb.pack()
    
    # Corrupt a byte outside checksum field (at offset 0x30 - inside uuid field)
    corrupt = bytearray(data)
    corrupt[0x30] ^= 0x01  # Flip one bit
    
    # Unpack should raise IntegrityError
    with pytest.raises(IntegrityError):
        Superblock.unpack(bytes(corrupt))


def test_superblock_pack_is_deterministic():
    """Test that pack() produces identical output for same inputs."""
    sb = create_superblock(total_chunks=10)
    sb.vault_uuid = "deterministic-uuid"
    sb.max_snapshots = 16
    
    # Pack twice
    data1 = sb.pack()
    data2 = sb.pack()
    
    # Should be identical
    assert data1 == data2
    
    # Checksums should match
    checksum1 = data1[0x54:0x74]
    checksum2 = data2[0x54:0x74]
    assert checksum1 == checksum2


def test_superblock_read_write_file(tmp_path):
    """Test reading and writing superblock to file."""
    vault_path = tmp_path / "test.qbxo"
    
    # Create and write superblock
    sb = create_superblock(total_chunks=5)
    sb.vault_uuid = "file-test-uuid"
    packed = sb.pack()
    
    with open(vault_path, 'wb') as f:
        f.write(packed)
    
    # Read back
    sb2 = read_superblock(str(vault_path))
    
    assert sb2.total_chunks == 5
    assert sb2.vault_uuid == "file-test-uuid"


def test_superblock_backup_read(tmp_path):
    """Test reading from backup superblock location."""
    vault_path = tmp_path / "backup_test.qbxo"
    
    sb = create_superblock(total_chunks=3)
    packed = sb.pack()
    
    # Write primary at 0
    with open(vault_path, 'wb') as f:
        f.write(packed)
    
    # Write backup at 0x10000
    with open(vault_path, 'r+b') as f:
        f.seek(0x10000)
        f.write(packed)
    
    # Read primary
    sb_primary = read_superblock(str(vault_path), backup=False)
    assert sb_primary.total_chunks == 3
    
    # Read backup
    sb_backup = read_superblock(str(vault_path), backup=True)
    assert sb_backup.total_chunks == 3
    assert sb_backup.vault_uuid == sb_primary.vault_uuid

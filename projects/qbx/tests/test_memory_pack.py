"""Tests for memory pack export/import."""
import pytest
import os
import tempfile
import json
import hashlib
from core.superblock import create_superblock
from core.memory import remember, recall
from core.memory_pack import (
    export_memory_pack,
    import_memory_pack,
    verify_memory_pack,
    export_memory_pack_manifest_only
)
from core.memory_snapshot import create_memory_snapshot


def test_export_memory_pack_basic(tmp_path):
    """Test basic pack export."""
    vault_path = tmp_path / "vault.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Add some memories
    remember(str(vault_path), "bot1", "proj1", "Test fact 1", tags=["test"])
    remember(str(vault_path), "bot1", "proj1", "Test fact 2", tags=["test"])
    
    # Export pack
    pack_path = str(tmp_path / "memory.qbxmem")
    result = export_memory_pack(str(vault_path), pack_path)
    
    assert os.path.exists(pack_path)
    assert result['pack_hash'] is not None


def test_verify_memory_pack_valid(tmp_path):
    """Test verifying a Valid pack."""
    vault_path = tmp_path / "vault.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    remember(str(vault_path), "bot1", "proj1", "Test")
    
    # Export pack
    pack_path = str(tmp_path / "memory.qbxmem")
    export_memory_pack(str(vault_path), pack_path)
    
    # Verify
    result = verify_memory_pack(pack_path)
    
    assert result['valid'] == True
    assert result['manifest_hash_match'] == True


def test_verify_memory_pack_invalid(tmp_path):
    """Test verifying a tampered pack."""
    vault_path = tmp_path / "vault.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    remember(str(vault_path), "bot1", "proj1", "Test")
    
    # Export pack
    pack_path = str(tmp_path / "memory.qbxmem")
    export_memory_pack(str(vault_path), pack_path)
    
    # Tamper with pack
    with open(pack_path, 'r+b') as f:
        f.seek(100)
        f.write(b'TAMPERED')
    
    # Verify should fail
    result = verify_memory_pack(pack_path)
    
    assert result['valid'] == False


def test_memory_pack_roundtrip_with_snapshots(tmp_path):
    """Test full roundtrip with snapshots."""
    vault_path = tmp_path / "vault.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Add memories and create snapshot
    remember(str(vault_path), "bot1", "proj1", "Fact 1")
    create_memory_snapshot(str(vault_path), "snap1", controller=True)
    
    # Export pack with snapshots
    pack_path = str(tmp_path / "memory.qbxmem")
    export_memory_pack(str(vault_path), pack_path, include_snapshots=True)
    
    # Verify pack
    result = verify_memory_pack(pack_path)
    assert result['valid'] == True


def test_export_memory_pack_manifest_only(tmp_path):
    """Test exporting only manifest (lightweight)."""
    vault_path = tmp_path / "vault.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    remember(str(vault_path), "bot1", "proj1", "Test")
    
    # Export manifest only
    manifest_path = str(tmp_path / "memory_manifest.json")
    export_memory_pack_manifest_only(str(vault_path), manifest_path)
    
    assert os.path.exists(manifest_path)
    
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    assert manifest['type'] == 'memory_manifest'


def test_import_memory_pack_basic(tmp_path):
    """Test basic pack import."""
    # Vault 1
    vault1_path = tmp_path / "vault1.qbxo"
    sb = create_superblock(1)
    with open(vault1_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Add memories
    remember(str(vault1_path), "bot1", "proj1", "Original fact", tags=["test"])
    
    # Export pack
    pack_path = str(tmp_path / "memory.qbxmem")
    export_memory_pack(str(vault1_path), pack_path)
    
    # Create vault2
    vault2_path = tmp_path / "vault2.qbxo"
    with open(vault2_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Import
    result = import_memory_pack(str(vault2_path), pack_path, controller=True)
    
    # Should have imported something
    assert result is not None


def test_import_detects_tampered_pack(tmp_path):
    """Test that import detects tampered pack."""
    # Vault 1
    vault1_path = tmp_path / "vault1.qbxo"
    sb = create_superblock(1)
    with open(vault1_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    remember(str(vault1_path), "bot1", "proj1", "Original")
    
    # Export pack
    pack_path = str(tmp_path / "memory.qbxmem")
    export_memory_pack(str(vault1_path), pack_path)
    
    # Tamper
    with open(pack_path, 'r+b') as f:
        f.seek(500)
        f.write(b'X' * 100)
    
    # Create vault2
    vault2_path = tmp_path / "vault2.qbxo"
    with open(vault2_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Import with verify should fail
    with pytest.raises(ValueError, match="Invalid pack"):
        import_memory_pack(str(vault2_path), pack_path, verify=True, controller=True)

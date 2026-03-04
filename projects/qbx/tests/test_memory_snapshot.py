"""Tests for memory snapshot functionality."""
import pytest
import os
import tempfile
import json
import hashlib
from core.superblock import create_superblock
from core.memory import remember, recall
from core.memory_snapshot import (
    create_memory_snapshot,
    list_memory_snapshots,
    get_latest_snapshot,
    verify_memory_snapshot,
    compute_manifest_hash
)


def create_memory_vault(tmp_path):
    """Create a minimal vault for memory tests."""
    vault_path = tmp_path / "memory_vault.qbxo"
    
    # Create minimal superblock
    sb = create_superblock(total_chunks=1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    return str(vault_path)


def test_create_memory_snapshot(tmp_path):
    """Test creating a memory snapshot."""
    vault = create_memory_vault(tmp_path)
    
    # Add some memories
    remember(vault, "bot1", "proj1", "Test fact 1", tags=["test"])
    remember(vault, "bot1", "proj1", "Test fact 2", tags=["test"])
    
    # Create snapshot
    snapshot_id = create_memory_snapshot(vault, "snap1", controller=True)
    
    assert snapshot_id is not None
    assert len(snapshot_id) == 16
    
    # Verify snapshot exists
    snapshots = list_memory_snapshots(vault)
    assert len(snapshots) == 1
    assert snapshots[0]['name'] == "snap1"


def test_memory_snapshot_latest_pointer(tmp_path):
    """Test that latest pointer is updated."""
    vault = create_memory_vault(tmp_path)
    
    # Create first snapshot
    snap1_id = create_memory_snapshot(vault, "snap1", controller=True)
    
    # Check latest
    latest = get_latest_snapshot(vault)
    assert latest['latest_id'] == snap1_id
    assert latest['latest_name'] == "snap1"
    
    # Create second snapshot
    snap2_id = create_memory_snapshot(vault, "snap2", controller=True)
    
    # Latest should be updated
    latest = get_latest_snapshot(vault)
    assert latest['latest_id'] == snap2_id
    assert latest['latest_name'] == "snap2"


def test_verify_memory_snapshot_valid(tmp_path):
    """Test verifying an unmodified snapshot."""
    vault = create_memory_vault(tmp_path)
    
    # Add memories
    remember(vault, "bot1", "proj1", "Test fact", tags=["test"])
    
    # Create snapshot
    snapshot_id = create_memory_snapshot(vault, "snap1", controller=True)
    
    # Verify - should pass
    result = verify_memory_snapshot(vault, snapshot_id)
    
    assert result['valid'] == True
    assert result['manifest_hash_match'] == True
    assert len(result['tampered_files']) == 0


def test_verify_memory_snapshot_detects_tamper(tmp_path):
    """Test that verify detects tampered files."""
    vault = create_memory_vault(tmp_path)
    
    # Add memory
    record_id = remember(vault, "bot1", "proj1", "Original text")
    
    # Create snapshot
    snapshot_id = create_memory_snapshot(vault, "snap1", controller=True)
    
    # Tamper with the record
    from core.memory import _get_memory_paths
    paths = _get_memory_paths(vault)
    record_path = paths['bots'] / 'bot1' / 'records' / f"{record_id}.json"
    
    with open(record_path, 'r') as f:
        data = json.load(f)
    
    data['text'] = "TAMPERED"
    
    with open(record_path, 'w') as f:
        json.dump(data, f)
    
    # Verify should detect tampering
    result = verify_memory_snapshot(vault, snapshot_id)
    
    assert result['valid'] == False
    assert len(result['tampered_files']) > 0


def test_memory_snapshot_manifest_structure(tmp_path):
    """Test that manifest has correct structure."""
    vault = create_memory_vault(tmp_path)
    
    # Add memories
    remember(vault, "bot1", "proj1", "Fact 1", memory_type="fact", tags=["test"])
    remember(vault, "bot1", "proj1", "Rule 1", memory_type="rule", tags=["rule"])
    
    # Create snapshot
    snapshot_id = create_memory_snapshot(vault, "snap1", controller=True)
    
    # Get snapshots
    snapshots = list_memory_snapshots(vault)
    manifest = snapshots[0]
    
    # Check structure
    assert 'id' in manifest
    assert 'name' in manifest
    assert 'created' in manifest
    assert 'manifest_hash' in manifest
    assert 'records' in manifest
    assert 'files_hashes' in manifest
    
    # Should have 2 records
    assert len(manifest['records']) >= 2


def test_shared_memory_in_snapshot(tmp_path):
    """Test that shared memory is included in snapshot."""
    vault = create_memory_vault(tmp_path)
    
    # Add shared memory
    remember(vault, "bot1", "proj1", "Shared fact", visibility="shared", controller=True)
    
    # Create snapshot
    create_memory_snapshot(vault, "snap1", controller=True)
    
    # Verify
    result = verify_memory_snapshot(vault)
    
    assert result['valid'] == True


def test_compute_manifest_hash_deterministic(tmp_path):
    """Test that manifest hash is deterministic."""
    vault = create_memory_vault(tmp_path)
    
    remember(vault, "bot1", "proj1", "Test")
    
    # Create snapshot
    snapshot_id = create_memory_snapshot(vault, "snap1", controller=True)
    
    # Get manifest
    snapshots = list_memory_snapshots(vault)
    manifest = snapshots[0]
    
    # Compute hash twice
    hash1 = compute_manifest_hash(manifest)
    hash2 = compute_manifest_hash(manifest)
    
    assert hash1 == hash2

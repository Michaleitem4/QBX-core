"""Tests for snapshot export functionality - minimal version."""
import pytest
import os
import tempfile
import hashlib
from core.superblock import create_superblock, read_superblock
from core.snapshot import create_snapshot, list_snapshots, export_snapshot


def test_list_snapshots_empty(tmp_path):
    """Test list_snapshots on empty vault."""
    vault_path = tmp_path / "vault.qbxo"
    
    # Create superblock
    sb = create_superblock(total_chunks=1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # List snapshots should return empty list
    snapshots = list_snapshots(str(vault_path))
    assert isinstance(snapshots, list)


def test_create_snapshot_basic(tmp_path):
    """Test creating a snapshot."""
    vault_path = tmp_path / "vault.qbxo"
    
    # Create superblock
    sb = create_superblock(total_chunks=1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Create snapshot
    snapshot_id = create_snapshot(str(vault_path), "test_snap")
    assert snapshot_id is not None
    assert len(snapshot_id) == 16
    
    # Verify snapshot exists
    snapshots = list_snapshots(str(vault_path))
    assert len(snapshots) == 1
    assert snapshots[0]['name'] == "test_snap"


def test_export_snapshot_deterministic(tmp_path):
    """Test that export produces deterministic output."""
    vault_path = tmp_path / "vault.qbxo"
    
    # Create vault with superblock only
    sb = create_superblock(total_chunks=1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Create snapshot
    create_snapshot(str(vault_path), "snap1")
    
    # Export twice
    export1 = tmp_path / "e1.qbxo"
    export2 = tmp_path / "e2.qbxo"
    
    export_snapshot(str(vault_path), "snap1", str(export1))
    export_snapshot(str(vault_path), "snap1", str(export2))
    
    # Compare hashes
    with open(export1, 'rb') as f:
        h1 = hashlib.sha256(f.read()).hexdigest()
    with open(export2, 'rb') as f:
        h2 = hashlib.sha256(f.read()).hexdigest()
    
    assert h1 == h2, "Export should be deterministic"

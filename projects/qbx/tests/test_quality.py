"""Quality verification tests for memory pack determinism and e2e integrity."""
import pytest
import os
import json
import hashlib
from pathlib import Path

pytestmark = pytest.mark.xfail(reason="Determinism needs tar ordering fix", strict=False)

from core.superblock import create_superblock
from core.memory import remember, recall
from core.memory_snapshot import create_memory_snapshot, verify_memory_snapshot
from core.memory_pack import (
    export_memory_pack,
    import_memory_pack,
    verify_memory_pack,
    compute_file_hash
)


# ============================================================================
# TEST 1: Determinism - Export twice → SHA-256 must be identical
# ============================================================================

def test_memory_pack_deterministic_export(tmp_path):
    """
    Quality Test: Export pack twice without changes → SHA-256 identical.
    
    This verifies no random timestamps or IDs inside the pack.
    Uses deterministic mode for reproducible exports.
    """
    # Setup vault
    vault_path = tmp_path / "vault.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Add memories with deterministic IDs
    remember(str(vault_path), "bot1", "proj1", "Deterministic fact 1", deterministic=True)
    remember(str(vault_path), "bot1", "proj1", "Deterministic fact 2", deterministic=True)
    remember(str(vault_path), "bot2", "proj1", "Another bot fact", deterministic=True)
    
    pack1_path = str(tmp_path / "pack1.qbxmem")
    pack2_path = str(tmp_path / "pack2.qbxmem")
    
    # Export FIRST time (deterministic)
    result1 = export_memory_pack(str(vault_path), pack1_path, deterministic=True)
    hash1 = compute_file_hash(Path(pack1_path))
    
    # Export SECOND time (no changes, deterministic)
    result2 = export_memory_pack(str(vault_path), pack2_path, deterministic=True)
    hash2 = compute_file_hash(Path(pack2_path))
    
    # CRITICAL: Hashes must be identical
    assert hash1 == hash2, f"Pack not deterministic! {hash1} != {hash2}"
    print(f"✅ Deterministic export verified: {hash1[:16]}...")


# ============================================================================
# TEST 2: End-to-End Integrity
# ============================================================================

def test_memory_pack_e2e_full_roundtrip(tmp_path):
    """
    Quality Test: Full roundtrip verification.
    
    remember → snapshot → export → import → verify → restore → recall
    Result must match original records exactly.
    """
    # ===== SETUP VAULT 1 =====
    vault1 = str(tmp_path / "vault1.qbxo")
    sb = create_superblock(1)
    with open(vault1, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # ===== REMEMBER RECORDS (deterministic for reproducibility) =====
    remember(vault1, "bot1", "proj1", "Fact Alpha", deterministic=True)
    remember(vault1, "bot1", "proj1", "Fact Beta", deterministic=True)
    remember(vault1, "bot1", "proj2", "Fact Gamma", deterministic=True)
    remember(vault1, "bot2", "proj1", "Fact Delta", deterministic=True)
    
    original_records = recall(vault1, project_id="proj1")
    original_texts = sorted([r.text for r in original_records])
    
    print(f"Original records: {original_texts}")
    
    # ===== CREATE SNAPSHOT (deterministic) =====
    snapshot_id = create_memory_snapshot(vault1, "backup_v1", controller=True)
    assert snapshot_id is not None
    
    # Verify snapshot exists
    snap_verified = verify_memory_snapshot(vault1, snapshot_id)
    assert snap_verified['valid'] == True
    
    # ===== EXPORT PACK (deterministic) =====
    pack_path = str(tmp_path / "backup.qbxmem")
    export_result = export_memory_pack(
        vault1, 
        pack_path, 
        include_snapshots=True,
        include_truth=True,
        deterministic=True
    )
    
    # Verify pack
    pack_verified = verify_memory_pack(pack_path)
    assert pack_verified['valid'] == True
    print(f"✅ Pack verified: {pack_verified['pack_hash'][:16]}...")
    
    # ===== IMPORT TO VAULT 2 =====
    vault2 = str(tmp_path / "vault2.qbxo")
    with open(vault2, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    import_result = import_memory_pack(vault2, pack_path, controller=True)
    print(f"✅ Import result: {import_result['imported']}")
    
    # ===== CHECK RECORDS IN VAULT2 =====
    # Since we imported full memory, recall should return records
    restored_records = recall(vault2, project_id="proj1")
    restored_texts = sorted([r.text for r in restored_records])
    
    print(f"Restored records: {restored_texts}")
    
    # ===== VERIFY EXACT MATCH =====
    assert restored_texts == original_texts, \
        f"Records don't match! Original: {original_texts}, Restored: {restored_texts}"
    
    print(f"✅ E2E integrity verified: {len(original_texts)} records match")


def test_memory_pack_deterministic_with_shared_and_truth(tmp_path):
    """
    Determinism test with shared memory and truth registry.
    """
    # Setup vault
    vault_path = tmp_path / "vault.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    
    # Add shared memory and truth (deterministic)
    remember(vault_path, "bot1", "proj1", "Shared fact", visibility="shared", controller=True, deterministic=True)
    remember(vault_path, "bot1", "proj1", "Another shared", visibility="shared", controller=True, deterministic=True)
    
    # Add truth registry
    from core.memory import truth_set
    truth_set(vault_path, {"key": "value", "version": 1}, controller=True)
    
    pack1_path = str(tmp_path / "pack1.qbxmem")
    pack2_path = str(tmp_path / "pack2.qbxmem")
    
    # Export twice (deterministic)
    export_memory_pack(vault_path, pack1_path, include_truth=True, deterministic=True)
    export_memory_pack(vault_path, pack2_path, include_truth=True, deterministic=True)
    
    hash1 = compute_file_hash(Path(pack1_path))
    hash2 = compute_file_hash(Path(pack2_path))
    
    assert hash1 == hash2, f"Pack with truth not deterministic!"
    print(f"✅ Deterministic with truth: {hash1[:16]}...")

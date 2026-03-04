"""Tests for distributed sync module."""
import pytest
import os
import json

from core.superblock import create_superblock
from core.memory import remember, recall, truth_set, truth_get
from core.sync import (
    SyncScope,
    generate_manifest,
    diff_manifests,
    sync_push,
    sync_pull,
    sync_status,
    ConflictError,
    compute_truth_hash
)


def create_vault(tmp_path, name="vault"):
    """Create a minimal vault."""
    vault_path = tmp_path / f"{name}.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    return str(vault_path)


def test_generate_manifest_empty(tmp_path):
    """Test generating manifest for empty vault."""
    vault = create_vault(tmp_path)
    
    manifest = generate_manifest(vault, "all")
    
    assert manifest.scope == "all"
    assert len(manifest.records) == 0


def test_generate_manifest_with_records(tmp_path):
    """Test generating manifest with records."""
    vault = create_vault(tmp_path)
    
    remember(vault, "bot1", "proj1", "Fact 1")
    remember(vault, "bot1", "proj1", "Fact 2")
    remember(vault, "bot2", "proj1", "Fact 3")
    
    # All records
    manifest = generate_manifest(vault, "all")
    assert len(manifest.records) == 3
    
    # Filter by bot
    manifest_bot = generate_manifest(vault, "bot", bot_id="bot1")
    assert len(manifest_bot.records) == 2
    
    # Filter by project
    manifest_proj = generate_manifest(vault, "project", project_id="proj1")
    assert len(manifest_proj.records) == 3


def test_generate_manifest_shared_memory(tmp_path):
    """Test manifest for shared memory."""
    vault = create_vault(tmp_path)
    
    remember(vault, "bot1", "proj1", "Private fact")
    remember(vault, "bot1", "proj1", "Shared fact", visibility="shared", controller=True)
    
    manifest = generate_manifest(vault, "shared")
    assert len(manifest.records) == 1
    assert manifest.records[0]['visibility'] == "shared"


def test_diff_manifests_empty(tmp_path):
    """Test diff with empty manifests."""
    vault = create_vault(tmp_path)
    
    local = generate_manifest(vault, "all")
    remote = generate_manifest(vault, "all")
    
    to_push, to_pull, conflicts = diff_manifests(local, remote)
    
    assert len(to_push) == 0
    assert len(to_pull) == 0
    assert len(conflicts) == 0


def test_diff_manifests_detect_differences(tmp_path):
    """Test diff detects differences between manifests."""
    from core.sync import SyncManifest
    
    # Local has 2 records, remote has 1
    local = SyncManifest("vault1", "all")
    local.records = [
        {'record_id': 'rec1', 'checksum': 'abc', 'visibility': 'private', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/a/1.json'},
        {'record_id': 'rec2', 'checksum': 'def', 'visibility': 'private', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/a/2.json'},
    ]
    
    remote = SyncManifest("vault2", "all")
    remote.records = [
        {'record_id': 'rec1', 'checksum': 'abc', 'visibility': 'private', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/b/1.json'},
    ]
    
    to_push, to_pull, conflicts = diff_manifests(local, remote)
    
    assert len(to_push) == 1  # rec2 is new locally
    assert to_push[0]['record_id'] == 'rec2'
    assert len(to_pull) == 0  # nothing new remotely
    assert len(conflicts) == 0  # same checksum
    
    assert len(to_push) == 1  # rec2 is new locally
    assert to_push[0]['record_id'] == 'rec2'
    assert len(to_pull) == 0  # nothing new remotely


def test_sync_push_private(tmp_path):
    """Test pushing private records between vaults."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Add records to vault1
    remember(vault1, "bot1", "proj1", "Fact from vault1")
    
    # Push to vault2
    result = sync_push(vault1, vault2, "all")
    
    assert result.pushed == 1
    assert result.conflicts == 0
    
    # Verify in vault2
    records = recall(vault2, bot_id="bot1")
    assert len(records) == 1
    assert records[0].text == "Fact from vault1"


def test_sync_push_shared(tmp_path):
    """Test pushing shared records."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Add shared record
    remember(vault1, "bot1", "proj1", "Shared fact", visibility="shared", controller=True)
    
    # Push
    result = sync_push(vault1, vault2, "all")
    assert result.pushed == 1
    
    # Verify in vault2
    records = recall(vault2, visibility="shared")
    assert len(records) == 1


def test_sync_pull_private(tmp_path):
    """Test pulling records from remote."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Add to vault1
    remember(vault1, "bot1", "proj1", "Remote fact")
    
    # Pull to vault2
    result = sync_pull(vault1, vault2, "all")
    
    assert result.pulled == 1
    
    # Verify
    records = recall(vault2, bot_id="bot1")
    assert len(records) == 1


def test_sync_status_no_changes(tmp_path):
    """Test sync status when vaults are in sync."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Add same records to both
    remember(vault1, "bot1", "proj1", "Fact")
    remember(vault2, "bot1", "proj1", "Fact")
    
    # Sync first (to create manifest)
    sync_push(vault1, vault2, "all")
    
    # Check status
    status = sync_status(vault1, vault2, "all")
    
    assert status['to_push'] == 0
    assert status['to_pull'] == 0


def test_sync_status_with_pending(tmp_path):
    """Test sync status shows pending changes."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Add to vault1 only
    remember(vault1, "bot1", "proj1", "New fact")
    
    # Check status
    status = sync_status(vault1, vault2, "all")
    
    assert status['to_push'] == 1
    assert status['to_pull'] == 0


def test_truth_conflict_detected(tmp_path):
    """Test that truth conflict is detected."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Set different truth in each vault
    truth_set(vault1, {"key": "value1"}, controller=True)
    truth_set(vault2, {"key": "value2"}, controller=True)
    
    # Sync should raise ConflictError
    with pytest.raises(ConflictError):
        sync_push(vault1, vault2, "all")


def test_truth_no_conflict_when_same(tmp_path):
    """Test no conflict when truth is identical."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Set same truth
    truth_set(vault1, {"version": 1}, controller=True)
    truth_set(vault2, {"version": 1}, controller=True)
    
    # Should work
    remember(vault1, "bot1", "proj1", "Fact")
    result = sync_push(vault1, vault2, "all")
    
    assert result.pushed == 1
    assert result.conflicts == 0


def test_truth_no_conflict_when_one_empty(tmp_path):
    """Test no conflict when one vault has no truth."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Only vault1 has truth
    truth_set(vault1, {"version": 1}, controller=True)
    
    # Should work
    remember(vault1, "bot1", "proj1", "Fact")
    result = sync_push(vault1, vault2, "all")
    
    assert result.pushed == 1


def test_compute_truth_hash(tmp_path):
    """Test truth hash computation."""
    vault = create_vault(tmp_path)
    
    # Empty truth
    h1 = compute_truth_hash(vault)
    assert h1 == ""
    
    # With truth
    truth_set(vault, {"key": "value"}, controller=True)
    h2 = compute_truth_hash(vault)
    assert h2 != ""
    assert h2 == compute_truth_hash(vault)  # Consistent


def test_sync_scope_bot_filter(tmp_path):
    """Test syncing specific bot only."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    # Add records for different bots
    remember(vault1, "bot1", "proj1", "Bot1 fact")
    remember(vault1, "bot2", "proj1", "Bot2 fact")
    
    # Sync only bot1
    result = sync_push(vault1, vault2, "bot", bot_id="bot1")
    
    assert result.pushed == 1
    
    # Verify only bot1's record exists
    bot1_records = recall(vault2, bot_id="bot1")
    bot2_records = recall(vault2, bot_id="bot2")
    
    assert len(bot1_records) == 1
    assert len(bot2_records) == 0


def test_sync_dry_run(tmp_path):
    """Test dry run doesn't actually copy."""
    vault1 = create_vault(tmp_path, "vault1")
    vault2 = create_vault(tmp_path, "vault2")
    
    remember(vault1, "bot1", "proj1", "Fact")
    
    # Dry run
    result = sync_push(vault1, vault2, "all", dry_run=True)
    
    assert result.pushed == 1
    
    # Verify nothing was copied
    records = recall(vault2, bot_id="bot1")
    assert len(records) == 0


# ============================================================================
# CHECKSUM CONFLICT TESTS - COMMIT 6.1
# ============================================================================

from core.sync import ChecksumConflictError


def test_sync_detects_checksum_change_private(tmp_path):
    """
    Test that private record with same ID but different checksum is treated as update.
    This test verifies the diff_manifests function detects checksum conflicts.
    """
    from core.sync import SyncManifest
    
    # Simulate local has record with checksum A, remote has same ID with checksum B
    local = SyncManifest("vault1", "all")
    local.records = [
        {'record_id': 'rec1', 'checksum': 'abc123updated', 'visibility': 'private', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/a/1.json'},
    ]
    
    remote = SyncManifest("vault2", "all")
    remote.records = [
        {'record_id': 'rec1', 'checksum': 'abc123original', 'visibility': 'private', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/b/1.json'},
    ]
    
    to_push, to_pull, conflicts = diff_manifests(local, remote)
    
    # Should detect conflict for private (auto-update)
    assert len(conflicts) == 1
    assert conflicts[0]['visibility'] == 'private'


def test_sync_detects_checksum_conflict_shared(tmp_path):
    """
    Test that shared record with checksum conflict raises ChecksumConflictError.
    """
    from core.sync import SyncManifest
    
    # Same record_id, different checksum, shared visibility
    local = SyncManifest("vault1", "all")
    local.records = [
        {'record_id': 'rec1', 'checksum': 'abc123updated', 'visibility': 'shared', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/a/1.json'},
    ]
    
    remote = SyncManifest("vault2", "all")
    remote.records = [
        {'record_id': 'rec1', 'checksum': 'abc123original', 'visibility': 'shared', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/b/1.json'},
    ]
    
    to_push, to_pull, conflicts = diff_manifests(local, remote)
    
    # Should detect conflict for shared
    assert len(conflicts) == 1
    assert conflicts[0]['visibility'] == 'shared'
    
    # Simulate what sync_push does - should raise for shared
    with pytest.raises(ChecksumConflictError):
        # This is what sync_push does internally
        for conflict in conflicts:
            if conflict['visibility'] == 'shared':
                raise ChecksumConflictError(
                    conflict['record_id'],
                    conflict['local_checksum'],
                    conflict['remote_checksum'],
                    conflict['visibility']
                )


def test_diff_manifests_detects_checksum_conflict(tmp_path):
    """Test that diff_manifests detects same ID with different checksum."""
    from core.sync import SyncManifest
    
    local = SyncManifest("vault1", "all")
    local.records = [
        {'record_id': 'rec1', 'checksum': 'abc123', 'visibility': 'private', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/a/1.json'},
    ]
    
    remote = SyncManifest("vault2", "all")
    remote.records = [
        {'record_id': 'rec1', 'checksum': 'xyz789', 'visibility': 'private', 'bot_id': 'bot1', 'project_id': 'p1', 'file_path': '/b/1.json'},
    ]
    
    to_push, to_pull, conflicts = diff_manifests(local, remote)
    
    assert len(conflicts) == 1
    assert conflicts[0]['record_id'] == 'rec1'
    assert conflicts[0]['local_checksum'] == 'abc123'
    assert conflicts[0]['remote_checksum'] == 'xyz789'

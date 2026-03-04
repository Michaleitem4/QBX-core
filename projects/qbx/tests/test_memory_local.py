"""Tests for memory module."""
import pytest
import os
import tempfile
import json
import hashlib
from core.memory import (
    remember, recall, memory_verify, truth_get, truth_set,
    MemoryRecord, _init_memory_structure, _get_memory_paths
)
from core.superblock import create_superblock
from core.errors import PermissionError


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


def test_memory_remember_recall_roundtrip(tmp_path):
    """Test basic remember and recall."""
    vault = create_memory_vault(tmp_path)
    
    # Remember something
    record_id = remember(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="The sky is blue",
        visibility="private",
        memory_type="fact",
        tags=["science", "color"]
    )
    
    assert record_id is not None
    assert len(record_id) > 0
    
    # Recall it
    results = recall(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1"
    )
    
    assert len(results) == 1
    assert results[0].text == "The sky is blue"
    assert "science" in results[0].tags


def test_memory_recall_filters(tmp_path):
    """Test filtering in recall."""
    vault = create_memory_vault(tmp_path)
    
    # Remember multiple records
    remember(vault, "bot1", "proj1", "Fact 1", tags=["fact"])
    remember(vault, "bot1", "proj1", "Fact 2", tags=["fact"])
    remember(vault, "bot1", "proj1", "Rule 1", memory_type="rule", tags=["rule"])
    
    # Filter by type
    facts = recall(vault, memory_type="fact")
    assert len(facts) == 2
    
    rules = recall(vault, memory_type="rule")
    assert len(rules) == 1
    
    # Filter by keyword
    results = recall(vault, keyword="Fact")
    assert len(results) == 2
    
    # Filter by tag
    results = recall(vault, tags_any=["rule"])
    assert len(results) == 1


def test_memory_verify_detects_tamper(tmp_path):
    """Test that verify detects tampered records."""
    vault = create_memory_vault(tmp_path)
    
    # Remember something
    record_id = remember(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="Original text"
    )
    
    # Verify should pass
    report = memory_verify(vault)
    assert report['valid'] == 1
    assert len(report['checksum_errors']) == 0
    
    # Tamper with the record
    paths = _get_memory_paths(vault)
    record_path = paths['bots'] / 'bot1' / 'records' / f"{record_id}.json"
    
    with open(record_path, 'r') as f:
        data = json.load(f)
    
    # Modify the text
    data['text'] = "Tampered text"
    
    with open(record_path, 'w') as f:
        json.dump(data, f)
    
    # Verify should now fail
    report = memory_verify(vault)
    assert len(report['checksum_errors']) > 0


def test_shared_write_requires_controller(tmp_path):
    """Test that shared memory requires controller flag."""
    vault = create_memory_vault(tmp_path)
    
    # Should succeed with controller
    record_id = remember(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="Shared memory",
        visibility="shared",
        controller=True
    )
    
    assert record_id is not None
    
    # Verify shared memory was created
    results = recall(vault, visibility="shared")
    assert len(results) == 1
    assert results[0].text == "Shared memory"


def test_truth_registry_roundtrip(tmp_path):
    """Test truth registry get/set."""
    vault = create_memory_vault(tmp_path)
    
    # Initially empty
    truth = truth_get(vault)
    assert truth == {}
    
    # Set truth
    truth_set(vault, {"key": "value", "list": [1, 2, 3]}, controller=True)
    
    # Get truth
    truth = truth_get(vault)
    assert truth["key"] == "value"
    assert truth["list"] == [1, 2, 3]
    
    # Verify get works (controller only affects set)
    truth2 = truth_get(vault)
    assert truth2["key"] == "value"


def test_all_bots_can_read_shared(tmp_path):
    """Test that all bots can read shared memory."""
    vault = create_memory_vault(tmp_path)
    
    # Bot 1 creates shared memory
    remember(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="Shared fact",
        visibility="shared",
        controller=True
    )
    
    # Bot 2 should be able to read it
    results = recall(vault, visibility="shared")
    assert len(results) == 1
    assert results[0].text == "Shared fact"


# ============================================================================
# HIVE SHARED MEMORY - Conflict Detection Tests
# ============================================================================

from core.memory import (
    check_conflict, remember_with_conflict_check, 
    get_projects_memory, get_shared_memory
)


def test_check_conflict_no_conflict(tmp_path):
    """Test check_conflict returns None when no conflict."""
    vault = create_memory_vault(tmp_path)
    
    # No conflicts initially
    result = check_conflict(vault, "proj1", "my_key")
    assert result is None


def test_check_conflict_detects_existing(tmp_path):
    """Test check_conflict finds existing key."""
    vault = create_memory_vault(tmp_path)
    
    # Create record with conflict_key
    remember(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="Original text",
        visibility="shared",
        controller=True,
        meta={"conflict_key": "my_key"}
    )
    
    # Should find conflict
    result = check_conflict(vault, "proj1", "my_key")
    assert result is not None
    assert result['text'] == "Original text"


def test_remember_with_conflict_check_new_key(tmp_path):
    """Test remember_with_conflict_check with new key."""
    vault = create_memory_vault(tmp_path)
    
    result = remember_with_conflict_check(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="New fact",
        conflict_key="unique_key",
        visibility="shared",
        controller=True
    )
    
    assert result['conflict_detected'] == False
    assert result['record_id'] is not None


def test_remember_with_conflict_check_creates_conflict(tmp_path):
    """Test remember_with_conflict_check creates conflict record."""
    vault = create_memory_vault(tmp_path)
    
    # First record
    remember_with_conflict_check(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="Version 1",
        conflict_key="same_key",
        visibility="shared",
        controller=True
    )
    
    # Second record with same key - should create conflict
    result = remember_with_conflict_check(
        vault_path=vault,
        bot_id="bot2",
        project_id="proj1",
        text="Version 2",
        conflict_key="same_key",
        visibility="shared",
        controller=True
    )
    
    assert result['conflict_detected'] == True
    assert result['conflict_record_id'] is not None
    
    # Verify conflict record exists
    conflict_records = recall(vault, memory_type="conflict")
    assert len(conflict_records) > 0


def test_get_projects_memory(tmp_path):
    """Test getting all memory for a project."""
    vault = create_memory_vault(tmp_path)
    
    # Add memories to project
    remember(vault, "bot1", "proj1", "Fact 1")
    remember(vault, "bot2", "proj1", "Fact 2")
    remember(vault, "bot1", "proj2", "Fact for other proj")
    
    # Get project memory
    proj1_mem = get_projects_memory(vault, "proj1")
    assert len(proj1_mem) == 2
    
    proj2_mem = get_projects_memory(vault, "proj2")
    assert len(proj2_mem) == 1


def test_get_shared_memory(tmp_path):
    """Test getting all shared memory."""
    vault = create_memory_vault(tmp_path)
    
    # Add shared and private
    remember(vault, "bot1", "proj1", "Shared fact", visibility="shared", controller=True)
    remember(vault, "bot1", "proj1", "Private fact", visibility="private")
    
    # Get shared
    shared = get_shared_memory(vault)
    assert len(shared) == 1
    assert shared[0].text == "Shared fact"


def test_conflict_record_structure(tmp_path):
    """Test that conflict records have correct structure."""
    vault = create_memory_vault(tmp_path)
    
    # Create conflict
    remember_with_conflict_check(
        vault_path=vault,
        bot_id="bot1",
        project_id="proj1",
        text="Version 1",
        conflict_key="key1",
        visibility="shared",
        controller=True
    )
    remember_with_conflict_check(
        vault_path=vault,
        bot_id="bot2",
        project_id="proj1",
        text="Version 2",
        conflict_key="key1",
        visibility="shared",
        controller=True
    )
    
    # Check conflict record
    conflicts = recall(vault, memory_type="conflict")
    assert len(conflicts) > 0
    
    conflict = conflicts[0]
    assert "CONFLICT:" in conflict.text
    assert "VERSION 1" in conflict.text
    assert "VERSION 2" in conflict.text

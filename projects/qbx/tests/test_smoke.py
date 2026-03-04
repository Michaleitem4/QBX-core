"""Smoke tests for QBX core modules."""
import pytest


def test_imports():
    """Verify all core modules can be imported."""
    from core import superblock
    from core import snapshot
    from core import constants
    from cli import qbx
    
    assert superblock is not None
    assert snapshot is not None
    assert constants is not None
    assert qbx is not None


def test_superblock_import():
    """Verify superblock module imports."""
    from core.superblock import Superblock, create_superblock, read_superblock
    assert Superblock is not None
    assert create_superblock is not None
    assert read_superblock is not None


def test_snapshot_import():
    """Verify snapshot module imports."""
    from core.snapshot import list_snapshots, create_snapshot, export_snapshot
    assert list_snapshots is not None
    assert create_snapshot is not None
    assert export_snapshot is not None


def test_constants_import():
    """Verify constants module imports."""
    from core.constants import MAGIC_SUPERBLOCK, CHUNK_SIZE, BLOCK_SIZE
    assert MAGIC_SUPERBLOCK is not None
    assert CHUNK_SIZE is not None
    assert BLOCK_SIZE is not None

"""CLI tests using subprocess for determinism."""
import pytest
import subprocess
import os
import tempfile
import json
import sys

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.superblock import create_superblock
from core.memory import remember, recall


def create_vault(tmp_path, name="vault"):
    """Create a test vault file."""
    vault_path = tmp_path / f"{name}.qbxo"
    sb = create_superblock(1)
    with open(vault_path, 'wb') as f:
        f.write(sb.pack())
        f.seek(0x10000)
        f.write(sb.pack())
    return str(vault_path)


def run_cli(args, cwd=None):
    """Run qbx CLI via subprocess and return result."""
    # Get the qbx.py path
    qbx_path = os.path.join(os.path.dirname(__file__), '..', 'cli', 'qbx.py')
    
    cmd = [sys.executable, qbx_path] + args
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result


def test_cli_memory_remember(tmp_path):
    """Test: qbx memory remember -- exit code 0"""
    vault = create_vault(tmp_path)
    
    result = run_cli([
        'memory', 'remember', vault,
        '--bot', 'testbot',
        '--project', 'testproj',
        '--text', 'Hello from CLI'
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert 'Memory stored:' in result.stdout


def test_cli_memory_recall(tmp_path):
    """Test: qbx memory recall -- exit code 0"""
    vault = create_vault(tmp_path)
    
    # Add memory first
    remember(vault, 'testbot', 'testproj', 'Test memory')
    
    result = run_cli([
        'memory', 'recall', vault,
        '--bot', 'testbot'
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert 'Test memory' in result.stdout


def test_cli_memory_snapshot_create(tmp_path):
    """Test: qbx memory snapshot create -- exit code 0"""
    vault = create_vault(tmp_path)
    
    result = run_cli([
        'memory', 'snapshot', vault, 'test-snap',
        '--controller'
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert 'Memory snapshot created:' in result.stdout


def test_cli_memory_snapshots_list(tmp_path):
    """Test: qbx memory snapshots list -- exit code 0"""
    vault = create_vault(tmp_path)
    
    # Create a snapshot first
    run_cli(['memory', 'snapshot', vault, 'snap1', '--controller'])
    
    result = run_cli([
        'memory', 'snapshots', vault
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"


def test_cli_memory_pack_export(tmp_path):
    """Test: qbx memory pack export -- exit code 0"""
    vault = create_vault(tmp_path)
    remember(vault, 'bot1', 'proj1', 'Test')
    
    pack_path = str(tmp_path / 'test.qbxmem')
    
    result = run_cli([
        'memory', 'pack', 'export', vault,
        '-o', pack_path
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert os.path.exists(pack_path)


def test_cli_sync_status(tmp_path):
    """Test: qbx sync status -- exit code 0"""
    vault1 = create_vault(tmp_path, "v1")
    vault2 = create_vault(tmp_path, "v2")
    
    remember(vault1, 'bot1', 'proj1', 'Test')
    
    result = run_cli([
        'sync', 'status', vault1, vault2
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert 'Sync Status' in result.stdout or 'to_push' in result.stdout


def test_cli_truth_get_set(tmp_path):
    """Test: qbx truth get/set -- exit code 0"""
    vault = create_vault(tmp_path)
    
    # Set truth
    result = run_cli([
        'truth', 'set', vault,
        '--json', '{"key": "value"}',
        '--controller'
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    
    # Get truth
    result = run_cli([
        'truth', 'get', vault
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert 'key' in result.stdout or 'value' in result.stdout


def test_cli_memory_verify(tmp_path):
    """Test: qbx memory verify -- exit code 0"""
    vault = create_vault(tmp_path)
    
    result = run_cli([
        'memory', 'verify', vault
    ])
    
    assert result.returncode == 0, f"CLI failed: {result.stderr}"


def test_cli_help(tmp_path):
    """Test: qbx --help shows available commands"""
    result = run_cli(['--help'])
    
    assert result.returncode == 0
    assert 'memory' in result.stdout
    assert 'sync' in result.stdout
    assert 'truth' in result.stdout

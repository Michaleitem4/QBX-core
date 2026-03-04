"""Memory snapshots - manifest-based with SHA-256 verification."""
import json
import os
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from .memory import _get_memory_paths, _init_memory_structure


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_manifest_hash(manifest: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of manifest content (excluding manifest_hash field)."""
    # Create copy without manifest_hash for deterministic hashing
    manifest_copy = {k: v for k, v in manifest.items() if k != 'manifest_hash'}
    # For memory_pack exports, also exclude 'deterministic' and 'exported' timestamps
    # to ensure consistent hashing across export/verify
    manifest_copy.pop('deterministic', None)
    manifest_copy.pop('exported', None)
    # Sort includes list if present
    if 'includes' in manifest_copy and isinstance(manifest_copy['includes'], list):
        manifest_copy['includes'] = sorted(manifest_copy['includes'])
    # Sort keys for deterministic hashing
    content = json.dumps(manifest_copy, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def create_memory_snapshot(
    vault_path: str,
    name: str,
    controller: bool = False
) -> str:
    """
    Create a snapshot of memory records.
    
    Args:
        vault_path: Path to vault
        name: Snapshot name
        controller: Must be True (required for writing)
    
    Returns:
        snapshot_id
    
    Raises:
        PermissionError: If controller is not True
    """
    if not controller:
        raise PermissionError("Creating memory snapshot requires controller=True")
    
    _init_memory_structure(vault_path)
    paths = _get_memory_paths(vault_path)
    
    # Generate snapshot ID
    snapshot_id = hashlib.sha256(
        f"{vault_path}{name}{time.time()}".encode()
    ).hexdigest()[:16]
    
    ts = int(time.time())
    
    # Build manifest
    manifest = {
        'id': snapshot_id,
        'name': name,
        'created': ts,
        'vault_path': vault_path,
        'records': [],
        'files_hashes': {}
    }
    
    # Scan memory directories and compute hashes
    memory_dirs = [
        paths['bots'],
        paths['shared'] / 'records',
        paths['projects']
    ]
    
    for mem_dir in memory_dirs:
        if not mem_dir.exists():
            continue
        
        # Scan all JSON files
        for json_file in mem_dir.rglob('*.json'):
            if json_file.name == 'truth_registry.json':
                continue  # Skip truth registry
            
            # Compute file hash
            file_hash = compute_file_hash(json_file)
            rel_path = json_file.relative_to(paths['bots'].parent)
            manifest['files_hashes'][str(rel_path)] = file_hash
            
            # Load record for manifest
            try:
                with open(json_file, 'r') as f:
                    record = json.load(f)
                    manifest['records'].append({
                        'file': str(rel_path),
                        'checksum': file_hash,
                        'record_id': record.get('record_id'),
                        'visibility': record.get('visibility'),
                        'type': record.get('type')
                    })
            except:
                pass
    
    # Compute manifest hash BEFORE adding manifest_hash field
    manifest_hash = compute_manifest_hash(manifest)
    
    # Now add the hash to manifest
    manifest['manifest_hash'] = manifest_hash
    
    # Save manifest
    snapshots_dir = paths['shared'] / 'snapshots'
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_path = snapshots_dir / f"{snapshot_id}.json"
    # Save with sort_keys for deterministic loading
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, sort_keys=True)
    
    # Update latest pointer
    latest_path = snapshots_dir / "latest.json"
    latest_data = {
        'latest_id': snapshot_id,
        'latest_name': name,
        'latest_hash': manifest_hash,
        'updated': ts
    }
    with open(latest_path, 'w') as f:
        json.dump(latest_data, f, indent=2)
    
    return snapshot_id


def list_memory_snapshots(vault_path: str) -> List[Dict[str, Any]]:
    """List all memory snapshots."""
    paths = _get_memory_paths(vault_path)
    snapshots_dir = paths['shared'] / 'snapshots'
    
    if not snapshots_dir.exists():
        return []
    
    snapshots = []
    for manifest_file in snapshots_dir.glob('*.json'):
        if manifest_file.name == 'latest.json':
            continue
        
        try:
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
                snapshots.append(manifest)
        except:
            pass
    
    # Sort by creation time
    snapshots.sort(key=lambda s: s.get('created', 0), reverse=True)
    return snapshots


def get_latest_snapshot(vault_path: str) -> Optional[Dict[str, Any]]:
    """Get the latest memory snapshot."""
    paths = _get_memory_paths(vault_path)
    latest_path = paths['shared'] / 'snapshots' / 'latest.json'
    
    if not latest_path.exists():
        return None
    
    try:
        with open(latest_path, 'r') as f:
            return json.load(f)
    except:
        return None


def verify_memory_snapshot(
    vault_path: str,
    snapshot_id: Optional[str] = None,
    check_tampering: bool = True
) -> Dict[str, Any]:
    """
    Verify integrity of memory snapshot.
    
    Args:
        vault_path: Path to vault
        snapshot_id: Specific snapshot to verify, or None for latest
        check_tampering: If True, verify file hashes match manifest
    
    Returns:
        Verification report dict
    """
    paths = _get_memory_paths(vault_path)
    
    report = {
        'snapshot_id': snapshot_id,
        'valid': False,
        'manifest_hash_match': False,
        'tampered_files': [],
        'missing_files': [],
        'errors': []
    }
    
    # Get snapshot to verify
    if snapshot_id:
        manifest_path = paths['shared'] / 'snapshots' / f"{snapshot_id}.json"
    else:
        latest = get_latest_snapshot(vault_path)
        if not latest:
            report['errors'].append("No snapshots found")
            return report
        snapshot_id = latest['latest_id']
        manifest_path = paths['shared'] / 'snapshots' / f"{snapshot_id}.json"
    
    if not manifest_path.exists():
        report['errors'].append(f"Snapshot not found: {snapshot_id}")
        return report
    
    # Load manifest
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        report['errors'].append(f"Failed to load manifest: {e}")
        return report
    
    # Verify manifest hash
    stored_hash = manifest.get('manifest_hash')
    computed_hash = compute_manifest_hash(manifest)
    report['manifest_hash_match'] = (stored_hash == computed_hash)
    
    if not report['manifest_hash_match']:
        report['errors'].append("Manifest hash mismatch - manifest tampered!")
        return report
    
    if not check_tampering:
        report['valid'] = True
        return report
    
    # Verify each file hash
    for file_info in manifest.get('records', []):
        file_path = file_info.get('file')
        expected_hash = file_info.get('checksum')
        
        full_path = paths['bots'].parent / file_path
        
        if not full_path.exists():
            report['missing_files'].append(file_path)
            continue
        
        # Compute current hash
        try:
            current_hash = compute_file_hash(full_path)
            if current_hash != expected_hash:
                report['tampered_files'].append({
                    'file': file_path,
                    'expected': expected_hash,
                    'actual': current_hash
                })
        except Exception as e:
            report['errors'].append(f"Error verifying {file_path}: {e}")
    
    report['valid'] = (
        report['manifest_hash_match'] and 
        len(report['tampered_files']) == 0 and
        len(report['missing_files']) == 0
    )
    
    return report


def restore_memory_snapshot(
    vault_path: str,
    snapshot_id: Optional[str] = None,
    controller: bool = False
) -> Dict[str, Any]:
    """
    Restore memory from a snapshot.
    
    Args:
        vault_path: Path to vault
        snapshot_id: Specific snapshot to restore, or None for latest
        controller: Must be True (required for writing)
    
    Returns:
        Restoration report
    """
    if not controller:
        raise PermissionError("Restoring memory snapshot requires controller=True")
    
    paths = _get_memory_paths(vault_path)
    
    # Get snapshot
    if snapshot_id:
        manifest_path = paths['shared'] / 'snapshots' / f"{snapshot_id}.json"
    else:
        latest = get_latest_snapshot(vault_path)
        if not latest:
            raise ValueError("No snapshots found")
        snapshot_id = latest['latest_id']
        manifest_path = paths['shared'] / 'snapshots' / f"{snapshot_id}.json"
    
    if not manifest_path.exists():
        raise ValueError(f"Snapshot not found: {snapshot_id}")
    
    # Verify before restoring
    verification = verify_memory_snapshot(vault_path, snapshot_id)
    if not verification['valid']:
        raise ValueError(
            f"Cannot restore tampered snapshot: {verification['errors']}"
        )
    
    # Load manifest
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    # Track restored files
    restored = []
    
    # Restore files
    for file_info in manifest.get('records', []):
        file_path = file_info.get('file')
        src_path = paths['bots'].parent / file_path
        
        if not src_path.exists():
            continue
        
        dest_dir = paths['bots'].parent / '.restored'
        dest_dir.mkdir(exist_ok=True)
        dest_path = dest_dir / file_path
        
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        import shutil
        shutil.copy2(src_path, dest_path)
        restored.append(file_path)
    
    return {
        'snapshot_id': snapshot_id,
        'restored_count': len(restored),
        'restored_files': restored
    }

"""Memory Pack Export/Import - Portable memory backup."""
import json
import os
import shutil
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import tarfile
import tempfile

from .memory import _get_memory_paths, _init_memory_structure
from .memory_snapshot import compute_manifest_hash


def export_memory_pack(
    vault_path: str,
    output_path: str,
    include_snapshots: bool = True,
    include_truth: bool = True,
    deterministic: bool = False
) -> Dict[str, Any]:
    """
    Export memory to a portable pack file.
    
    Creates a .qbxmem file (tar.gz) containing:
    - Memory records (bots, shared, projects)
    - Index file
    - Manifest with hashes
    
    Args:
        vault_path: Path to vault
        output_path: Output .qbxmem file path
        include_snapshots: Include memory snapshots
        include_truth: Include truth registry
        deterministic: If True, exclude timestamps for reproducible exports
    
    Returns:
        Export report with hashes
    """
    paths = _get_memory_paths(vault_path)
    vault = Path(vault_path)
    
    # Create temp directory for packing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create manifest (without timestamp for deterministic mode)
        manifest = {
            'version': 1,
            'vault_path': str(Path(vault_path).resolve()),
            'deterministic': deterministic,
            'includes': []
        }
        
        if not deterministic:
            manifest['exported'] = int(time.time())
        
        # Copy memory directories
        memory_dir = temp_path / 'memory'
        memory_dir.mkdir()
        
        # Export bots
        if paths['bots'].exists():
            dest = memory_dir / 'bots'
            shutil.copytree(paths['bots'], dest)
            manifest['includes'].append('bots')
        
        # Export shared records (copy as 'shared_records' to avoid conflict)
        shared_records_src = paths['shared'] / 'records'
        if shared_records_src.exists():
            dest = memory_dir / 'shared_records'
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(shared_records_src, dest)
            manifest['includes'].append('shared_records')
        
        # Export projects
        if paths['projects'].exists():
            dest = memory_dir / 'projects'
            shutil.copytree(paths['projects'], dest)
            manifest['includes'].append('projects')
        
        # Export truth registry
        if include_truth and (paths['shared'] / 'truth_registry.json').exists():
            dest = memory_dir / 'truth_registry.json'
            shutil.copy2(paths['shared'] / 'truth_registry.json', dest)
            manifest['includes'].append('truth_registry')
        
        # Export snapshots
        if include_snapshots:
            snapshots_src = paths['shared'] / 'snapshots'
            if snapshots_src.exists():
                dest = memory_dir / 'snapshots'
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(snapshots_src, dest)
                manifest['includes'].append('snapshots')
        
        # Export index
        if paths['index'].exists():
            dest = memory_dir / 'index'
            shutil.copytree(paths['index'], dest)
            manifest['includes'].append('index')
        
        # Compute manifest hash BEFORE adding it to manifest (for deterministic mode)
        # Create a clean copy for hash computation
        manifest_for_hash = {
            'version': manifest['version'],
            'vault_path': manifest['vault_path'],
            'includes': sorted(manifest['includes'])
        }
        manifest_hash = compute_manifest_hash(manifest_for_hash)
        
        # Now add the full manifest data
        manifest['manifest_hash'] = manifest_hash
        
        # Save manifest
        with open(temp_path / 'manifest.json', 'w') as f:
            json.dump(manifest, f, sort_keys=True)
        
        # Also save manifest hash separately (for verification without extracting)
        with open(temp_path / 'MANIFEST.SHA256', 'w') as f:
            f.write(manifest_hash)
        
        # Create tar.gz pack
        # For deterministic exports, we need to control file order
        with tarfile.open(output_path, 'w:gz') as tar:
            # Add files in sorted order for determinism
            temp_path_str = str(temp_path)
            
            # Collect all files to add
            files_to_add = []
            for root, dirs, files in os.walk(temp_path_str):
                # Sort directories and files for consistent ordering
                dirs.sort()
                files.sort()
                
                for filename in files:
                    filepath = os.path.join(root, filename)
                    arcname = os.path.relpath(filepath, temp_path_str)
                    files_to_add.append((filepath, arcname))
            
            # Add to tar in sorted order
            for filepath, arcname in files_to_add:
                tar.add(filepath, arcname=arcname)
    
    # Compute pack hash
    pack_hash = compute_file_hash(Path(output_path))
    
    return {
        'output_path': output_path,
        'pack_hash': pack_hash,
        'manifest_hash': manifest_hash,
        'files_included': manifest['includes']
    }


def import_memory_pack(
    vault_path: str,
    pack_path: str,
    verify: bool = True,
    controller: bool = False
) -> Dict[str, Any]:
    """
    Import memory from a portable pack file.
    
    Args:
        vault_path: Path to vault
        pack_path: Path to .qbxmem file
        verify: Verify pack integrity before import
        controller: Required for writing
    
    Returns:
        Import report
    """
    if not controller:
        raise PermissionError("Importing memory pack requires controller=True")
    
    _init_memory_structure(vault_path)
    paths = _get_memory_paths(vault_path)
    
    if verify:
        # Verify pack
        verification = verify_memory_pack(pack_path)
        if not verification['valid']:
            raise ValueError(f"Invalid pack: {verification['errors']}")
    
    # Extract pack
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Extract tar.gz
        with tarfile.open(pack_path, 'r:gz') as tar:
            tar.extractall(temp_path)
        
        # Handle both formats: memory_pack/manifest.json or manifest.json
        memory_pack = temp_path / 'memory_pack'
        manifest_path = memory_pack / 'manifest.json'
        if not manifest_path.exists():
            manifest_path = temp_path / 'manifest.json'
            memory_pack = temp_path  # Update root to temp_path
        
        # Load manifest
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        imported = {
            'bots': 0,
            'shared_records': 0,
            'projects': 0,
            'snapshots': 0,
            'truth': False
        }
        
        # Import bots
        bots_src = memory_pack / 'bots'
        if bots_src.exists():
            if paths['bots'].exists():
                shutil.rmtree(paths['bots'])
            shutil.copytree(bots_src, paths['bots'])
            imported['bots'] = len(list(bots_src.rglob('*.json')))
        
        # Import shared records (from 'shared_records' folder)
        shared_src = memory_pack / 'shared_records'
        if shared_src.exists():
            dest = paths['shared'] / 'records'
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(shared_src, dest)
            imported['shared_records'] = len(list(shared_src.rglob('*.json')))
        
        # Import projects
        projects_src = memory_pack / 'projects'
        if projects_src.exists():
            if paths['projects'].exists():
                shutil.rmtree(paths['projects'])
            shutil.copytree(projects_src, paths['projects'])
            imported['projects'] = len(list(projects_src.rglob('*.json')))
        
        # Import truth registry
        truth_src = memory_pack / 'truth_registry.json'
        if truth_src.exists():
            shutil.copy2(truth_src, paths['shared'] / 'truth_registry.json')
            imported['truth'] = True
        
        # Import snapshots
        snapshots_src = memory_pack / 'snapshots'
        if snapshots_src.exists():
            dest = paths['shared'] / 'snapshots'
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(snapshots_src, dest)
            imported['snapshots'] = len(list(snapshots_src.rglob('*.json')))
        
        # Import index
        index_src = memory_pack / 'index'
        if index_src.exists():
            if paths['index'].exists():
                shutil.rmtree(paths['index'])
            shutil.copytree(index_src, paths['index'])
    
    return {
        'imported': imported,
        'manifest': manifest
    }


def verify_memory_pack(pack_path: str) -> Dict[str, Any]:
    """
    Verify integrity of a memory pack.
    
    Args:
        pack_path: Path to .qbxmem file
    
    Returns:
        Verification report
    """
    report = {
        'valid': False,
        'pack_hash': None,
        'manifest_hash': None,
        'manifest_hash_match': False,
        'errors': []
    }
    
    pack_file = Path(pack_path)
    if not pack_file.exists():
        report['errors'].append("Pack file not found")
        return report
    
    # Compute pack hash
    report['pack_hash'] = compute_file_hash(pack_file)
    
    # Extract and verify manifest
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            with tarfile.open(pack_path, 'r:gz') as tar:
                tar.extractall(temp_path)
            
            # Handle both formats: memory_pack/manifest.json or manifest.json
            manifest_path = temp_path / 'memory_pack' / 'manifest.json'
            if not manifest_path.exists():
                manifest_path = temp_path / 'manifest.json'
            if not manifest_path.exists():
                report['errors'].append("Manifest not found in pack")
                return report
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Verify manifest hash
            stored_hash = manifest.get('manifest_hash')
            computed_hash = compute_manifest_hash(manifest)
            report['manifest_hash'] = computed_hash
            report['manifest_hash_match'] = (stored_hash == computed_hash)
            
            if not report['manifest_hash_match']:
                report['errors'].append("Manifest hash mismatch")
                return report
            
            report['valid'] = True
            
    except Exception as e:
        report['errors'].append(f"Verification failed: {e}")
    
    return report


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def export_memory_pack_manifest_only(
    vault_path: str,
    output_path: str
) -> str:
    """
    Export only manifest (metadata) without full pack.
    
    Useful for lightweight backup of structure only.
    """
    paths = _get_memory_paths(vault_path)
    
    manifest = {
        'type': 'memory_manifest',
        'vault_path': vault_path,
        'exported': int(time.time()),
        'bots': [],
        'shared_records_count': 0,
        'projects': []
    }
    
    # Count bots
    if paths['bots'].exists():
        for bot_dir in paths['bots'].iterdir():
            if bot_dir.is_dir():
                records_dir = bot_dir / 'records'
                if records_dir.exists():
                    manifest['bots'].append({
                        'bot_id': bot_dir.name,
                        'records': len(list(records_dir.glob('*.json')))
                    })
    
    # Count shared
    shared_records = paths['shared'] / 'records'
    if shared_records.exists():
        manifest['shared_records_count'] = len(list(shared_records.glob('*.json')))
    
    # Count projects
    if paths['projects'].exists():
        for proj_dir in paths['projects'].iterdir():
            if proj_dir.is_dir():
                manifest['projects'].append(proj_dir.name)
    
    # Save manifest
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    return output_path

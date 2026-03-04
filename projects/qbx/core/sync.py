"""
Distributed Sync MVP - Push/Pull entre nodos usando manifests + hashes.

Arquitectura:
- sync_push(local, remote, scope, since_snapshot=None)
- sync_pull(remote, local, scope, since_snapshot=None)
- diff_manifests(local, remote) → missing records

Scope soportado:
- bot_id: Solo memoria privada de ese bot
- project: Memoria de un proyecto específico  
- shared: Memoria compartida de la colmena
- all: Toda la memoria

Conflictos:
- Si truth_registry difiere → ConflictError (controller resuelve)
"""

import json
import os
import shutil
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .memory import _get_memory_paths, _init_memory_structure, truth_get, truth_set
from .memory_snapshot import compute_manifest_hash


# ============================================================================
# ERRORS
# ============================================================================

class SyncError(Exception):
    """Base sync error."""
    pass


class ConflictError(SyncError):
    """
    Raised when truth_registry differs between local and remote.
    Controller must resolve the conflict.
    """
    def __init__(self, local_truth: Dict, remote_truth: Dict):
        self.local_truth = local_truth
        self.remote_truth = remote_truth
        super().__init__(f"Truth registry conflict: local={local_truth}, remote={remote_truth}")


class ChecksumConflictError(SyncError):
    """
    Raised when same record_id has different checksum in local vs remote.
    For private: treated as update. For shared: requires controller resolution.
    """
    def __init__(self, record_id: str, local_checksum: str, remote_checksum: str, visibility: str):
        self.record_id = record_id
        self.local_checksum = local_checksum
        self.remote_checksum = remote_checksum
        self.visibility = visibility
        super().__init__(f"Checksum conflict for {record_id}: local={local_checksum[:16]}..., remote={remote_checksum[:16]}...")


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class SyncScope(Enum):
    """Sync scope types."""
    BOT = "bot"           # Private memory for specific bot
    PROJECT = "project"  # All memory for a project
    SHARED = "shared"    # Shared hive memory
    ALL = "all"          # Everything


@dataclass
class SyncRecord:
    """A single record to sync."""
    record_id: str
    checksum: str
    visibility: str      # "private" or "shared"
    bot_id: str
    project_id: str
    file_path: str       # Relative path within memory structure


@dataclass
class SyncManifest:
    """Manifest describing what records exist in a node."""
    vault_path: str
    scope: str
    generated: int = field(default_factory=lambda: int(time.time()))
    truth_hash: str = ""
    records: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'vault_path': self.vault_path,
            'scope': self.scope,
            'generated': self.generated,
            'truth_hash': self.truth_hash,
            'records': self.records
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'SyncManifest':
        return SyncManifest(
            vault_path=data['vault_path'],
            scope=data['scope'],
            generated=data.get('generated', int(time.time())),
            truth_hash=data.get('truth_hash', ''),
            records=data.get('records', [])
        )


@dataclass
class SyncResult:
    """Result of a sync operation."""
    pushed: int = 0
    pulled: int = 0
    conflicts: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


# ============================================================================
# MANIFEST GENERATION
# ============================================================================

def compute_truth_hash(vault_path: str) -> str:
    """Compute hash of truth_registry."""
    truth = truth_get(vault_path)
    if not truth:
        return ""
    content = json.dumps(truth, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def generate_manifest(
    vault_path: str,
    scope: str,
    bot_id: Optional[str] = None,
    project_id: Optional[str] = None
) -> SyncManifest:
    """
    Generate a sync manifest for the given scope.
    
    Args:
        vault_path: Path to vault
        scope: "bot", "project", "shared", or "all"
        bot_id: Required for scope="bot"
        project_id: Required for scope="project"
    
    Returns:
        SyncManifest with all records
    """
    paths = _get_memory_paths(vault_path)
    manifest = SyncManifest(
        vault_path=vault_path,
        scope=scope,
        truth_hash=compute_truth_hash(vault_path)
    )
    
    # Collect records based on scope
    index_path = paths['index'] / 'records_index.jsonl'
    if not index_path.exists():
        return manifest
    
    with open(index_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            
            # Filter by scope
            if scope == "bot":
                if entry.get('bot_id') != bot_id:
                    continue
            elif scope == "project":
                if entry.get('project_id') != project_id:
                    continue
            elif scope == "shared":
                if entry.get('visibility') != "shared":
                    continue
            # "all" includes everything
            
            # Determine file path
            if entry.get('visibility') == 'shared':
                record_path = paths['shared'] / 'records' / f"{entry['record_id']}.json"
            else:
                record_path = paths['bots'] / entry.get('bot_id', '') / 'records' / f"{entry['record_id']}.json"
            
            manifest.records.append({
                'record_id': entry['record_id'],
                'checksum': entry.get('checksum', ''),
                'visibility': entry.get('visibility', 'private'),
                'bot_id': entry.get('bot_id', ''),
                'project_id': entry.get('project_id', ''),
                'file_path': str(record_path)
            })
    
    return manifest


def diff_manifests(
    local_manifest: SyncManifest,
    remote_manifest: SyncManifest
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Compare two manifests to find missing records and checksum conflicts.
    
    Returns:
        (to_push, to_pull, conflicts) 
        - to_push: records in local but not remote
        - to_pull: records in remote but not local
        - conflicts: records with same ID but different checksum
    
    Algorithm:
    1. Build index of remote records by record_id
    2. For each local record:
       - if not in remote → to_push
       - if in remote but checksum differs → conflict
    3. Build index of local records by record_id  
    4. For each remote record, if not in local → to_pull
    """
    # Index remote records
    remote_index = {r['record_id']: r for r in remote_manifest.records}
    
    # Find records to push and conflicts
    to_push = []
    conflicts = []
    for record in local_manifest.records:
        rid = record['record_id']
        if rid not in remote_index:
            to_push.append(record)
        else:
            # Check checksum
            remote_record = remote_index[rid]
            if record.get('checksum') != remote_record.get('checksum'):
                conflicts.append({
                    'record_id': rid,
                    'local_checksum': record.get('checksum'),
                    'remote_checksum': remote_record.get('checksum'),
                    'visibility': record.get('visibility', 'private')
                })
    
    # Index local records
    local_index = {r['record_id']: r for r in local_manifest.records}
    
    # Find records to pull (remote only)
    to_pull = []
    for record in remote_manifest.records:
        if record['record_id'] not in local_index:
            to_pull.append(record)
    
    return to_push, to_pull, conflicts


# ============================================================================
# SYNC OPERATIONS
# ============================================================================

def sync_push(
    local_vault: str,
    remote_vault: str,
    scope: str,
    since_snapshot: Optional[str] = None,
    bot_id: Optional[str] = None,
    project_id: Optional[str] = None,
    dry_run: bool = False
) -> SyncResult:
    """
    Push records from local to remote.
    
    Args:
        local_vault: Source vault path
        remote_vault: Destination vault path
        scope: "bot", "project", "shared", "all"
        since_snapshot: Only sync records after this snapshot (TODO)
        bot_id: Required for scope="bot"
        project_id: Required for scope="project"
        dry_run: If True, don't actually copy
    
    Returns:
        SyncResult with counts
    """
    result = SyncResult()
    
    # Check truth registry conflict
    # Only conflict if BOTH have truth AND they're different
    local_truth = truth_get(local_vault)
    remote_truth = truth_get(remote_vault)
    
    # Conflict only when both have truth AND they're different
    if local_truth and remote_truth and local_truth != remote_truth:
        raise ConflictError(local_truth, remote_truth)
    
    # Generate manifests
    local_manifest = generate_manifest(local_vault, scope, bot_id, project_id)
    
    # Try to load remote manifest if exists
    remote_manifest = load_remote_manifest(remote_vault, scope)
    
    if remote_manifest is None:
        # Remote is empty - push everything
        to_push = local_manifest.records
        to_pull = []
        conflicts = []
    else:
        # Find diff (now returns 3 values)
        to_push, to_pull, conflicts = diff_manifests(local_manifest, remote_manifest)
    
    # Handle checksum conflicts
    for conflict in conflicts:
        visibility = conflict['visibility']
        if visibility == 'shared':
            # Shared records require conflict resolution
            raise ChecksumConflictError(
                conflict['record_id'],
                conflict['local_checksum'],
                conflict['remote_checksum'],
                visibility
            )
        # Private records: treat as update (overwrite with newer version)
        # Find the local record and add it to to_push
        for record in local_manifest.records:
            if record['record_id'] == conflict['record_id']:
                to_push.append(record)
                break
        result.conflicts += 1
    
    # Copy records
    local_paths = _get_memory_paths(local_vault)
    
    for record in to_push:
        if dry_run:
            result.pushed += 1
            continue
        
        try:
            # The file_path in the manifest is absolute from the source vault
            # We need to reconstruct the path relative to the source vault
            src_path = Path(record['file_path'])
            if not src_path.exists():
                result.errors.append(f"Source not found: {src_path}")
                continue
            
            # Determine destination based on record type, not stored path
            _init_memory_structure(remote_vault)
            remote_paths = _get_memory_paths(remote_vault)
            
            if record['visibility'] == 'shared':
                dest_path = remote_paths['shared'] / 'records' / f"{record['record_id']}.json"
            else:
                dest_path = remote_paths['bots'] / record['bot_id'] / 'records' / f"{record['record_id']}.json"
            
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write: copy to temp, then rename
            temp_path = dest_path.with_suffix('.tmp')
            shutil.copy2(src_path, temp_path)
            os.replace(temp_path, dest_path)  # Atomic on Windows
            
            result.pushed += 1
            
        except Exception as e:
            result.errors.append(f"Error copying {record['record_id']}: {e}")
    
    # Update remote manifest
    if not dry_run and result.pushed > 0:
        save_remote_manifest(remote_vault, scope, local_manifest)
        
        # Also update the index file in remote
        _update_remote_index(remote_vault, to_push)
    
    return result


def _update_remote_index(vault_path: str, records: List[Dict]):
    """Update the index file when records are synced."""
    paths = _get_memory_paths(vault_path)
    index_path = paths['index'] / 'records_index.jsonl'
    
    with open(index_path, 'a', encoding='utf-8') as f:
        for record in records:
            index_entry = {
                'record_id': record['record_id'],
                'bot_id': record['bot_id'],
                'project_id': record['project_id'],
                'visibility': record['visibility'],
                'type': 'fact',  # Default
                'tags': [],
                'ts': 0,  # Use 0 for synced records (no original timestamp)
                'checksum': record['checksum']
            }
            f.write(json.dumps(index_entry) + '\n')


def sync_pull(
    remote_vault: str,
    local_vault: str,
    scope: str,
    since_snapshot: Optional[str] = None,
    bot_id: Optional[str] = None,
    project_id: Optional[str] = None,
    dry_run: bool = False
) -> SyncResult:
    """
    Pull records from remote to local.
    
    Args:
        remote_vault: Source vault path
        local_vault: Destination vault path
        scope: "bot", "project", "shared", "all"
        since_snapshot: Only sync records after this snapshot (TODO)
        bot_id: Required for scope="bot"
        project_id: Required for scope="project"
        dry_run: If True, don't actually copy
    
    Returns:
        SyncResult with counts
    """
    # Pull is essentially push in reverse direction
    # Generate manifest from remote, copy to local
    result = SyncResult()
    
    # Check truth registry conflict (same as push)
    remote_truth = truth_get(remote_vault)
    local_truth = truth_get(local_vault)
    
    if remote_truth and local_truth and remote_truth != local_truth:
        raise ConflictError(local_truth, remote_truth)
    
    # Generate manifests
    remote_manifest = generate_manifest(remote_vault, scope, bot_id, project_id)
    local_manifest = load_remote_manifest(local_vault, scope) or SyncManifest(local_vault, scope)
    
    # Find records to pull (in remote but not in local)
    # diff_manifests now returns 3 values
    _, to_pull, conflicts = diff_manifests(local_manifest, remote_manifest)
    
    # Handle conflicts (same logic as push)
    for conflict in conflicts:
        visibility = conflict['visibility']
        if visibility == 'shared':
            raise ChecksumConflictError(
                conflict['record_id'],
                conflict['local_checksum'],
                conflict['remote_checksum'],
                visibility
            )
        # Private: treat as update
        for record in remote_manifest.records:
            if record['record_id'] == conflict['record_id']:
                to_pull.append(record)
                break
        result.conflicts += 1
    
    # Copy records
    for record in to_pull:
        if dry_run:
            result.pulled += 1
            continue
        
        try:
            src_path = Path(record['file_path'])
            if not src_path.exists():
                result.errors.append(f"Source not found: {src_path}")
                continue
            
            _init_memory_structure(local_vault)
            local_paths = _get_memory_paths(local_vault)
            
            if record['visibility'] == 'shared':
                dest_path = local_paths['shared'] / 'records' / f"{record['record_id']}.json"
            else:
                dest_path = local_paths['bots'] / record['bot_id'] / 'records' / f"{record['record_id']}.json"
            
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write: copy to temp, then rename
            temp_path = dest_path.with_suffix('.tmp')
            shutil.copy2(src_path, temp_path)
            os.replace(temp_path, dest_path)  # Atomic on Windows
            
            result.pulled += 1
            
        except Exception as e:
            result.errors.append(f"Error copying {record['record_id']}: {e}")
    
    # Update local manifest
    if not dry_run and result.pulled > 0:
        save_remote_manifest(local_vault, scope, remote_manifest)
        _update_remote_index(local_vault, to_pull)
    
    return result


def sync_bidirectional(
    vault_a: str,
    vault_b: str,
    scope: str,
    bot_id: Optional[str] = None,
    project_id: Optional[str] = None,
    dry_run: bool = False
) -> Tuple[SyncResult, SyncResult]:
    """
    Bidirectional sync - push and pull in one operation.
    
    Returns:
        (result_a_to_b, result_b_to_a)
    """
    # Check for conflicts first
    truth_a = truth_get(vault_a)
    truth_b = truth_get(vault_b)
    
    if truth_a != truth_b:
        raise ConflictError(truth_a, truth_b)
    
    # Push A → B
    result_ab = sync_push(vault_a, vault_b, scope, bot_id=bot_id, project_id=project_id, dry_run=dry_run)
    
    # Push B → A
    result_ba = sync_push(vault_b, vault_a, scope, bot_id=bot_id, project_id=project_id, dry_run=dry_run)
    
    return result_ab, result_ba


# ============================================================================
# REMOTE MANIFEST STORAGE
# ============================================================================

def get_remote_manifest_path(vault_path: str, scope: str) -> Path:
    """Get path to stored manifest for a scope."""
    paths = _get_memory_paths(vault_path)
    return paths['shared'] / 'sync_manifests' / f"{scope}.json"


def save_remote_manifest(vault_path: str, scope: str, manifest: SyncManifest):
    """Save manifest to vault."""
    _init_memory_structure(vault_path)
    paths = _get_memory_paths(vault_path)
    
    manifest_dir = paths['shared'] / 'sync_manifests'
    manifest_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_path = manifest_dir / f"{scope}.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest.to_dict(), f, indent=2)


def load_remote_manifest(vault_path: str, scope: str) -> Optional[SyncManifest]:
    """Load stored manifest for a scope."""
    manifest_path = get_remote_manifest_path(vault_path, scope)
    
    if not manifest_path.exists():
        return None
    
    with open(manifest_path, 'r') as f:
        data = json.load(f)
    
    return SyncManifest.from_dict(data)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def sync_status(local_vault: str, remote_vault: str, scope: str) -> Dict[str, Any]:
    """
    Get sync status between two vaults.
    
    Returns info about pending changes.
    """
    local_manifest = generate_manifest(local_vault, scope)
    remote_manifest = load_remote_manifest(remote_vault, scope) or SyncManifest(remote_vault, scope)
    
    to_push, to_pull, conflicts = diff_manifests(local_manifest, remote_manifest)
    
    local_truth = truth_get(local_vault)
    remote_truth = truth_get(remote_vault)
    
    return {
        'scope': scope,
        'local_records': len(local_manifest.records),
        'remote_records': len(remote_manifest.records),
        'to_push': len(to_push),
        'to_pull': len(to_pull),
        'conflicts': len(conflicts),
        'truth_conflict': local_truth != remote_truth,
        'local_truth': local_truth,
        'remote_truth': remote_truth
    }

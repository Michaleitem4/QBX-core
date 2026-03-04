"""QBX Memory Engine - Local Agent Brain + Hive Shared Memory."""
import json
import os
import hashlib
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from pathlib import Path
from .errors import IntegrityError


# Memory record types
MEMORY_TYPES = [
    "fact",      # Factual information
    "rule",      # Rule or policy
    "decision",  # Decision made
    "task_state", # State of a task
    "metric",    # Metric or measurement
    "doc_ref",   # Reference to document
    "summary",   # Summary of content
]

MEMORY_VISIBILITY = ["private", "shared"]


@dataclass
class MemoryRecord:
    """A single memory record."""
    record_id: str
    ts: int  # timestamp
    bot_id: str
    project_id: str
    visibility: str  # "private" or "shared"
    type: str  # fact, rule, decision, etc.
    tags: List[str] = field(default_factory=list)
    text: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    checksum: str = ""  # SHA-256 of content for verification
    
    def __post_init__(self):
        # Only compute checksum if not loading from storage (no existing checksum)
        if not self.checksum:
            self.checksum = self._compute_checksum()
    
    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the record content."""
        content = f"{self.record_id}:{self.ts}:{self.bot_id}:{self.project_id}:{self.visibility}:{self.type}:{self.tags}:{self.text}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def compute_current_checksum(self) -> str:
        """Compute what the checksum SHOULD be for current content."""
        return self._compute_checksum()
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MemoryRecord':
        """Create record from dict WITHOUT computing checksum."""
        # Create instance with existing checksum (don't recompute)
        record = cls(
            record_id=data['record_id'],
            ts=data['ts'],
            bot_id=data['bot_id'],
            project_id=data['project_id'],
            visibility=data['visibility'],
            type=data['type'],
            tags=data.get('tags', []),
            text=data.get('text', ''),
            meta=data.get('meta', {}),
            checksum=data.get('checksum', '')
        )
        return record


def _atomic_write(path: Path, content: str):
    """Write file atomically (write to temp, then rename)."""
    temp = path.with_suffix('.tmp')
    with open(temp, 'w', encoding='utf-8') as f:
        f.write(content)
    # On Windows, might need to handle existing file
    if path.exists():
        os.remove(path)
    os.rename(temp, path)


def _get_memory_paths(vault_path: str) -> Dict[str, Path]:
    """Get standard memory paths - stored alongside vault, not inside."""
    vault = Path(vault_path)
    
    # Memory stored in .qbx_memory/ directory next to vault
    mem_dir = vault.parent / f".{vault.stem}_memory"
    
    return {
        'bots': mem_dir / 'bots',
        'shared': mem_dir / 'shared',
        'projects': mem_dir / 'projects',
        'index': vault.parent / f".{vault.stem}_memory_index",
    }


def _init_memory_structure(vault_path: str):
    """Ensure memory directory structure exists."""
    vault = Path(vault_path)
    mem_dir = vault.parent / f".{vault.stem}_memory"
    index_dir = vault.parent / f".{vault.stem}_memory_index"
    
    # Create memory directories
    (mem_dir / 'bots').mkdir(parents=True, exist_ok=True)
    (mem_dir / 'shared' / 'records').mkdir(parents=True, exist_ok=True)
    (mem_dir / 'projects').mkdir(parents=True, exist_ok=True)
    
    # Create index directory
    index_dir.mkdir(parents=True, exist_ok=True)


def remember(
    vault_path: str,
    bot_id: str,
    project_id: str,
    text: str,
    visibility: str = "private",
    memory_type: str = "fact",
    tags: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    controller: bool = False,
    deterministic: bool = False
) -> str:
    """
    Store a memory record.
    
    Args:
        vault_path: Path to vault
        bot_id: ID of the bot creating this memory
        project_id: Project ID
        text: Memory content
        visibility: "private" or "shared"
        memory_type: Type of memory (fact, rule, decision, etc.)
        tags: Optional tags
        meta: Optional metadata
        controller: Required for shared memory (True)
        deterministic: If True, use content-based ID (reproducible)
    
    Returns:
        record_id
    
    Raises:
        PermissionError: If trying to write shared without controller
    """
    if visibility == "shared" and not controller:
        raise PermissionError("Writing shared memory requires controller=True")
    
    _init_memory_structure(vault_path)
    paths = _get_memory_paths(vault_path)
    
    # Generate record ID - deterministic or timestamp-based
    if deterministic:
        # Content-based ID for reproducibility
        content_for_hash = f"{bot_id}:{project_id}:{text}:{memory_type}"
        record_id = hashlib.sha256(content_for_hash.encode()).hexdigest()[:16]
        ts = 0  # Fixed timestamp for deterministic
    else:
        record_id = hashlib.sha256(f"{vault_path}{time.time()}{text}".encode()).hexdigest()[:16]
        ts = int(time.time())
    
    # Create record
    record = MemoryRecord(
        record_id=record_id,
        ts=ts,
        bot_id=bot_id,
        project_id=project_id,
        visibility=visibility,
        type=memory_type,
        tags=tags or [],
        text=text,
        meta=meta or {}
    )
    
    # Determine storage path
    if visibility == "shared":
        record_path = paths['shared'] / 'records' / f"{record_id}.json"
        proj_path = paths['shared']
    else:
        # Private memory: /mem/bots/{bot_id}/records/{record_id}.json
        record_path = paths['bots'] / bot_id / 'records' / f"{record_id}.json"
        proj_path = paths['bots'] / bot_id
    
    # Ensure directory exists
    record_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write record atomically
    _atomic_write(record_path, json.dumps(asdict(record), indent=2))
    
    # Append to index
    index_path = paths['index'] / 'records_index.jsonl'
    index_entry = {
        'record_id': record_id,
        'bot_id': bot_id,
        'project_id': project_id,
        'visibility': visibility,
        'type': memory_type,
        'tags': tags or [],
        'ts': ts,
        'checksum': record.checksum
    }
    with open(index_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(index_entry) + '\n')
    
    return record_id


def recall(
    vault_path: str,
    bot_id: Optional[str] = None,
    project_id: Optional[str] = None,
    visibility: Optional[str] = None,
    memory_type: Optional[str] = None,
    tags_any: Optional[List[str]] = None,
    keyword: Optional[str] = None,
    ts_min: Optional[int] = None,
    ts_max: Optional[int] = None,
    limit: int = 100
) -> List[MemoryRecord]:
    """
    Recall memory records matching criteria.
    
    Args:
        vault_path: Path to vault
        bot_id: Filter by bot ID
        project_id: Filter by project ID
        visibility: Filter by visibility (private/shared)
        memory_type: Filter by type
        tags_any: Match any of these tags
        keyword: Search in text content
        ts_min: Minimum timestamp
        ts_max: Maximum timestamp
        limit: Maximum results
    
    Returns:
        List of matching MemoryRecord
    """
    paths = _get_memory_paths(vault_path)
    index_path = paths['index'] / 'records_index.jsonl'
    
    if not index_path.exists():
        return []
    
    results = []
    
    # Read index and filter
    with open(index_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            
            # Apply filters
            if bot_id and entry.get('bot_id') != bot_id:
                continue
            if project_id and entry.get('project_id') != project_id:
                continue
            if visibility and entry.get('visibility') != visibility:
                continue
            if memory_type and entry.get('type') != memory_type:
                continue
            if tags_any and not any(t in entry.get('tags', []) for t in tags_any):
                continue
            if ts_min and entry.get('ts', 0) < ts_min:
                continue
            if ts_max and entry.get('ts', 0) > ts_max:
                continue
            
            # Load full record
            record_path = None
            if entry.get('visibility') == 'shared':
                record_path = paths['shared'] / 'records' / f"{entry['record_id']}.json"
            else:
                record_path = paths['bots'] / entry.get('bot_id', '') / 'records' / f"{entry['record_id']}.json"
            
            if record_path and record_path.exists():
                with open(record_path, 'r') as f:
                    record_data = json.load(f)
                    record = MemoryRecord(**record_data)
                    
                    # Keyword filter (search in text)
                    if keyword and keyword.lower() not in record.text.lower():
                        continue
                    
                    results.append(record)
            
            if len(results) >= limit:
                break
    
    return results


def memory_verify(vault_path: str, scope: str = "all") -> Dict[str, Any]:
    """
    Verify integrity of memory records.
    
    Args:
        vault_path: Path to vault
        scope: "all", "bots", "shared", or specific bot_id
    
    Returns:
        Verification report dict
    """
    paths = _get_memory_paths(vault_path)
    index_path = paths['index'] / 'records_index.jsonl'
    
    report = {
        'total': 0,
        'valid': 0,
        'invalid': [],
        'missing': [],
        'checksum_errors': []
    }
    
    if not index_path.exists():
        report['error'] = "No index found"
        return report
    
    with open(index_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            record_id = entry.get('record_id')
            expected_checksum = entry.get('checksum')
            
            report['total'] += 1
            
            # Find record file
            if entry.get('visibility') == 'shared':
                record_path = paths['shared'] / 'records' / f"{record_id}.json"
            else:
                record_path = paths['bots'] / entry.get('bot_id', '') / 'records' / f"{record_id}.json"
            
            if not record_path or not record_path.exists():
                report['missing'].append(record_id)
                continue
            
            # Verify checksum - compute current checksum and compare to stored
            try:
                with open(record_path, 'r') as f:
                    record_data = json.load(f)
                    # Create record without auto-computing checksum
                    record = MemoryRecord.from_dict(record_data)
                    # Compute what checksum SHOULD be now
                    current_checksum = record.compute_current_checksum()
                    stored_checksum = record_data.get('checksum', '')
                    
                    if current_checksum == stored_checksum:
                        report['valid'] += 1
                    else:
                        report['checksum_errors'].append(record_id)
            except Exception as e:
                report['invalid'].append({'record_id': record_id, 'error': str(e)})
    
    return report


# Truth registry for shared state
def truth_get(vault_path: str) -> Dict[str, Any]:
    """Get truth registry (shared state)."""
    paths = _get_memory_paths(vault_path)
    truth_path = paths['shared'] / 'truth_registry.json'
    
    if not truth_path.exists():
        return {}
    
    with open(truth_path, 'r') as f:
        return json.load(f)


def truth_set(vault_path: str, data: Dict[str, Any], controller: bool = False):
    """
    Set truth registry (shared state).
    
    Args:
        vault_path: Path to vault
        data: Truth data to set
        controller: Must be True to modify truth
    
    Raises:
        PermissionError: If controller is not True
    """
    if not controller:
        raise PermissionError("Setting truth registry requires controller=True")
    
    _init_memory_structure(vault_path)
    paths = _get_memory_paths(vault_path)
    truth_path = paths['shared'] / 'truth_registry.json'
    
    # Atomic write
    _atomic_write(truth_path, json.dumps(data, indent=2))


# ============================================================================
# HIVE SHARED MEMORY - Namespaces + Conflict Detection
# ============================================================================

def check_conflict(
    vault_path: str,
    project_id: str,
    key: str,
    visibility: str = "shared"
) -> Optional[Dict[str, Any]]:
    """
    Check if a key already exists (conflict detection).
    
    Args:
        vault_path: Path to vault
        project_id: Project ID
        key: Key to check (stored in meta.conflict_key)
        visibility: "shared" or "private"
    
    Returns:
        Existing record dict if conflict, None otherwise
    """
    paths = _get_memory_paths(vault_path)
    index_path = paths['index'] / 'records_index.jsonl'
    
    if not index_path.exists():
        return None
    
    with open(index_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            
            # Match project_id and key
            if (entry.get('project_id') == project_id and 
                entry.get('visibility') == visibility):
                
                # Load record to check key
                if visibility == 'shared':
                    record_path = paths['shared'] / 'records' / f"{entry['record_id']}.json"
                else:
                    record_path = paths['bots'] / entry.get('bot_id', '') / 'records' / f"{entry['record_id']}.json"
                
                if record_path and record_path.exists():
                    with open(record_path, 'r') as f:
                        record_data = json.load(f)
                        # Check conflict_key in meta
                        if record_data.get('meta', {}).get('conflict_key') == key:
                            return record_data
    
    return None


def remember_with_conflict_check(
    vault_path: str,
    bot_id: str,
    project_id: str,
    text: str,
    conflict_key: Optional[str] = None,
    visibility: str = "private",
    memory_type: str = "fact",
    tags: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    controller: bool = False
) -> Dict[str, Any]:
    """
    Store memory with conflict detection.
    
    If conflict_key is provided and a record with that key exists:
    - Creates a "conflict" type record with both versions
    - Registers conflict metadata
    
    Args:
        vault_path: Path to vault
        bot_id: ID of the bot
        project_id: Project ID
        text: Memory content
        conflict_key: Optional key to check for conflicts
        visibility: "private" or "shared"
        memory_type: Type of memory
        tags: Optional tags
        meta: Optional metadata
        controller: Required for shared memory
    
    Returns:
        Dict with:
        - record_id: Primary record ID
        - conflict_record_id: If conflict created
        - conflict_detected: Boolean
    """
    result = {
        'record_id': None,
        'conflict_record_id': None,
        'conflict_detected': False
    }
    
    # Check for conflict if key provided
    existing = None
    if conflict_key:
        existing = check_conflict(vault_path, project_id, conflict_key, visibility)
    
    # Prepare meta
    record_meta = meta or {}
    if conflict_key:
        record_meta['conflict_key'] = conflict_key
    
    # Create primary record
    record_id = remember(
        vault_path=vault_path,
        bot_id=bot_id,
        project_id=project_id,
        text=text,
        visibility=visibility,
        memory_type=memory_type,
        tags=tags,
        meta=record_meta,
        controller=controller
    )
    result['record_id'] = record_id
    
    # If conflict detected, create conflict record
    if existing:
        result['conflict_detected'] = True
        
        # Create conflict record
        conflict_text = f"CONFLICT: {conflict_key}\n---\nVERSION 1 (existing):\n{existing.get('text', '')}\n---\nVERSION 2 (new):\n{text}"
        
        conflict_id = remember(
            vault_path=vault_path,
            bot_id=bot_id,
            project_id=project_id,
            text=conflict_text,
            visibility=visibility,
            memory_type="conflict",
            tags=["conflict", conflict_key],
            meta={
                'conflict_key': conflict_key,
                'existing_record_id': existing.get('record_id'),
                'new_record_id': record_id,
                'original_type': memory_type
            },
            controller=controller
        )
        result['conflict_record_id'] = conflict_id
    
    return result


def get_projects_memory(
    vault_path: str,
    project_id: str
) -> List[MemoryRecord]:
    """
    Get all memory records for a specific project.
    
    Args:
        vault_path: Path to vault
        project_id: Project ID to query
    
    Returns:
        List of MemoryRecord for the project
    """
    return recall(vault_path, project_id=project_id)


def get_shared_memory(
    vault_path: str,
    memory_type: Optional[str] = None
) -> List[MemoryRecord]:
    """
    Get all shared memory (any bot can read).
    
    Args:
        vault_path: Path to vault
        memory_type: Optional filter by type
    
    Returns:
        List of shared MemoryRecord
    """
    return recall(vault_path, visibility="shared", memory_type=memory_type)

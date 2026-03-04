# QBX Memory Model

## Overview

QBX Memory provides a local agent brain with persistent storage, versioning, and coordination capabilities for multi-agent systems.

## Core Concepts

### MemoryRecord

The fundamental unit of memory storage:

```python
@dataclass
class MemoryRecord:
    record_id: str      # Unique identifier (SHA-256 based)
    ts: int            # Unix timestamp
    bot_id: str        # Which bot created this
    project_id: str    # Which project
    visibility: str     # "private" or "shared"
    type: str          # "fact", "rule", "decision", etc.
    tags: List[str]    # Optional tags for filtering
    text: str          # Memory content
    meta: Dict         # Additional metadata
    checksum: str      # SHA-256 for integrity
```

### Visibility Modes

- **Private**: Only the bot that created it can read it
- **Shared**: All bots in the hive can read it

### Memory Types

- `fact` - Factual information
- `rule` - Operational rules
- `decision` - Decision records
- `conflict` - Conflict resolution records

## Namespaces

Memory is organized into namespaces:

```
.vaultname_memory/
├── bots/
│   └── {bot_id}/
│       └── records/
│           └── {record_id}.json
├── shared/
│   └── records/
│       └── {record_id}.json
├── projects/
│   └── {project_id}/
└── shared/
    └── truth_registry.json
```

## Snapshots

Memory snapshots create point-in-time captures:

- Store all records + metadata
- Include checksums for verification
- Exportable to new vaults
- Restore to any previous state

```python
# Create snapshot
create_memory_snapshot(vault_path, "backup-v1", controller=True)

# List snapshots
list_memory_snapshots(vault_path)

# Verify integrity
verify_memory_snapshot(vault_path, snapshot_id)
```

## Memory Packs

Portable containers for backup/restore:

- `.qbxmem` format (tar.gz)
- Include all records, snapshots, truth
- Deterministic mode for reproducibility
- SHA-256 verification

```python
# Export
export_memory_pack(vault, "backup.qbxmem", deterministic=True)

# Import
import_memory_pack(vault, "backup.qbxmem")

# Verify
verify_memory_pack("backup.qbxmem")
```

## Truth Registry

Shared state for coordination:

```python
# Set truth (controller only)
truth_set(vault, {"version": 1, "settings": {}}, controller=True)

# Get truth
truth = truth_get(vault)
```

Used for:
- Hive-wide configuration
- Version tracking
- Coordination state

## Integrity Verification

Every record includes SHA-256 checksum:

```python
# Verify all records
result = memory_verify(vault_path)
# Returns: {'valid': bool, 'issues': []}
```

Detects:
- Tampered records
- Missing files
- Checksum mismatches

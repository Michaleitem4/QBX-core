# QBX-Ω Architecture

## Overview

QBX-Ω is a deterministic vault system designed for secure data storage, versioning, and synchronization. It provides cryptographic integrity verification, portable memory containers, and multi-node sync capabilities.

## Core Concepts

### 1. Deterministic Vault

The vault is a single file containing:
- **Superblock**: Metadata header with checksums
- **Chunks**: Fixed-size data blocks (128MB default)
- **Object Table**: Index of stored objects

Key principle: **Given the same input, the vault produces identical output**. This is achieved through:
- Deterministic compression
- Fixed-size block alignment
- SHA-256 checksums for every block

### 2. Snapshots

Snapshots create point-in-time captures of the vault:
- Store object table state
- Preserve metadata (timestamps, checksums)
- Enable rollback to previous states
- Exportable to new vaults

### 3. Integrity Verification

Every operation verifies data integrity:
- Block-level SHA-256 checksums
- Superblock validation on mount
- Tamper detection via checksum mismatch
- Optional fsync for durability

### 4. Memory Packs

Portable containers for memory backup/restore:
- Export memory to `.qbxmem` (tar.gz)
- Include all records, snapshots, truth registry
- Deterministic export mode (reproducible hashes)
- Import with verification

### 5. Distributed Sync

Sync between nodes using manifests + hashes:
- **Scopes**: bot, project, shared, all
- **Conflict detection**: Via checksum comparison
- **Atomic writes**: Temp file + rename
- **Truth registry**: Shared state coordination

## System Components

```
qbx/
├── core/
│   ├── superblock.py    # Vault header r/w
│   ├── chunk.py         # Chunk management
│   ├── block.py         # Block with SHA-256
│   ├── memory.py        # Local agent brain
│   ├── memory_snapshot.py
│   ├── memory_pack.py   # Export/Import
│   ├── sync.py          # Distributed sync
│   └── object_table.py
├── cli/
│   └── qbx.py           # CLI interface
└── tests/
```

## Data Flow

1. **Write**: User → CLI → Core → Block → Chunk → Vault
2. **Read**: Vault → Chunk → Block → Verify → User
3. **Sync**: Manifest → Diff → Copy (atomic) → Verify
4. **Backup**: Memory → Pack → tar.gz → Export

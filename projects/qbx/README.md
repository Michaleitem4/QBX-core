# QBX Memory Engine

A deterministic vault system for secure data storage, versioning, and multi-agent synchronization.

## Overview

QBX (Quantum Block eXchange) is a deterministic vault system designed for:
- **Secure Storage**: Cryptographic integrity verification via SHA-256 checksums
- **Versioning**: Snapshots with point-in-time capture and rollback
- **Portability**: Memory packs for backup/restore across systems
- **Sync**: Distributed synchronization between nodes using manifests + hashes

## Installation

```bash
# Clone or download the project
cd projects/qbx

# Run tests
python -m pytest -q

# Show CLI help
python -m cli.qbx --help
```

## Quick Start

```bash
# Create a vault
python -m cli.qbx create myvault.qbxo

# Store a memory
python -m cli.qbx memory remember myvault.qbxo \
  --bot mybot \
  --project myproject \
  --text "Important fact"

# Query memories
python -m cli.qbx memory recall myvault.qbxo --bot mybot

# Create snapshot
python -m cli.qbx memory snapshot myvault.qbxo backup-001 --controller

# Export pack
python -m cli.qbx memory pack export myvault.qbxo -o backup.qbxmem
```

## Architecture

```
qbx/
├── core/           # Core modules
│   ├── memory.py        # Agent brain
│   ├── memory_snapshot.py
│   ├── memory_pack.py   # Export/Import
│   ├── sync.py         # Distributed sync
│   ├── superblock.py   # Vault header
│   └── chunk.py        # Chunk management
├── cli/            # CLI interface
│   └── qbx.py
├── docs/           # Documentation
└── tests/          # Test suite
```

## Features

| Feature | Description |
|---------|-------------|
| Deterministic Storage | Same input = same output |
| Snapshots | Point-in-time captures |
| Integrity | SHA-256 verification |
| Memory Packs | Portable backup containers |
| Distributed Sync | Multi-node synchronization |

## Documentation

- [Architecture](docs/architecture.md)
- [CLI Reference](docs/cli.md)
- [Memory Model](docs/memory_model.md)
- [Prior Art](docs/prior_art_reference.md)

## License

MIT License - See LICENSE file.

## Status

Tests: **64 passing**

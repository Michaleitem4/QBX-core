# PRIOR ART: QBX Memory Engine

## Abstract

This document describes the QBX Memory Engine, a deterministic vault system for secure data storage, versioning, and multi-agent synchronization.

---

## 1. Deterministic Storage

QBX achieves deterministic storage through:

- **Fixed-size chunks**: 128MB blocks ensure consistent addressing
- **Content-addressable naming**: SHA-256 based IDs for records
- **Deterministic export**: Excludes timestamps from pack manifests when requested
- **Fixed block alignment**: No fragmentation variability

This approach ensures that given identical inputs, QBX produces identical vault outputs.

---

## 2. Snapshot Versioning

QBX implements two-level snapshots:

- **Vault-level**: Filesystem snapshots preserving object table state
- **Memory-level**: Agent brain snapshots for state capture

Each snapshot stores:
- Full object table manifest
- Original timestamps (preserved, not replaced)
- SHA-256 checksums for every object

Snapshots are exportable to new vault files for isolation.

---

## 3. Cryptographic Verification

Every QBX record includes:

- **SHA-256 checksum**: Computed on write, verified on read
- **Inline storage**: Checksum stored with data
- **Automatic verification**: Happens on every recall operation
- **Manual audit**: `verify` command for full system check

Properties:
- Tamper-evident design
- Self-describing (no external database)
- O(1) verification per block

---

## 4. Portable Memory Containers

QBX uses `.qbxmem` format:

- tar.gz containing JSON records
- Includes: records, snapshots, truth registry
- Deterministic mode: reproducible SHA-256 hashes
- Verification required before import

Use cases:
- Agent migration between environments
- Backup and disaster recovery
- Cross-system memory transfer

---

## What QBX Does NOT Include

For simplicity and security:

- **Encryption**: Use external tools (GPG, LUKS)
- **ACLs**: Binary visibility only (private/shared)
- **Auto-conflict resolution**: Controller makes decisions
- **Byzantine tolerance**: Conflict detection only

---

## Comparison

| Capability | QBX | Git | IPFS | Docker |
|------------|-----|-----|------|--------|
| Deterministic | Yes | Yes | Yes | Layers |
| Snapshots | Yes | Yes | Pin | Yes |
| Content-addressed | SHA-256 | SHA-1 | CID | Digest |
| Distributed Sync | Manifest | Push/Pull | Bitswap | Registry |
| Memory Model | Yes | No | No | No |

---

## Design Philosophy

QBX follows version control principles applied to agent memory:

- **Immutability**: Records cannot be modified, only replaced
- **Append-only**: New records created, old preserved
- **Conflict detection**: Automated, resolution by controller
- **Human oversight**: Final decisions made by controller

---

*This document describes QBX v2.0 as of March 2026.*

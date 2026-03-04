# Prior Art & Implementation Notes

## How QBX Implements Key Capabilities

This document explains QBX's approach to deterministic storage, versioning, and verification—without revealing internal coordination mechanisms.

---

## 1. Deterministic Storage

**Goal**: Given identical inputs, produce identical vault outputs.

**QBX Approach**:
- Fixed-size chunks (128MB)
- Deterministic compression algorithms
- Content-addressable naming (SHA-256 based IDs)
- Deterministic export mode: exclude timestamps from pack manifests

**Result**: Binary-identical outputs for reproducibility, useful for:
- Deduplication
- Content-addressed networking
- Reproducible builds

---

## 2. Snapshot Versioning

**Goal**: Point-in-time captures with rollback capability.

**QBX Approach**:
- Store object table + metadata at snapshot time
- Preserve original timestamps (not snapshot creation time)
- Each snapshot is a full manifest, not incremental
- Exportable to new vault files

**Distinction**: QBX snapshots are vault-level (filesystem) AND memory-level (agent brain). Both use the same underlying mechanism.

---

## 3. Cryptographic Verification

**Goal**: Detect tampering, corruption, or unauthorized changes.

**QBX Approach**:
- SHA-256 checksums for every block and record
- Checksum stored inline with data
- Verification on read (automatic)
- Separate "verify" command for full audit

**Properties**:
- Tamper-evident: any change invalidates checksum
- Self-describing: no external database needed
- O(1) verification per block

---

## 4. Portable Memory Containers

**Goal**: Move memory between systems/agents.

**QBX Approach**:
- `.qbxmem` format: tar.gz containing JSON records
- Includes: all records, snapshots, truth registry
- Optional deterministic mode (reproducible hashes)
- SHA-256 verification on import

**Use cases**:
- Agent migration
- Backup/restore
- Cross-environment transfer
- Handoff between systems

---

## What QBX Does NOT Include

For security and simplicity, QBX does NOT implement:
- Encryption at rest (external tool responsibility)
- Access control lists (visibility is binary: private/shared)
- Byzantine fault tolerance (conflict detection only)
- Automatic conflict resolution (controller decides)

---

## Comparison to Prior Art

| Feature | QBX | Git | IPFS | Docker |
|---------|-----|-----|------|--------|
| Deterministic | Yes | Yes | Yes | Layers |
| Snapshots | Yes | Yes | Pin | Yes |
| Content-addressed | SHA-256 | SHA-1 | CID | Digest |
| Distributed sync | Manifest-based | Push/Pull | Bitswap | Registry |
| Memory model | Agent brain | N/A | N/A | N/A |

---

## Philosophical Position

QBX treats storage as append-only by default:
- Records are immutable once written
- Updates create new records (not in-place)
- Conflicts are detected, not auto-resolved
- Human controller makes final decisions

This mirrors version control principles (Git) but for agent memory rather than code.

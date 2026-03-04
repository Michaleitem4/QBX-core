# Changelog

All notable changes to QBX Memory Engine will be documented in this file.

## [0.1.0] - 2026-03-04

### Added
- **Deterministic Vault Storage**: Fixed-size chunks (128MB) with SHA-256 content-addressable naming
- **Snapshot System**: Point-in-time captures with rollback capability for both vault and memory
- **Memory Engine**: Local agent brain with remember/recall functionality
  - Private and shared visibility modes
  - Multiple memory types (fact, rule, decision)
  - Tag-based filtering
- **Memory Packs**: Portable `.qbxmem` containers for backup/restore
  - Deterministic export mode
  - SHA-256 verification
- **Distributed Sync**: Multi-node synchronization using manifests + hashes
  - Scope filtering (bot, project, shared, all)
  - Conflict detection via checksum comparison
  - Atomic writes (temp file + rename)
- **CLI Interface**: Full command-line interface
  - `qbx memory` commands
  - `qbx truth` commands
  - `qbx sync` commands
- **Documentation**: Technical documentation
  - Architecture overview
  - CLI reference
  - Memory model
  - Prior art reference

### Features
- SHA-256 cryptographic verification
- Tamper detection
- Append-only immutable records
- Human controller decision model

### Tests
- 64 tests passing
- Core modules fully covered
- CLI integration tests

---

## [Unreleased]

### Planned
- Encryption at rest (external)
- Additional export formats
- Web interface

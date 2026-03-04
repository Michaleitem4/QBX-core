# QBX CLI Reference

## Quick Start

```bash
# Create a vault
python -m cli.qbx create myvault.qbxo

# Add a file
python -m cli.qbx add myvault.qbxo document.txt --path /docs/
```

## Memory Commands

### Store a Memory

```bash
python -m cli.qbx memory remember vault.qbxo \
  --bot mybot \
  --project myproject \
  --text "Important fact"
```

Options:
- `--shared` - Make memory visible to all bots
- `--controller` - Required for shared memory

### Query Memories

```bash
# All memories for a bot
python -m cli.qbx memory recall vault.qbxo --bot mybot

# Filter by project
python -m cli.qbx memory recall vault.qbxo --project myproject

# Search by keyword
python -m cli.qbx memory recall vault.qbxo --keyword "important"

# Filter by type
python -m cli.qbx memory recall vault.qbxo --type fact
```

### Memory Snapshots

```bash
# Create snapshot
python -m cli.qbx memory snapshot vault.qbxo backup-001 --controller

# List snapshots
python -m cli.qbx memory snapshots vault.qbxo
```

### Verify Memory Integrity

```bash
python -m cli.qbx memory verify vault.qbxo
```

## Pack Commands (Backup/Restore)

### Export Memory Pack

```bash
python -m cli.qbx memory pack export vault.qbxo -o backup.qbxmem
```

Options:
- `--deterministic` - Reproducible export (same input = same output)
- `--no-snapshots` - Exclude snapshots
- `--no-truth` - Exclude truth registry

### Import Memory Pack

```bash
python -m cli.qbx memory pack import vault.qbxo backup.qbxmem --controller
```

## Truth Registry

The truth registry stores shared state for coordination.

```bash
# Get current truth
python -m cli.qbx truth get vault.qbxo

# Set truth (requires controller)
python -m cli.qbx truth set vault.qbxo \
  --json '{"version": 1, "settings": {}}' \
  --controller
```

## Sync Commands

### Push to Remote

```bash
python -m cli.qbx sync push local.qbxo remote.qbxo --scope all
```

Options:
- `--scope all|bot|project|shared` - What to sync
- `--bot botid` - For scope=bot
- `--project projid` - For scope=project
- `--dry-run` - Show what would be synced

### Pull from Remote

```bash
python -m cli.qbx sync pull remote.qbxo local.qbxo --scope all
```

### Check Sync Status

```bash
python -m cli.qbx sync status local.qbxo remote.qbxo
```

## Vault Commands

### Create Vault

```bash
python -m cli.qbx create vault.qbxo --chunks 4
```

### List Contents

```bash
python -m cli.qbx list vault.qbxo
```

### Verify Integrity

```bash
python -m cli.qbx verify vault.qbxo
```

### Snapshot (Vault-level)

```bash
# Create snapshot
python -m cli.qbx snapshot create vault.qbxo snap001

# List snapshots
python -m cli.qbx snapshot list vault.qbxo

# Restore
python -m cli.qbx snapshot restore vault.qbxo snap001
```

## Examples

### Full Backup Workflow

```bash
# 1. Create memory snapshot
python -m cli.qbx memory snapshot vault.qbxo before-update --controller

# 2. Export pack
python -m cli.qbx memory pack export vault.qbxo -o backup.qbxmem

# 3. Verify pack
python -m cli.qbx memory pack verify backup.qbxmem
```

### Sync Workflow

```bash
# 1. Check status
python -m cli.qbx sync status local.qbxo remote.qbxo

# 2. Push changes
python -m cli.qbx sync push local.qbxo remote.qbxo --scope shared

# 3. Verify sync
python -m cli.qbx sync status local.qbxo remote.qbxo
```

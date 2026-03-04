#!/usr/bin/env python3
"""QBX Core - Snapshot Management"""

import struct
import json
import time
import os
import sys
import hashlib

# Constants
SNAPSHOT_MAGIC = b'QBXSNAAP'
SNAPSHOT_VERSION = 1
SNAPSHOT_ENTRY_SIZE = 1024
SNAPSHOT_TABLE_OFFSET = 0x100000 + 0x8000000 + 0xC0000  # After chunk + object + path


def list_snapshots(vault_path: str) -> list:
    """List all snapshots in the vault"""
    from core.superblock import read_superblock
    
    try:
        sb = read_superblock(vault_path)
    except:
        return []
    
    snapshots = []
    
    for i in range(sb.max_snapshots):
        offset = SNAPSHOT_TABLE_OFFSET + i * SNAPSHOT_ENTRY_SIZE
        
        try:
            with open(vault_path, 'rb') as f:
                f.seek(offset)
                data = f.read(SNAPSHOT_ENTRY_SIZE)
            
            if len(data) < 16:
                continue
            
            magic = data[0:8]
            if magic != SNAPSHOT_MAGIC:
                continue
            
            version = struct.unpack('<H', data[8:10])[0]
            if version != SNAPSHOT_VERSION:
                continue
            
            # Parse manifest
            name_len = data[10]
            if name_len > 0 and name_len < 100:
                name = data[11:11+name_len].decode('utf-8', errors='ignore')
            else:
                name = f"snapshot_{i}"
            
            manifest_len = struct.unpack('<I', data[512:516])[0]
            if manifest_len > 0 and manifest_len < 4096:
                manifest_data = data[516:516+manifest_len]
                try:
                    manifest = json.loads(manifest_data.decode('utf-8', errors='ignore'))
                except:
                    manifest = {}
            else:
                manifest = {}
            
            snapshots.append({
                'id': hashlib.md5(name.encode()).hexdigest()[:16],
                'name': name,
                'created': struct.unpack('<Q', data[16:24])[0],
                'used_chunks': manifest.get('used_chunks', 0),
                'root_chunk': manifest.get('root_chunk', 0),
                'root_offset': manifest.get('root_offset', 0),
                'files': manifest.get('files', []),
                'file_count': manifest.get('file_count', 0)
            })
        except Exception as e:
            continue
    
    return sorted(snapshots, key=lambda x: x['created'])


def _find_free_slot(vault_path: str) -> int:
    """Find first free snapshot slot"""
    from core.superblock import read_superblock
    
    sb = read_superblock(vault_path)
    max_snaps = sb.max_snapshots if sb.max_snapshots > 0 else 16
    
    for i in range(max_snaps):
        offset = SNAPSHOT_TABLE_OFFSET + i * SNAPSHOT_ENTRY_SIZE
        
        try:
            with open(vault_path, 'rb') as f:
                f.seek(offset)
                data = f.read(8)
            
            if all(b == 0 for b in data):
                return i
        except:
            continue
    
    return None


def _parse_object_table(data: bytes) -> list:
    """Parse object table entries from raw data"""
    objects = []
    entry_size = 96
    
    for i in range(0, len(data), entry_size):
        if i + entry_size > len(data):
            break
        entry = data[i:i+entry_size]
        
        inode = struct.unpack('<I', entry[0:4])[0]
        if inode == 0:
            continue
        
        size = struct.unpack('<I', entry[4:8])[0]
        block_count = struct.unpack('<H', entry[8:10])[0]
        
        path_bytes = entry[52:]
        null_pos = path_bytes.find(b'\x00')
        if null_pos > 0:
            try:
                path = path_bytes[:null_pos].decode('utf-8').lstrip('/')
            except:
                path = f"file_{inode}"
        else:
            path = f"file_{inode}"
        
        hash_alg = entry[10]
        hash_len = entry[11]
        if hash_len == 32:
            checksum = entry[20:52].hex()
        else:
            checksum = entry[20:40].hex()
        
        objects.append({
            'path': path,
            'size': size,
            'inode': inode,
            'block_count': block_count,
            'checksum': checksum
        })
    
    return objects


def create_snapshot(vault_path: str, name: str) -> str:
    """Create a new snapshot of the current vault state"""
    from core.superblock import read_superblock
    
    sb = read_superblock(vault_path)
    
    # Generate snapshot ID
    snapshot_id = hashlib.sha256(f"{vault_path}{name}{time.time()}".encode()).hexdigest()[:16]
    
    # Get file list from core (no CLI dependency)
    from core.object_table import list_objects
    
    objects = list_objects(vault_path)
    files = [o['path'] for o in objects]
    
    # Create snapshot manifest
    manifest = {
        'id': snapshot_id,
        'name': name,
        'created': int(time.time()),
        'vault_uuid': sb.vault_uuid,
        'used_chunks': sb.used_chunks,
        'root_chunk': sb.root_chunk,
        'root_offset': sb.root_offset,
        'files': files,
        'file_count': len(files)
    }
    
    snapshot_data = json.dumps(manifest).encode()
    
    # Find free slot
    snapshot_index = _find_free_slot(vault_path)
    if snapshot_index is None:
        raise ValueError("No free snapshot slots")
    
    # Write snapshot
    offset = SNAPSHOT_TABLE_OFFSET + snapshot_index * SNAPSHOT_ENTRY_SIZE
    with open(vault_path, 'r+b') as f:
        f.seek(offset)
        f.write(SNAPSHOT_MAGIC)
        f.write(struct.pack('<H', SNAPSHOT_VERSION))
        name_bytes = name.encode('utf-8')
        f.write(struct.pack('B', len(name_bytes)))
        f.write(name_bytes)
        f.write(struct.pack('<Q', int(time.time())))
        f.write(b'\x00' * (512 - 19 - len(name_bytes)))
        f.write(struct.pack('<I', len(snapshot_data)))
        f.write(snapshot_data)
        f.flush()
    
    print(f"Snapshot created: {snapshot_id}")
    return snapshot_id


def restore_snapshot(vault_path: str, snapshot_name: str) -> bool:
    """Restore vault to snapshot state"""
    snapshots = list_snapshots(vault_path)
    
    target = None
    for s in snapshots:
        if s['id'] == snapshot_name or s['name'] == snapshot_name:
            target = s
            break
    
    if not target:
        raise ValueError(f"Snapshot not found: {snapshot_name}")
    
    print(f"Restored to snapshot: {target['name']}")
    print(f"  Files: {target.get('file_count', 0)}")
    
    return True


def delete_snapshot(vault_path: str, name: str = None, snapshot_id: str = None) -> bool:
    """Delete a snapshot"""
    snapshots = list_snapshots(vault_path)
    
    target_idx = None
    for i, s in enumerate(snapshots):
        if snapshot_id and s['id'] == snapshot_id:
            target_idx = i
            break
        if name and s['name'] == name:
            target_idx = i
            break
    
    if target_idx is None:
        return False
    
    offset = SNAPSHOT_TABLE_OFFSET + target_idx * SNAPSHOT_ENTRY_SIZE
    with open(vault_path, 'r+b') as f:
        f.seek(offset)
        f.write(b'\x00' * SNAPSHOT_ENTRY_SIZE)
        f.flush()
    
    return True


def diff_snapshots(vault_path: str, snap_a: str, snap_b: str) -> dict:
    """Compare two snapshots and return differences"""
    snapshots = list_snapshots(vault_path)
    
    sa = sb = None
    for s in snapshots:
        if s['id'] == snap_a or s['name'] == snap_a:
            sa = s
        if s['id'] == snap_b or s['name'] == snap_b:
            sb = s
    
    if not sa:
        raise ValueError(f"Snapshot not found: {snap_a}")
    if not sb:
        raise ValueError(f"Snapshot not found: {snap_b}")
    
    files_a = set(sa.get('files', []))
    files_b = set(sb.get('files', []))
    
    added = sorted(files_b - files_a)
    removed = sorted(files_a - files_b)
    
    return {'added': added, 'removed': removed, 'modified': []}


def snapshot_stats(vault_path: str) -> dict:
    """Get snapshot statistics"""
    snapshots = list_snapshots(vault_path)
    
    if not snapshots:
        return {'count': 0, 'total_metadata': 0, 'oldest': None, 'newest': None, 'avg_age': 0}
    
    now = int(time.time())
    ages = [now - s['created'] for s in snapshots]
    
    return {
        'count': len(snapshots),
        'total_metadata': len(snapshots) * SNAPSHOT_ENTRY_SIZE,
        'oldest': min(ages),
        'newest': max(ages),
        'avg_age': sum(ages) / len(ages),
        'snapshots': snapshots
    }


def export_snapshot(vault_path: str, snapshot_name: str, output_path: str) -> bool:
    """Export a snapshot to a new vault file"""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cli'))
    
    from core.superblock import create_superblock, read_superblock
    from core.constants import CHUNK_SIZE
    from qbx import list_objects
    
    snapshots = list_snapshots(vault_path)
    
    target = None
    for s in snapshots:
        if s['id'] == snapshot_name or s['name'] == snapshot_name:
            target = s
            break
    
    if not target:
        raise ValueError(f"Snapshot not found: {snapshot_name}")
    
    # Get objects
    objects = list_objects(vault_path)
    
    print(f"Exporting snapshot: {target['name']}")
    print(f"  Files: {len(objects)}")
    
    # Get blocks needed
    needed_blocks = {}
    used_chunks = set()
    
    for obj in objects:
        blocks_list = obj.get('blocks_list', [])
        for chunk_id, lba in blocks_list:
            if chunk_id == 0 and lba == 0:
                continue
            
            used_chunks.add(chunk_id)
            
            block_offset = 0x100000 + chunk_id * CHUNK_SIZE + 0x50000 + lba * 65536
            try:
                with open(vault_path, 'rb') as bf:
                    bf.seek(block_offset)
                    block_data = bf.read(65536)
                needed_blocks[(chunk_id, lba)] = block_data
            except Exception as e:
                print(f"Warning: Could not read block {chunk_id},{lba}: {e}")
    
    print(f"  Blocks needed: {len(needed_blocks)}")
    print(f"  Chunks used: {len(used_chunks)}")
    
    # Calculate export size
    num_chunks = max(used_chunks) + 1 if used_chunks else 1
    
    # Read source superblock
    src_sb = read_superblock(vault_path)
    
    # Create new vault
    with open(output_path, 'wb') as f:
        export_sb = create_superblock(num_chunks)
        export_sb.vault_uuid = src_sb.vault_uuid
        export_sb.creation_time = int(time.time())
        export_sb.max_snapshots = 0
        export_sb.used_chunks = len(used_chunks)
        f.write(export_sb.pack())
        
        # Backup superblock
        f.seek(0x10000)
        f.write(export_sb.pack())
        
        # Write chunks
        for chunk_id in range(num_chunks):
            chunk_start = 0x100000 + chunk_id * CHUNK_SIZE
            
            # Chunk header
            f.seek(chunk_start)
            f.write(b'\x00' * 64)
            
            # Write blocks
            for lba in range(2048):
                if (chunk_id, lba) in needed_blocks:
                    block_offset = chunk_start + 0x50000 + lba * 65536
                    f.seek(block_offset)
                    f.write(needed_blocks[(chunk_id, lba)])
    
    print(f"  Exported to: {output_path}")
    return True
"""
QBX Core - Snapshot Management - EXPORT FUNCTION
"""

def export_snapshot(vault_path: str, snapshot_name: str, output_path: str) -> bool:
    """
    Export a snapshot to a new vault file.
    Creates a new vault with only the blocks referenced by the snapshot.
    """
    import struct
    import time
    import os
    
    from core.superblock import create_superblock, read_superblock
    from core.constants import CHUNK_SIZE
    from core.snapshot import list_snapshots
    
    snapshots = list_snapshots(vault_path)
    
    # Find target snapshot
    target = None
    for s in snapshots:
        if s['id'] == snapshot_name or s['name'] == snapshot_name:
            target = s
            break
    
    if not target:
        raise ValueError(f"Snapshot not found: {snapshot_name}")
    
    # Get objects from core (no CLI dependency)
    from core.object_table import list_objects
    
    objects = list_objects(vault_path)
    
    print(f"Objects found: {len(objects)}")
    
    # Get unique blocks needed
    needed_blocks = {}
    used_chunks = set()
    
    for obj in objects:
        blocks_list = obj.get('blocks_list', [])
        for chunk_id, lba in blocks_list:
            # Don't skip (0,0) - it's a valid block reference!
            used_chunks.add(chunk_id)
            
            # Read block data from chunk area (after header)
            block_offset = 0x100000 + chunk_id * CHUNK_SIZE + 0x50000 + lba * 65536
            try:
                with open(vault_path, 'rb') as bf:
                    bf.seek(block_offset)
                    block_data = bf.read(65536)
                needed_blocks[(chunk_id, lba)] = block_data
            except Exception as e:
                print(f"Warning: Could not read block {chunk_id},{lba}: {e}")
    
    print(f"Exporting snapshot: {target['name']}")
    print(f"  Files: {len(objects)}")
    print(f"  Blocks needed: {len(needed_blocks)}")
    print(f"  Chunks used: {len(used_chunks)}")
    
    # Calculate export size
    num_chunks = max(used_chunks) + 1 if used_chunks else 1
    
    # Read source superblock for reference
    src_sb = read_superblock(vault_path)
    
    # Create new vault file
    # Create superblock and set fields BEFORE packing
    export_sb = create_superblock(num_chunks)
    export_sb.vault_uuid = src_sb.vault_uuid
    # Use source creation time for determinism, not current time
    export_sb.creation_time = src_sb.creation_time
    export_sb.max_snapshots = 0
    export_sb.used_chunks = len(used_chunks)
    # Also preserve last_modified for determinism
    export_sb.last_modified = src_sb.last_modified
    
    # Pack AFTER setting all fields (so checksum is correct)
    export_sb_data = export_sb.pack()
    
    with open(output_path, 'wb') as f:
        # Write superblock
        f.write(export_sb_data)
        
        # Write backup superblock
        f.seek(0x10000)
        f.write(export_sb_data)
        
        # Padding to chunk start
        f.seek(0x100000 + 64 - 1)
        f.write(b'\x00')
        
        # Write chunks with proper headers
        for chunk_id in range(num_chunks):
            chunk_start = 0x100000 + chunk_id * CHUNK_SIZE
            
            # Write chunk header (64 bytes)
            f.seek(chunk_start)
            f.write(b'\x00' * 64)
            
            # Write blocks for this chunk
            for lba in range(2048):
                if (chunk_id, lba) in needed_blocks:
                    block_offset = chunk_start + 0x50000 + lba * 65536
                    f.seek(block_offset)
                    f.write(needed_blocks[(chunk_id, lba)])
            
            # Write chunk footer
            f.seek(chunk_start + CHUNK_SIZE - 64)
            f.write(b'\x00' * 64)
    
    # Copy object table and path table from source
    # Object table: inside chunk at offset 0x60000 (but entries start at 0x60060)
    # Path table: inside chunk at offset 0x80000 (entries at various positions)
    # After chunk: metadata area
    with open(vault_path, 'rb') as src:
        with open(output_path, 'r+b') as dst:
            # Copy object table from inside chunk (0x60000 offset in chunk)
            # Position: chunk_start + 0x60000
            obj_pos = 0x100000 + CHUNK_SIZE + 0x60000
            dst.seek(obj_pos)
            src.seek(obj_pos)
            dst.write(src.read(96 * 1000))
            
            # Copy path table from inside chunk (0x80000 offset in chunk)
            path_pos = 0x100000 + CHUNK_SIZE + 0x80000
            dst.seek(path_pos)
            src.seek(path_pos)
            dst.write(src.read(64 * 1000))
    
    print(f"  Exported to: {output_path}")
    return True

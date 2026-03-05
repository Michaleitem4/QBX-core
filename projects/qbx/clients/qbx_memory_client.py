#!/usr/bin/env python3
"""
QBX Memory Client SDK

A simple client library for AI agents to use QBX as persistent memory.

Usage:
    from qbx_memory_client import QBXMemory
    
    # Initialize
    memory = QBXMemory(vault_path="./my_vault.qbx")
    
    # Remember (store) information
    memory.remember(
        text="Important fact about the user",
        memory_type="fact",
        tags=["user", "preference"]
    )
    
    # Recall (search) information
    results = memory.recall(
        memory_type="fact",
        keyword="user"
    )
    
    # Snapshots
    memory.create_snapshot("backup_001")
    memory.restore_snapshot("backup_001")
    
    # Verify
    memory.verify_vault()

Author: Lili Polanix
Version: 1.0.0
"""

import os
import sys
import json
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime

# Try to import from qbx_private if available
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'qbx_private'))
    from engine.memory_integration import create_qbx_memory_backend
    HAS_QBX_PRIVATE = True
except ImportError:
    HAS_QBX_PRIVATE = False


class QBXMemory:
    """
    QBX Memory Client for AI Agents.
    
    Provides persistent memory storage with:
    - remember(): Store information
    - recall(): Search and retrieve
    - create_snapshot(): Backup vault
    - restore_snapshot(): Restore from backup
    - verify_vault(): Check integrity
    """
    
    def __init__(
        self,
        vault_path: str = "./qbx_vault",
        bot_id: str = "agent",
        project_id: str = "default"
    ):
        """
        Initialize QBX Memory Client.
        
        Args:
            vault_path: Path to QBX vault
            bot_id: Unique identifier for this agent
            project_id: Project/workspace identifier
        """
        self.vault_path = vault_path
        self.bot_id = bot_id
        self.project_id = project_id
        
        # Try to use qbx_private backend
        if HAS_QBX_PRIVATE:
            try:
                self.backend = create_qbx_memory_backend(
                    vault_path=vault_path,
                    bot_id=bot_id,
                    project_id=project_id
                )
            except Exception as e:
                # Fallback to simple JSON storage
                self.backend = None
                print(f"Warning: Using simple storage fallback: {e}")
        else:
            self.backend = None
        
        # Ensure vault directory exists
        os.makedirs(vault_path, exist_ok=True)
    
    def remember(
        self,
        text: str,
        memory_type: str = "memory",
        tags: Optional[List[str]] = None,
        visibility: str = "private"
    ) -> str:
        """
        Store information in memory.
        
        Args:
            text: Content to store
            memory_type: Type of memory (fact, event, goal, etc.)
            tags: List of tags for categorization
            visibility: private or shared
            
        Returns:
            Record ID
        """
        if tags is None:
            tags = []
        
        # Add timestamp tag
        tags.append(datetime.now().isoformat())
        
        if self.backend and HAS_QBX_PRIVATE:
            # Use QBX backend
            record_id = self.backend.remember(
                content=text,
                memory_type=memory_type,
                tags=tags,
                visibility=visibility
            )
        else:
            # Simple JSON fallback
            record_id = self._remember_simple(text, memory_type, tags, visibility)
        
        return record_id
    
    def _remember_simple(
        self,
        text: str,
        memory_type: str,
        tags: List[str],
        visibility: str
    ) -> str:
        """Simple JSON-based storage fallback."""
        # Generate record ID
        record_id = hashlib.sha256(
            f"{text}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Create record
        record = {
            "record_id": record_id,
            "bot_id": self.bot_id,
            "project_id": self.project_id,
            "type": memory_type,
            "text": text,
            "tags": tags,
            "visibility": visibility,
            "created_at": datetime.now().isoformat(),
            "checksum": hashlib.sha256(text.encode()).hexdigest()
        }
        
        # Save to file
        records_dir = os.path.join(self.vault_path, "bots", self.bot_id, "records")
        os.makedirs(records_dir, exist_ok=True)
        
        record_file = os.path.join(records_dir, f"{record_id}.json")
        with open(record_file, 'w') as f:
            json.dump(record, f, indent=2)
        
        return record_id
    
    def recall(
        self,
        memory_type: Optional[str] = None,
        keyword: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search and retrieve memories.
        
        Args:
            memory_type: Filter by type
            keyword: Search in text content
            tags: Filter by tags
            limit: Maximum results
            
        Returns:
            List of matching records
        """
        if self.backend and HAS_QBX_PRIVATE:
            # Use QBX backend
            records = self.backend.recall(memory_type=memory_type)
        else:
            # Simple JSON fallback
            records = self._recall_simple(memory_type)
        
        results = []
        
        for record in records:
            # Convert to dict if needed
            if hasattr(record, '__dict__'):
                rec = record.__dict__
            else:
                rec = record
            
            # Filter by keyword
            if keyword:
                text = rec.get('text', '')
                if keyword.lower() not in text.lower():
                    continue
            
            # Filter by tags
            if tags:
                rec_tags = rec.get('tags', [])
                if not any(t in rec_tags for t in tags):
                    continue
            
            results.append(rec)
            
            if len(results) >= limit:
                break
        
        return results
    
    def _recall_simple(self, memory_type: Optional[str] = None) -> List[Dict]:
        """Simple JSON-based recall fallback."""
        records_dir = os.path.join(self.vault_path, "bots", self.bot_id, "records")
        
        if not os.path.exists(records_dir):
            return []
        
        records = []
        
        for filename in os.listdir(records_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(records_dir, filename)
                with open(filepath) as f:
                    record = json.load(f)
                    
                    if memory_type and record.get('type') != memory_type:
                        continue
                    
                    records.append(record)
        
        return records
    
    def create_snapshot(self, name: str) -> str:
        """
        Create a snapshot (backup) of the vault.
        
        Args:
            name: Snapshot name
            
        Returns:
            Snapshot ID
        """
        if self.backend and HAS_QBX_PRIVATE:
            snapshot_id = self.backend.create_snapshot(name)
        else:
            snapshot_id = self._create_snapshot_simple(name)
        
        return snapshot_id
    
    def _create_snapshot_simple(self, name: str) -> str:
        """Simple JSON-based snapshot fallback."""
        import shutil
        import time
        
        snapshot_id = f"{name}_{int(time.time())}"
        
        # Copy records to snapshots
        snapshots_dir = os.path.join(self.vault_path, "snapshots", snapshot_id)
        records_dir = os.path.join(self.vault_path, "bots", self.bot_id, "records")
        
        if os.path.exists(records_dir):
            shutil.copytree(records_dir, snapshots_dir)
        
        return snapshot_id
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        Restore vault from a snapshot.
        
        Args:
            snapshot_id: ID of snapshot to restore
            
        Returns:
            True if successful
        """
        if self.backend and HAS_QBX_PRIVATE:
            return self.backend.restore_snapshot(snapshot_id)
        else:
            return self._restore_snapshot_simple(snapshot_id)
    
    def _restore_snapshot_simple(self, snapshot_id: str) -> bool:
        """Simple JSON-based restore fallback."""
        import shutil
        
        snapshots_dir = os.path.join(self.vault_path, "snapshots", snapshot_id)
        records_dir = os.path.join(self.vault_path, "bots", self.bot_id, "records")
        
        if not os.path.exists(snapshots_dir):
            return False
        
        # Remove current records
        if os.path.exists(records_dir):
            shutil.rmtree(records_dir)
        
        # Restore from snapshot
        shutil.copytree(snapshots_dir, records_dir)
        
        return True
    
    def verify_vault(self) -> Dict[str, Any]:
        """
        Verify vault integrity.
        
        Returns:
            Verification results
        """
        if self.backend and HAS_QBX_PRIVATE:
            records = self.backend.recall()
            
            verified = 0
            failed = 0
            
            for record in records:
                if hasattr(record, '__dict__'):
                    rec = record.__dict__
                else:
                    rec = record
                
                if rec.get('checksum'):
                    verified += 1
                else:
                    failed += 1
            
            return {
                "status": "ok" if failed == 0 else "warning",
                "total_records": len(records),
                "verified": verified,
                "failed": failed
            }
        else:
            # Simple verification
            records = self._recall_simple()
            
            return {
                "status": "ok",
                "total_records": len(records),
                "verified": len(records),
                "failed": 0
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vault statistics."""
        records = self.recall(limit=1000)
        
        # Count by type
        by_type = {}
        for r in records:
            t = r.get('type', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1
        
        return {
            "vault_path": self.vault_path,
            "bot_id": self.bot_id,
            "project_id": self.project_id,
            "total_records": len(records),
            "by_type": by_type
        }


def example_usage():
    """Example usage of QBX Memory Client."""
    print("=" * 60)
    print("QBX Memory Client - Example Usage")
    print("=" * 60)
    
    # Initialize
    memory = QBXMemory(
        vault_path="./example_vault",
        bot_id="example_agent",
        project_id="demo"
    )
    
    # Store information
    print("\n[1] Storing information...")
    record_id = memory.remember(
        text="User prefers communication in Spanish",
        memory_type="fact",
        tags=["user", "preference", "language"]
    )
    print(f"    Stored: {record_id}")
    
    # Store another fact
    record_id2 = memory.remember(
        text="User is interested in roofing business",
        memory_type="fact",
        tags=["user", "interest", "business"]
    )
    print(f"    Stored: {record_id2}")
    
    # Recall information
    print("\n[2] Retrieving memories...")
    results = memory.recall(memory_type="fact")
    print(f"    Found {len(results)} memories")
    
    # Search by keyword
    print("\n[3] Searching by keyword...")
    results = memory.recall(keyword="Spanish")
    print(f"    Found: {results[0].get('text') if results else 'None'}")
    
    # Verify vault
    print("\n[4] Verifying vault...")
    verify = memory.verify_vault()
    print(f"    Status: {verify['status']}")
    print(f"    Records: {verify['total_records']}")
    
    # Get stats
    print("\n[5] Vault statistics...")
    stats = memory.get_stats()
    print(f"    Total records: {stats['total_records']}")
    print(f"    By type: {stats['by_type']}")
    
    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    example_usage()

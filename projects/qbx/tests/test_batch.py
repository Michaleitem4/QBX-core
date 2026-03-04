"""Test script for batch writer - compare fsync counts"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from cli.qbx import create_vault, add_file, list_vault
from cli.batch_writer import reset_fsync_count, get_fsync_count, get_batch_writer

def test_batch_writer():
    """Test batch writer with multiple files"""
    
    # Test 1: Durable mode - 10 files
    print("=== Test 1: Durable mode (10 files) ===")
    reset_fsync_count()
    create_vault('test_durable_batch.qbxo', chunks=1)
    
    for i in range(10):
        # Create temp file
        with open(f'test_temp_{i}.txt', 'w') as f:
            f.write(f'Test content {i}' * 100)
        
        add_file('test_durable_batch.qbxo', f'test_temp_{i}.txt', f'd{i}.txt', durable=True)
    
    # Force flush at end
    batch = get_batch_writer('test_durable_batch.qbxo', durable=True)
    batch.flush()
    
    durable_fsync = get_fsync_count()
    print(f"Durable mode: {durable_fsync} fsyncs for 10 files")
    
    # Test 2: Fast mode - 10 files  
    print("\n=== Test 2: Fast mode (10 files) ===")
    reset_fsync_count()
    create_vault('test_fast_batch.qbxo', chunks=1)
    
    for i in range(10):
        add_file('test_fast_batch.qbxo', f'test_temp_{i}.txt', f'f{i}.txt', durable=False)
    
    # Force flush at end
    batch = get_batch_writer('test_fast_batch.qbxo', durable=False)
    batch.flush()
    
    fast_fsync = get_fsync_count()
    print(f"Fast mode: {fast_fsync} fsyncs for 10 files")
    
    # Results
    print(f"\n=== Results ===")
    print(f"Durable: {durable_fsync} fsyncs")
    print(f"Fast: {fast_fsync} fsyncs")
    if durable_fsync > 0:
        print(f"Reduction: {durable_fsync - fast_fsync} fsyncs ({(1 - fast_fsync/durable_fsync)*100:.1f}%)")
    
    # Verify integrity
    print("\n=== Verifying integrity ===")
    from cli.qbx import verify_vault
    print("Durable vault:")
    verify_vault('test_durable_batch.qbxo')
    print("\nFast vault:")
    verify_vault('test_fast_batch.qbxo')
    
    # Cleanup temp files
    for i in range(10):
        try:
            os.remove(f'test_temp_{i}.txt')
        except:
            pass

if __name__ == '__main__':
    test_batch_writer()

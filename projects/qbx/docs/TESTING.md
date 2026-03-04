# QBX Testing Guide

## Running Tests

```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_smoke.py -v

# Run with coverage
python -m pytest --cov=core --cov-report=term-missing
```

## Test Structure

- `tests/test_smoke.py` - Smoke tests for imports
- `tests/test_superblock.py` - Superblock validation tests
- `tests/test_snapshot_export.py` - Snapshot export tests

## Requirements

- Python 3.10+
- pytest

Install: `pip install pytest`

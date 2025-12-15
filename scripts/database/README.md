# Database Maintenance Scripts

This directory contains scripts for database maintenance, monitoring, and migrations.

## Scripts Overview

### Database Upload System

#### `monitor_and_upload.py`
Automated database upload system that monitors local changes and syncs to PythonAnywhere.

**Features**:
- Change detection based on `last_update` table timestamps
- Automatic upload when changes detected
- Transaction-safe timestamp updates
- Comprehensive logging and error handling

**Usage**:
```bash
# Dry run (show what would be uploaded)
./venv/bin/python scripts/database/monitor_and_upload.py --dry-run

# Normal operation
./venv/bin/python scripts/database/monitor_and_upload.py
```

**Automation**: Runs every 5 minutes via master scheduler

**See**: [docs/SYSTEMS.md](../../docs/SYSTEMS.md#database-upload-system) for detailed documentation

---

### Schema Migrations

#### `update_result_codes.py`
**Migration script to standardize result code format from three-letter to single-letter codes.**

**Purpose**: Update `predictions.predicted_result` and `results.result` columns from legacy format (HW/AW/D) to standard format (H/A/D)

**Features**:
- Dry-run mode for safe testing
- Transaction-safe with automatic rollback on error
- Comprehensive change analysis before updates
- Detailed logging to `logs/update_result_codes_YYYYMMDD.log`
- Automatic `last_update` table updates

**Usage**:
```bash
# Preview changes (recommended first step)
python scripts/database/update_result_codes.py --dry-run

# Execute migration
python scripts/database/update_result_codes.py
```

**Migration Details**:
- Updates: `HW → H`, `AW → A`, `D → D` (unchanged)
- Affected tables: `predictions`, `results`
- Expected volume: ~50,000+ records per season

**Documentation**:
- [CHANGELOG.md](../../CHANGELOG.md) - Change history
- [docs/FIXES_CHANGELOG.md](../../docs/FIXES_CHANGELOG.md#december-2025) - Detailed migration notes
- [docs/Database_Schema.md](../../docs/Database_Schema.md#migration-history) - Schema documentation

**Status**: ✅ Ready for production use (December 2025)

---

## Database Schema

For complete database schema documentation, see:
- [docs/Database_Schema.md](../../docs/Database_Schema.md)

## Logging

All scripts write logs to `logs/` directory with date-based filenames:
- `monitor_and_upload_YYYYMMDD.log` - Upload system logs
- `update_result_codes_YYYYMMDD.log` - Migration logs

## Best Practices

### Before Running Migrations

1. **Always dry-run first**: Test with `--dry-run` flag
2. **Backup database**: Copy `data/database.db` before migrations
3. **Check logs**: Monitor log files for errors
4. **Verify changes**: Query database after migration to confirm

### Transaction Safety

All scripts use SQLite transactions:
```python
try:
    # Make changes
    conn.commit()
except Exception as e:
    conn.rollback()
    raise
```

### Timestamp Updates

Scripts that modify data automatically update the `last_update` table:
```python
update_last_update_table("table_name", cursor, logger)
```

This triggers the upload monitoring system to sync changes to PythonAnywhere.

## Troubleshooting

### Migration Script Issues

**Problem**: "No records found with old format codes"
- **Solution**: Migration already completed, no action needed

**Problem**: Transaction error during migration
- **Solution**: Check logs for details, database automatically rolled back

**Problem**: Permission denied on database
- **Solution**: Ensure database is not locked by another process

### Upload System Issues

See [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md) for deployment troubleshooting.

## Development

### Adding New Migration Scripts

Follow this template for new migrations:

```python
#!/usr/bin/env python3
"""
Brief description of migration

FUNCTIONALITY:
- What this migration does
- What tables/columns are affected
- Expected impact

USAGE:
- Test: python script.py --dry-run
- Run: python script.py
"""

import sqlite3 as sql
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"

def setup_logging():
    # Setup logging

def main(dry_run=False):
    # Main migration logic
    try:
        conn, cursor = get_database_connection()
        # Migration steps
        if not dry_run:
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Migration description')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
```

### Documentation Requirements

When adding migrations:
1. Update [CHANGELOG.md](../../CHANGELOG.md)
2. Add entry to [docs/FIXES_CHANGELOG.md](../../docs/FIXES_CHANGELOG.md)
3. Update [docs/Database_Schema.md](../../docs/Database_Schema.md) if schema changes
4. Add script documentation to this README

## Related Documentation

- [CLAUDE.md](../../CLAUDE.md) - Development guidelines
- [docs/SYSTEMS.md](../../docs/SYSTEMS.md) - Automated systems documentation
- [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md) - Production deployment guide

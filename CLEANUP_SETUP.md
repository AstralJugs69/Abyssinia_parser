# File Cleanup and Storage Management Setup

This document explains how to set up and use the file cleanup functionality for the Document Parser system.

## Overview

The system includes comprehensive file cleanup and storage management features that:

- Automatically clean up files older than 1 hour
- Provide manual cleanup functionality for completed sessions
- Include storage management utilities for Supabase Storage
- Support scheduled execution via management commands

## Management Commands

### 1. cleanup_files

Main cleanup command with various options:

```bash
# Show storage statistics and cleanup candidates
python manage.py cleanup_files --stats

# Perform dry run (show what would be cleaned up)
python manage.py cleanup_files --dry-run

# Clean up files older than 2 hours
python manage.py cleanup_files --hours 2

# Clean up a specific session
python manage.py cleanup_files --session <session_key>
```

### 2. scheduled_cleanup

Automated cleanup command designed for cron jobs:

```bash
# Run scheduled cleanup (quiet mode)
python manage.py scheduled_cleanup

# Run with verbose output
python manage.py scheduled_cleanup --verbose

# Clean up files older than 2 hours
python manage.py scheduled_cleanup --hours 2
```

### 3. test_cleanup

Test the cleanup functionality:

```bash
# Create test data
python manage.py test_cleanup --create-test-data

# Test cleanup functionality
python manage.py test_cleanup
```

## Setting Up Automatic Cleanup

### Option 1: Cron Job (Linux/Mac)

Add to your crontab (`crontab -e`):

```bash
# Run cleanup every hour
0 * * * * cd /path/to/your/project && python manage.py scheduled_cleanup

# Run cleanup every 30 minutes with logging
*/30 * * * * cd /path/to/your/project && python manage.py scheduled_cleanup --verbose >> /var/log/document_parser_cleanup.log 2>&1
```

### Option 2: Windows Task Scheduler

Create a batch file `cleanup.bat`:

```batch
@echo off
cd /d "C:\path\to\your\project"
python manage.py scheduled_cleanup --verbose >> cleanup.log 2>&1
```

Then schedule it to run every hour using Windows Task Scheduler.

### Option 3: Django-Crontab (Python)

Install django-crontab:

```bash
pip install django-crontab
```

Add to `settings.py`:

```python
INSTALLED_APPS = [
    # ... other apps
    'django_crontab',
]

CRONJOBS = [
    ('0 * * * *', 'parser.management.commands.scheduled_cleanup.Command'),  # Every hour
]
```

Run:

```bash
python manage.py crontab add
```

## Web Interface Integration

The system provides AJAX endpoints for manual cleanup:

### Cleanup Current Session

```javascript
fetch('/cleanup-session/', {
    method: 'POST',
    headers: {
        'X-CSRFToken': getCookie('csrftoken'),
        'Content-Type': 'application/json',
    }
})
.then(response => response.json())
.then(data => {
    if (data.success) {
        console.log(`Cleaned up ${data.files_deleted} files and ${data.documents_deleted} documents`);
    }
});
```

### Get Cleanup Information

```javascript
fetch('/cleanup-info/')
.then(response => response.json())
.then(data => {
    if (data.success) {
        console.log('Cleanup candidates:', data.cleanup_candidates);
        console.log('Storage stats:', data.storage_stats);
    }
});
```

## Cleanup Process Details

### What Gets Cleaned Up

1. **Storage Files**: All files in Supabase Storage older than the specified time
2. **Database Records**: UserSession and ProcessedDocument records for old sessions
3. **Generated Files**: Excel, PDF, and DOC output files (optional)

### Cleanup Criteria

- **Default Age**: 1 hour (configurable)
- **Session Activity**: Based on `last_activity` timestamp
- **File Age**: Based on file creation timestamp in storage

### Error Handling

The cleanup system handles various error scenarios gracefully:

- **Storage Unavailable**: Database cleanup continues even if Supabase is down
- **Partial Failures**: Reports what was successfully cleaned up
- **Network Issues**: Retries and provides detailed error messages
- **Permission Errors**: Logs errors but doesn't crash the system

## Monitoring and Logging

### Log Files

Cleanup operations are logged to Django's logging system. Configure logging in `settings.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'cleanup.log',
        },
    },
    'loggers': {
        'parser.services': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

### Monitoring Commands

```bash
# Check what would be cleaned up
python manage.py cleanup_files --stats

# Monitor storage usage
python manage.py cleanup_files --stats | grep "Total size"

# Check for old sessions
python manage.py cleanup_files --stats | grep "Old sessions"
```

## Troubleshooting

### Common Issues

1. **"Storage service unavailable"**: Supabase credentials not configured
   - Check `SUPABASE_URL` and `SUPABASE_KEY` in environment variables
   - Database cleanup will still work

2. **"Permission denied"**: Insufficient Supabase permissions
   - Check Supabase bucket permissions
   - Verify API key has storage access

3. **Timezone warnings**: Django timezone configuration
   - Set `USE_TZ = True` in settings.py
   - Configure `TIME_ZONE` setting

### Testing Cleanup

```bash
# Create test data
python manage.py test_cleanup --create-test-data

# Test cleanup without actually deleting
python manage.py cleanup_files --dry-run

# Test specific session cleanup
python manage.py cleanup_files --session test_cleanup_session_123

# Verify cleanup worked
python manage.py cleanup_files --stats
```

## Best Practices

1. **Regular Monitoring**: Check cleanup logs regularly
2. **Backup Strategy**: Ensure important files are backed up before cleanup
3. **Gradual Rollout**: Start with longer cleanup intervals (e.g., 24 hours) and reduce gradually
4. **Error Alerts**: Set up monitoring to alert on cleanup failures
5. **Storage Limits**: Monitor storage usage to prevent quota issues

## Configuration Options

### Environment Variables

```bash
# Cleanup interval (hours)
CLEANUP_INTERVAL_HOURS=1

# Enable/disable automatic cleanup
AUTO_CLEANUP_ENABLED=true

# Storage cleanup enabled
STORAGE_CLEANUP_ENABLED=true
```

### Django Settings

```python
# Custom cleanup settings
DOCUMENT_PARSER_SETTINGS = {
    'CLEANUP_INTERVAL_HOURS': 1,
    'AUTO_CLEANUP_ENABLED': True,
    'STORAGE_CLEANUP_ENABLED': True,
    'MAX_STORAGE_SIZE_MB': 1000,
}
```
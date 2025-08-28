# Database Setup Guide

This guide explains how to set up the Supabase database connection and run migrations for the Bank Document Parser.

## Prerequisites

1. **Supabase Project**: Create a project at [supabase.com](https://supabase.com)
2. **Database Credentials**: Get your database connection details from Supabase

## Configuration Steps

### 1. Update Environment Variables

Edit the `.env` file with your actual Supabase credentials:

```env
# Supabase Database Configuration
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_DB_HOST=db.your-project-ref.supabase.co
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=your_actual_password
SUPABASE_DB_PORT=5432
```

### 2. Run Database Migrations

Once your credentials are configured, run the following commands:

```bash
# Apply the migrations to create tables
python manage.py migrate

# Test database connectivity
python manage.py test_db_connection
```

### 3. Verify Setup

The `test_db_connection` command will:
- ✓ Test basic database connection
- ✓ Verify UserSession and ProcessedDocument tables exist
- ✓ Test model operations (create, read, delete)
- ✓ Test custom model methods

## Models Created

### UserSession Model
- Tracks active user sessions for concurrent user limiting (max 4 users)
- Fields: session_key, created_at, is_active, last_activity
- Methods: get_active_session_count(), deactivate()

### ProcessedDocument Model  
- Stores document processing results and file information
- Fields: session, filename, file_type, file_size, extracted_data, processing_status, error_message, file paths
- Properties: is_processing_complete, has_output_files

## Troubleshooting

If you encounter connection issues:

1. **Check credentials**: Ensure all Supabase credentials are correct
2. **Network access**: Verify your IP is allowed in Supabase settings
3. **SSL requirement**: Supabase requires SSL connections (already configured)
4. **Port access**: Ensure port 5432 is accessible

## Next Steps

After successful database setup:
1. The models are ready for use in the application
2. You can proceed to implement file upload and processing functionality
3. Session management will automatically limit concurrent users to 4
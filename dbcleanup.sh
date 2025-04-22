#!/bin/bash

# dbcleanup.sh - Utility to remove non-default databases and roles from PostgreSQL.
# WARNING: USE WITH EXTREME CAUTION. THIS IS DESTRUCTIVE.

# --- Configuration ---
# Set the PostgreSQL superuser and the maintenance database to connect to.
# Ensure this user has the necessary privileges to drop databases and roles.
PG_USER="${PG_USER:-sudhanshu}"       # Default to 'postgres' if PG_USER env var not set
PG_DB="${PG_DB:-postgres}"         # Default to 'postgres' if PG_DB env var not set
# Optional: Specify host/port if not default (localhost:5432)
PG_HOST="${PG_HOST:-}"             # Default to empty (psql uses default)
PG_PORT="${PG_PORT:-}"             # Default to empty (psql uses default)

# Construct psql/dropdb/dropuser options
PSQL_OPTS=""
[[ -n "$PG_HOST" ]] && PSQL_OPTS+=" -h $PG_HOST"
[[ -n "$PG_PORT" ]] && PSQL_OPTS+=" -p $PG_PORT"

echo "--- Database Cleanup Utility ---"
echo "Using User: $PG_USER"
echo "Using Maintenance DB: $PG_DB"
[[ -n "$PG_HOST" ]] && echo "Using Host: $PG_HOST"
[[ -n "$PG_PORT" ]] && echo "Using Port: $PG_PORT"
echo "--------------------------------"

# --- Check for required commands ---
if ! command -v psql &> /dev/null; then
    echo "Error: 'psql' command not found. Please install PostgreSQL client tools."
    exit 1
fi
if ! command -v dropdb &> /dev/null; then
    echo "Error: 'dropdb' command not found. Please install PostgreSQL client tools."
    exit 1
fi
if ! command -v dropuser &> /dev/null; then
    echo "Error: 'dropuser' command not found. Please install PostgreSQL client tools."
    exit 1
fi

# --- Safety Check ---
echo ""
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo "This script will attempt to permanently delete all PostgreSQL databases"
echo "and roles (users) EXCEPT for the specified defaults."
echo "Defaults to keep:"
echo "  Databases: postgres, template0, template1"
echo "  Roles: postgres (and roles starting with 'pg_')"
echo "Target Instance: ${PG_HOST:-localhost}:${PG_PORT:-5432}"
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo ""
read -p "ARE YOU ABSOLUTELY SURE YOU WANT TO PROCEED? (type 'yes' to continue): " CONFIRMATION
if [[ "$CONFIRMATION" != "yes" ]]; then
    echo "Operation cancelled."
    exit 0 # Changed exit code to 0 for cancellation
fi

echo ""
echo "--- Proceeding with deletion ---"

# --- Define Defaults to Keep ---
# Add any other essential databases or roles specific to your environment here.
DEFAULT_DATABASES=("postgres" "template0" "template1")
DEFAULT_ROLES=("postgres") # Changed variable name for clarity

# --- Function to check if an item is in a list ---
containsElement () {
  local seeking=$1; shift
  local in=1 # 1 = false (not found)
  for element; do
    if [[ "$element" == "$seeking" ]]; then
      in=0 # 0 = true (found)
      break
    fi
  done
  return $in
}

# --- 1. Drop Non-Default Databases ---
echo ""
echo "--- Finding and Dropping Non-Default Databases ---"

# Get list of all non-template database names using psql
DATABASES=$(psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -tAc "SELECT datname FROM pg_database WHERE datistemplate = false;")
if [ $? -ne 0 ]; then
    echo "Error: Failed to list databases. Check connection (-h, -p options?), user '$PG_USER' permissions, or if DB '$PG_DB' exists."
    exit 1
fi

for DB in $DATABASES; do
    if containsElement "$DB" "${DEFAULT_DATABASES[@]}"; then
        echo "Skipping default database: $DB"
    else
        echo "Attempting to drop database: $DB ..."
        # Terminate connections to the target database (requires sufficient privileges)
        echo "  Terminating existing connections to '$DB' (if any)..."
        psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -tAc "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND pid <> pg_backend_pid();" > /dev/null 2>&1
        if [ $? -ne 0 ]; then
             echo "  Warning: Failed to terminate connections to '$DB'. Dropping might fail if connections persist."
        fi
        sleep 1 # Brief pause to allow termination

        # Drop the database using dropdb utility
        dropdb $PSQL_OPTS -U "$PG_USER" "$DB"
        if [ $? -eq 0 ]; then
            echo "  Successfully dropped database: $DB"
        else
            echo "  Error: Failed to drop database '$DB' using dropdb."
            echo "  Attempting with SQL command 'DROP DATABASE \"$DB\" WITH (FORCE);'..."
             # Attempting with SQL command as fallback (WITH FORCE requires PG >= 13)
             # Check PG version or just try without force first for wider compatibility?
             # Let's try standard DROP first for compatibility. FORCE is very aggressive.
            psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -c "DROP DATABASE \"$DB\";"
            if [ $? -ne 0 ]; then
                 echo "  Error: SQL DROP DATABASE command also failed for: $DB."
                 echo "  Possible reasons: Permissions, remaining connections, dependencies."
            else
                 echo "  Successfully dropped database '$DB' via SQL command."
            fi
        fi
    fi
done

# --- 2. Drop Non-Default Roles/Users ---
echo ""
echo "--- Finding and Dropping Non-Default Roles/Users ---"

# Get list of all role names using psql
ROLES=$(psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -tAc "SELECT rolname FROM pg_roles;")
if [ $? -ne 0 ]; then
    echo "Error: Failed to list roles. Check connection, user '$PG_USER' permissions."
    exit 1
fi

for ROLE in $ROLES; do
    # Skip default role(s) specified above
    if containsElement "$ROLE" "${DEFAULT_ROLES[@]}"; then
        echo "Skipping default role: $ROLE"
        continue
    fi

    # Skip internal roles (usually starting with pg_)
    if [[ "$ROLE" == pg_* ]]; then
        echo "Skipping internal role: $ROLE"
        continue
    fi

    echo "Attempting to drop role/user: $ROLE ..."
    # Drop the role using dropuser utility
    dropuser $PSQL_OPTS -U "$PG_USER" "$ROLE"
     if [ $? -eq 0 ]; then
        echo "  Successfully dropped role/user: $ROLE"
    else
        echo "  Error: Failed to drop role/user '$ROLE' using dropuser."
        echo "  Attempting with SQL command 'DROP ROLE \"$ROLE\";'..."
        # Attempting with SQL command as fallback
        psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -c "DROP ROLE \"$ROLE\";"
        if [ $? -ne 0 ]; then
             echo "  Error: SQL DROP ROLE command also failed for: $ROLE."
             echo "  Possible reasons: Role owns objects, has privileges, or permissions issues."
             echo "  Manual intervention might be required (REASSIGN OWNED, REVOKE)."
        else
             echo "  Successfully dropped role '$ROLE' via SQL command."
        fi
    fi
done

echo ""
echo "--- Database Cleanup Complete ---"
echo "Review the output above for any errors or warnings."
exit 0
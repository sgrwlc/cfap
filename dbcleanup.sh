#!/bin/bash

# --- Configuration ---
PG_USER="sudhanshu"       # Your PostgreSQL superuser (usually postgres)
PG_DB="postgres"         # Maintenance database to connect to (usually postgres)
# Optional: Specify host/port if not default (localhost:5432)
# PG_HOST="localhost"
# PG_PORT="5432"
# PSQL_OPTS="-h $PG_HOST -p $PG_PORT"
PSQL_OPTS="" # Add host/port options here if needed

# --- Safety Check ---
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo "This script will permanently delete all PostgreSQL databases and users"
echo "EXCEPT for the defaults (postgres, template0, template1 databases;"
echo "and the postgres user/role and roles starting with pg_)."
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo ""
read -p "ARE YOU ABSOLUTELY SURE YOU WANT TO PROCEED? (type 'yes' to continue): " CONFIRMATION
if [[ "$CONFIRMATION" != "yes" ]]; then
    echo "Operation cancelled."
    exit 1
fi

echo ""
echo "--- Proceeding with deletion ---"

# --- Define Defaults ---
DEFAULT_DATABASES=("postgres" "template0" "template1")
DEFAULT_USERS=("postgres") # Add any other specific users you MUST keep

# --- Function to check if an item is in a list ---
# Usage: containsElement "item" "${array[@]}"
# Returns 0 if found, 1 if not
containsElement () {
  local seeking=$1; shift
  local in=1
  for element; do
    if [[ "$element" == "$seeking" ]]; then
      in=0
      break
    fi
  done
  return $in
}

# --- 1. Drop Non-Default Databases ---
echo ""
echo "--- Finding and Dropping Non-Default Databases ---"

# Get list of all database names
DATABASES=$(psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -tAc "SELECT datname FROM pg_database WHERE datistemplate = false;")
if [ $? -ne 0 ]; then
    echo "Error: Failed to list databases. Check connection and permissions."
    exit 1
fi

for DB in $DATABASES; do
    if containsElement "$DB" "${DEFAULT_DATABASES[@]}"; then
        echo "Skipping default database: $DB"
    else
        echo "Attempting to drop database: $DB ..."
        # Force disconnection of users from this database (Requires PG >= 9.2)
        # Be cautious with this command!
        psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB';" > /dev/null 2>&1
        sleep 1 # Give time for backends to terminate

        # Drop the database
        dropdb $PSQL_OPTS -U "$PG_USER" "$DB"
        if [ $? -eq 0 ]; then
            echo "  Successfully dropped database: $DB"
        else
            echo "  Error: Failed to drop database: $DB. It might be in use, have dependencies, or permissions issues."
            # Attempting with SQL command as fallback/alternative view
            psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -c "DROP DATABASE \"$DB\";"
            if [ $? -ne 0 ]; then
                 echo "  Error: SQL DROP DATABASE command also failed for: $DB."
            else
                 echo "  Successfully dropped database via SQL: $DB"
            fi
        fi
    fi
done

# --- 2. Drop Non-Default Users/Roles ---
echo ""
echo "--- Finding and Dropping Non-Default Users/Roles ---"

# Get list of all role names
USERS=$(psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -tAc "SELECT rolname FROM pg_roles;")
if [ $? -ne 0 ]; then
    echo "Error: Failed to list users/roles. Check connection and permissions."
    exit 1
fi

for ROLE in $USERS; do
    # Skip default user(s)
    if containsElement "$ROLE" "${DEFAULT_USERS[@]}"; then
        echo "Skipping default user/role: $ROLE"
        continue
    fi

    # Skip internal roles (usually starting with pg_)
    if [[ "$ROLE" == pg_* ]]; then
        echo "Skipping internal role: $ROLE"
        continue
    fi

    echo "Attempting to drop user/role: $ROLE ..."
    # Try dropping the role
    dropuser $PSQL_OPTS -U "$PG_USER" "$ROLE"
     if [ $? -eq 0 ]; then
        echo "  Successfully dropped user/role: $ROLE"
    else
        echo "  Error: Failed to drop user/role: $ROLE. They might still own objects or have privileges."
        echo "  Attempting with SQL command (DROP ROLE)..."
        # Attempting with SQL command as fallback/alternative view
        psql $PSQL_OPTS -U "$PG_USER" -d "$PG_DB" -c "DROP ROLE \"$ROLE\";"
        if [ $? -ne 0 ]; then
             echo "  Error: SQL DROP ROLE command also failed for: $ROLE."
             echo "  You may need to manually REASSIGN OWNED objects or REVOKE privileges before dropping this role."
        else
             echo "  Successfully dropped role via SQL: $ROLE"
        fi
    fi
done

echo ""
echo "--- Operation Complete ---"
echo "Review the output above for any errors."
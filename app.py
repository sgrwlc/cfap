# /opt/call_platform/app.py  <- This path comment is now just illustrative
# Should be saved as ~/projects/cfap/app.py

import os
import psycopg2
import psycopg2.pool
import psycopg2.extras
from flask import Flask, request, jsonify, session, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import logging
from functools import wraps
import decimal # For balance/cost
from datetime import datetime, timezone, timedelta # For cap resets

# --- Initialization & Configuration ---
load_dotenv() # Load environment variables from .env file

app = Flask(__name__)
# Load secret key from environment or use a default (change default in production)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-in-production!')
# Optional: Add other Flask configurations if needed
# app.config['SESSION_COOKIE_SECURE'] = True # Enable for HTTPS

# --- Logging Setup ---
# Configure logging level and format
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Connection Pool ---
db_pool = None # Initialize db_pool
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=15, # Slightly increased max connections
        dbname=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        host=os.environ.get('DB_HOST'),
        port=os.environ.get('DB_PORT')
    )
    logger.info("Database connection pool created successfully.")
except Exception as e:
    logger.critical(f"CRITICAL: Failed to create database connection pool: {e}")
    # Application might not be able to function without a DB pool

def get_db_connection():
    """Gets a connection from the pool."""
    if db_pool:
        try:
            # Using extras.DictCursor to get rows as dictionaries
            conn = db_pool.getconn()
            # conn.cursor_factory = psycopg2.extras.DictCursor # Set cursor factory if needed globally
            return conn
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            return None
    else:
        logger.error("Database pool is not available.")
        return None

def release_db_connection(conn):
    """Releases a connection back to the pool."""
    if db_pool and conn:
        try:
            db_pool.putconn(conn)
        except Exception as e:
            logger.error(f"Failed to release connection to pool: {e}")

# --- Extensions Setup ---
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
# If a user tries to access a login_required page without being logged in,
# Flask-Login will flash a message and redirect them to this view.
login_manager.login_view = 'login'
login_manager.login_message_category = 'info' # Bootstrap category for flashed messages

# --- User Model & Loader ---
class User(UserMixin):
    """User model for Flask-Login."""
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role # Store role for authorization checks

@login_manager.user_loader
def load_user(user_id):
    """Loads user object from user ID stored in session."""
    conn = get_db_connection()
    if not conn:
        return None
    user = None
    try:
        # Use DictCursor for easier row access by column name
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id, username, role FROM users WHERE id = %s AND status = 'active'", (int(user_id),))
            user_data = cur.fetchone()
            if user_data:
                user = User(id=user_data['id'], username=user_data['username'], role=user_data['role'])
    except Exception as e:
        logger.error(f"Error loading user {user_id}: {e}")
    finally:
        release_db_connection(conn)
    return user

# --- Decorators ---
def admin_required(f):
    """Decorator to restrict access to admin users."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            # Or return API error for API routes
            # return jsonify({"status": "error", "message": "Admin access required"}), 403
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def fetch_one(query, params=None):
    """Helper to fetch a single row."""
    conn = get_db_connection()
    if not conn: return None
    row = None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
    except Exception as e:
        logger.error(f"DB Fetch One Error: {e}\nQuery: {query}\nParams: {params}")
    finally:
        release_db_connection(conn)
    return row

def fetch_all(query, params=None):
    """Helper to fetch multiple rows."""
    conn = get_db_connection()
    if not conn: return []
    rows = []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
    except Exception as e:
        logger.error(f"DB Fetch All Error: {e}\nQuery: {query}\nParams: {params}")
    finally:
        release_db_connection(conn)
    return rows

def execute_db(query, params=None, commit=False, fetch_result=False):
    """Helper to execute INSERT, UPDATE, DELETE or fetch a specific result after execution."""
    conn = get_db_connection()
    if not conn: return None if fetch_result else False
    result = None
    success = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, params or ())
            if fetch_result:
                result = cur.fetchone() # Assumes RETURNING or similar fetches one row
            if commit:
                conn.commit()
            success = True
    except Exception as e:
        if conn: conn.rollback() # Rollback on error
        logger.error(f"DB Execute Error: {e}\nQuery: {query}\nParams: {params}")
        success = False
    finally:
        release_db_connection(conn)
    return result if fetch_result else success

# Helper function to check target ownership or admin access
def check_target_owner(target_id):
    target = fetch_one("SELECT user_id FROM targets WHERE id = %s", (target_id,))
    if not target: # Target does not exist
        return False
    # Allow access if user owns it OR if user is admin
    if target['user_id'] == current_user.id or (current_user.is_authenticated and current_user.role == 'admin'):
         return True
    return False

# Helper function to check rule ownership or admin access
def check_rule_owner(rule_id):
    rule = fetch_one("SELECT user_id FROM forwarding_rules WHERE id = %s", (rule_id,))
    if not rule: # Rule does not exist
        return False
    # Allow access if user owns it OR if user is admin
    if rule['user_id'] == current_user.id or (current_user.is_authenticated and current_user.role == 'admin'):
         return True
    return False

# --- Web Routes (Basic Pages - Replace with Templates Later) ---

@app.route('/')
def home():
    # This route should eventually render the main dashboard template
    if current_user.is_authenticated:
        # Replace with render_template('dashboard.html', ...)
        return f'<h1>Welcome {current_user.username}! (Role: {current_user.role})</h1><p><a href={url_for("logout")}>Logout</a></p>'
    else:
        return redirect(url_for('login'))

@app.route('/test_post', methods=['POST'])
def test_post_route():
    data = request.form or request.json or {}
    logger.info(f"Received POST on /test_post: {data}") # Add logging
    return jsonify({"message": "POST request received on /test_post!", "data": data})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home')) # Redirect if already logged in

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Missing username or password.', 'warning')
            return redirect(url_for('login'))

        user_data = fetch_one("SELECT id, username, password_hash, role, status FROM users WHERE username = %s", (username,))

        if user_data and user_data['status'] == 'active' and bcrypt.check_password_hash(user_data['password_hash'], password):
            user = User(id=user_data['id'], username=user_data['username'], role=user_data['role'])
            login_user(user, remember=True) # Add 'remember=True'
            logger.info(f"User logged in: {username}")
            next_page = request.args.get('next')
            # Basic security check for open redirect vulnerability
            if next_page and next_page.startswith('/'):
                 return redirect(next_page)
            else:
                 return redirect(url_for('home'))
        else:
            logger.warning(f"Failed login attempt for user: {username}")
            flash('Invalid username, password, or inactive account.', 'danger')
            return redirect(url_for('login'))

    # Render login template for GET request
    # Replace with return render_template('login.html')
    return """
        <form method="post">
            <h2>Login</h2>
            <!-- Add flashed messages display here -->
            Username: <input type="text" name="username" required><br>
            Password: <input type="password" name="password" required><br>
            <input type="submit" value="Login">
        </form>
        <p>Need an account? <a href="/register">Register here</a></p>
    """

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Note: In final version, registration might be admin-only or invite-based
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Add more robust validation
        if not username or not email or not password:
            flash('All fields are required.', 'warning')
            return redirect(url_for('register')) # Redirect back to form

        # Check if user/email exists
        existing_user = fetch_one("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if existing_user:
            flash('Username or Email already exists.', 'danger')
            return redirect(url_for('register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        success = execute_db(
            "INSERT INTO users (username, email, password_hash, role, status) VALUES (%s, %s, %s, %s, %s)",
            (username, email, hashed_password, 'user', 'active'),
            commit=True
        )

        if success:
            logger.info(f"User registered: {username}")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Registration failed. Please try again.', 'danger')
            return redirect(url_for('register'))

    # Render registration template for GET request
    # Replace with return render_template('register.html')
    return """
        <form method="post">
            <h2>Register</h2>
             <!-- Add flashed messages display here -->
            Username: <input type="text" name="username" required><br>
            Email: <input type="email" name="email" required><br>
            Password: <input type="password" name="password" required><br>
            <input type="submit" value="Register">
        </form>
         <p>Already have an account? <a href="/login">Login here</a></p>
    """

@app.route('/logout')
@login_required
def logout():
    username = current_user.username # Get username before logging out
    logout_user()
    logger.info(f"User logged out: {username}")
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# --- API Routes ---

# Helper function to check campaign ownership
def check_campaign_owner(campaign_id):
    campaign = fetch_one("SELECT user_id FROM campaigns WHERE id = %s", (campaign_id,))
    if not campaign: # Check if campaign exists first
        return False
    # Allow access if user owns it OR if user is admin
    if campaign['user_id'] == current_user.id or (current_user.is_authenticated and current_user.role == 'admin'):
         return True
    return False

# --- Campaign Management API ---
@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    data = request.json
    # Basic Validation
    if not data or not data.get('name'):
         return jsonify({"status": "error", "message": "Missing campaign name"}), 400
    # Add more specific validations for types, lengths, allowed values etc.
    # e.g., validate status, cap types

    user_id = current_user.id
    name = data.get('name')
    # Check for duplicate name for this user
    if fetch_one("SELECT id FROM campaigns WHERE user_id = %s AND name = %s", (user_id, name)):
        return jsonify({"status": "error", "message": f"Campaign name '{name}' already exists for this user"}), 409

    # Insert into DB
    # Use data.get('key', default_value) for optional fields
    new_campaign_row = execute_db(
        """
        INSERT INTO campaigns (user_id, name, description, ad_platform, country, status, cap_hourly, cap_daily, cap_total)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *;
        """,
        (user_id, name, data.get('description'), data.get('ad_platform'), data.get('country'), data.get('status', 'active'),
         data.get('cap_hourly'), data.get('cap_daily'), data.get('cap_total')),
        commit=True,
        fetch_result=True
    )

    if new_campaign_row:
        logger.info(f"User {user_id} created campaign {new_campaign_row['id']} ('{name}')")
        # Convert rowproxy to dict for JSON serialization
        return jsonify({"status": "success", "message": "Campaign created", "campaign": dict(new_campaign_row)}), 201
    else:
        logger.error(f"Failed to create campaign for user {user_id}, name '{name}'")
        return jsonify({"status": "error", "message": "Failed to create campaign"}), 500

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    user_id = current_user.id
    # Fetch campaigns with associated DID numbers using array_agg
    # FILTER clause ensures empty array instead of [None] if no DIDs
    campaigns_raw = fetch_all("""
        SELECT c.*, array_agg(d.number) FILTER (WHERE d.id IS NOT NULL) as did_numbers
        FROM campaigns c
        LEFT JOIN campaign_dids cd ON c.id = cd.campaign_id
        LEFT JOIN dids d ON cd.did_id = d.id
        WHERE c.user_id = %s
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """, (user_id,))
    # Convert row proxies to list of dicts for JSON serialization
    campaigns = [dict(row) for row in campaigns_raw]
    return jsonify({"status": "success", "campaigns": campaigns}), 200

@app.route('/api/campaigns/<int:campaign_id>', methods=['GET'])
@login_required
def get_campaign(campaign_id):
    # Check ownership or admin status
    if not check_campaign_owner(campaign_id):
         return jsonify({"status": "error", "message": "Campaign not found or access denied"}), 404

    # Fetch specific campaign details including associated DIDs
    campaign_row = fetch_one("""
         SELECT c.*,
                array_agg(d.id) FILTER (WHERE d.id IS NOT NULL) as did_ids,
                array_agg(d.number) FILTER (WHERE d.id IS NOT NULL) as did_numbers
         FROM campaigns c
         LEFT JOIN campaign_dids cd ON c.id = cd.campaign_id
         LEFT JOIN dids d ON cd.did_id = d.id
         WHERE c.id = %s
         GROUP BY c.id
    """, (campaign_id,))

    # Should always be found if check_campaign_owner passed, but check anyway
    if campaign_row:
        return jsonify({"status": "success", "campaign": dict(campaign_row)}), 200
    else:
        logger.warning(f"Campaign {campaign_id} passed ownership check but not found in detail query.")
        return jsonify({"status": "error", "message": "Campaign not found"}), 404


@app.route('/api/campaigns/<int:campaign_id>', methods=['PUT'])
@login_required
def update_campaign(campaign_id):
     # Check ownership or admin status
    if not check_campaign_owner(campaign_id):
         return jsonify({"status": "error", "message": "Campaign not found or access denied"}), 404

    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    # Build the SET clause dynamically based on allowed fields
    allowed_updates = ['name', 'description', 'ad_platform', 'country', 'status', 'cap_hourly', 'cap_daily', 'cap_total']
    update_fields = {}
    for key in allowed_updates:
        if key in data:
            # Add validation here! Check types, ranges, allowed values ('status')
            # Example: if key == 'status' and data[key] not in ('active', 'inactive'): continue
            # Example: if 'cap_hourly' in data and (not isinstance(data['cap_hourly'], int) or data['cap_hourly'] < 0): continue
            update_fields[key] = data[key]

    if not update_fields:
        return jsonify({"status": "error", "message": "No valid or updatable fields provided"}), 400

    # Check for name uniqueness if name is being updated
    if 'name' in update_fields:
         existing = fetch_one("SELECT id FROM campaigns WHERE user_id = %s AND name = %s AND id != %s",
                              (current_user.id, update_fields['name'], campaign_id))
         if existing:
             return jsonify({"status": "error", "message": f"Campaign name '{update_fields['name']}' already exists for this user"}), 409

    # Construct SQL query
    set_clause = ", ".join([f"{key} = %s" for key in update_fields])
    update_params = list(update_fields.values())
    update_params.append(campaign_id) # For WHERE id = %s

    updated_campaign_row = execute_db(
        f"UPDATE campaigns SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *;",
        update_params,
        commit=True,
        fetch_result=True
    )

    if updated_campaign_row:
         logger.info(f"User {current_user.id} updated campaign {campaign_id}")
         return jsonify({"status": "success", "message": "Campaign updated", "campaign": dict(updated_campaign_row)}), 200
    else:
         # This might indicate the row was deleted between check and update, or DB error
         logger.error(f"Failed to update campaign {campaign_id} for user {current_user.id}")
         return jsonify({"status": "error", "message": "Failed to update campaign"}), 500


@app.route('/api/campaigns/<int:campaign_id>/dids', methods=['PUT'])
@login_required
def update_campaign_dids(campaign_id):
    # Check ownership or admin status
    if not check_campaign_owner(campaign_id):
         return jsonify({"status": "error", "message": "Campaign not found or access denied"}), 404

    data = request.json
    if not data or 'did_ids' not in data or not isinstance(data['did_ids'], list):
        return jsonify({"status": "error", "message": "Missing/invalid 'did_ids' list"}), 400

    # Convert to integers and remove duplicates
    try:
        did_ids = list(set(int(did_id) for did_id in data['did_ids']))
    except ValueError:
         return jsonify({"status": "error", "message": "Invalid DID ID format in list"}), 400


    # Transaction needed here for atomicity
    conn = get_db_connection()
    if not conn: return jsonify({"status": "error", "message": "Database connection error"}), 500
    try:
        with conn.cursor() as cur:
            # Verify all provided DIDs belong to the current user OR are unassigned
            # (Admins might have different rules, add check for current_user.role == 'admin' if needed)
            valid_dids_count = 0
            if did_ids: # Only check if the list is not empty
                placeholders = ','.join(['%s'] * len(did_ids))
                cur.execute(f"""
                    SELECT COUNT(id) FROM dids
                    WHERE id IN ({placeholders})
                    AND (assigned_user_id = %s OR assigned_user_id IS NULL)
                """, did_ids + [current_user.id])
                result = cur.fetchone()
                valid_dids_count = result[0] if result else 0

            if valid_dids_count != len(did_ids):
                 conn.rollback()
                 logger.warning(f"Attempt to assign invalid/unowned DIDs to campaign {campaign_id} by user {current_user.id}")
                 return jsonify({"status": "error", "message": "One or more DID IDs are invalid, do not exist, or are already assigned to another user"}), 400

            # --- Update Links ---
            # 1. Get DIDs currently linked to THIS campaign
            cur.execute("SELECT did_id FROM campaign_dids WHERE campaign_id = %s", (campaign_id,))
            current_linked_dids = {row[0] for row in cur.fetchall()}

            # 2. DIDs to add (in new list, not currently linked)
            dids_to_add = [did_id for did_id in did_ids if did_id not in current_linked_dids]

            # 3. DIDs to remove (currently linked, not in new list)
            dids_to_remove = [did_id for did_id in current_linked_dids if did_id not in did_ids]

            # 4. Perform deletions
            if dids_to_remove:
                 placeholders_remove = ','.join(['%s'] * len(dids_to_remove))
                 cur.execute(f"DELETE FROM campaign_dids WHERE campaign_id = %s AND did_id IN ({placeholders_remove})",
                             [campaign_id] + dids_to_remove)
                 # Decide if removing from campaign should make DID unassigned. If so:
                 # cur.execute(f"UPDATE dids SET assignment_status = 'unassigned', assigned_user_id = NULL WHERE id IN ({placeholders_remove})", dids_to_remove)


            # 5. Perform insertions
            if dids_to_add:
                 assignment_data = [(campaign_id, did_id) for did_id in dids_to_add]
                 # Use execute_values for efficiency if psycopg2 version supports it well
                 # Or loop insert
                 for assign_data in assignment_data:
                      cur.execute("INSERT INTO campaign_dids (campaign_id, did_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", assign_data)
                 # Update DID status to 'assigned' and link to user
                 placeholders_add = ','.join(['%s'] * len(dids_to_add))
                 cur.execute(f"""
                      UPDATE dids SET assignment_status = 'assigned', assigned_user_id = %s, updated_at = CURRENT_TIMESTAMP
                      WHERE id IN ({placeholders_add})
                 """, [current_user.id] + dids_to_add)

            conn.commit()
            logger.info(f"User {current_user.id} updated DIDs for campaign {campaign_id}. Added: {dids_to_add}, Removed: {dids_to_remove}")
            return jsonify({"status": "success", "message": "Campaign DIDs updated"}), 200
    except psycopg2.Error as e: # Catch specific DB errors
        conn.rollback()
        logger.error(f"Database error updating DIDs for campaign {campaign_id}: {e}")
        return jsonify({"status": "error", "message": "Database error during DID update"}), 500
    except Exception as e: # Catch other potential errors
        conn.rollback()
        logger.error(f"Unexpected error updating DIDs for campaign {campaign_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to update campaign DIDs"}), 500
    finally:
        release_db_connection(conn)


@app.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
     # Check ownership or admin status
     if not check_campaign_owner(campaign_id):
          return jsonify({"status": "error", "message": "Campaign not found or access denied"}), 404

     # We need to know which DIDs were linked before deleting the campaign
     # to potentially update their status (optional, depends on desired logic)
     linked_dids = fetch_all("SELECT did_id FROM campaign_dids WHERE campaign_id = %s", (campaign_id,))
     did_ids_to_update = [row['did_id'] for row in linked_dids]

     # ON DELETE CASCADE handles junction tables (campaign_dids, rule_campaigns) automatically
     success = execute_db("DELETE FROM campaigns WHERE id = %s", (campaign_id,), commit=True)

     if success:
         logger.info(f"User {current_user.id} deleted campaign {campaign_id}")
         # Optional: Update status of previously linked DIDs if they are now orphaned
         # This logic depends on whether a DID can exist without a campaign link
         # if did_ids_to_update:
         #    placeholders = ','.join(['%s'] * len(did_ids_to_update))
         #    # Check if these DIDs are linked to ANY other campaign for this user before unassigning
         #    execute_db(f"UPDATE dids SET assignment_status = 'unassigned', assigned_user_id = NULL WHERE id IN ({placeholders}) AND assigned_user_id = %s", did_ids_to_update + [current_user.id], commit=True)
         return jsonify({"status": "success", "message": "Campaign deleted"}), 200
     else:
         logger.error(f"Failed to delete campaign {campaign_id} for user {current_user.id}")
         return jsonify({"status": "error", "message": "Failed to delete campaign"}), 500


# --- TODO: Add API endpoints for DIDs, CDRs, Admin functions ---

# --- Target Management API ---

@app.route('/api/targets', methods=['POST'])
@login_required
def create_target():
    data = request.json
    # --- Validation ---
    required_fields = ['name', 'destination_type', 'destination_uri', 'concurrency_limit']
    if not data or not all(field in data for field in required_fields):
        missing = [field for field in required_fields if not data or field not in data]
        return jsonify({"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}), 400

    name = data.get('name')
    dest_type = data.get('destination_type')
    dest_uri = data.get('destination_uri')
    concurrency = data.get('concurrency_limit')
    total_allowed = data.get('total_calls_allowed') # Optional
    status = data.get('status', 'active')

    # Validate specific values
    if dest_type not in ('SIP', 'IAX2'):
        return jsonify({"status": "error", "message": "Invalid destination_type. Must be 'SIP' or 'IAX2'."}), 400
    if status not in ('active', 'inactive'):
         return jsonify({"status": "error", "message": "Invalid status. Must be 'active' or 'inactive'."}), 400
    try:
        concurrency = int(concurrency)
        if concurrency < 1: raise ValueError("Concurrency must be positive")
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid concurrency_limit. Must be a positive integer."}), 400
    if total_allowed is not None:
        try:
            total_allowed = int(total_allowed)
            if total_allowed < 0: raise ValueError("Total calls allowed cannot be negative")
        except (ValueError, TypeError):
             return jsonify({"status": "error", "message": "Invalid total_calls_allowed. Must be a non-negative integer or null."}), 400
    # Add validation for destination_uri format if needed (e.g., basic check for sip: or iax2:)

    # --- Check for duplicate name for this user ---
    user_id = current_user.id
    if fetch_one("SELECT id FROM targets WHERE user_id = %s AND name = %s", (user_id, name)):
        return jsonify({"status": "error", "message": f"Target name '{name}' already exists for this user"}), 409 # 409 Conflict

    # --- Insert into DB ---
    new_target_row = execute_db(
        """
        INSERT INTO targets (user_id, name, client_name, description, destination_type,
                             destination_uri, total_calls_allowed, concurrency_limit, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *;
        """,
        (user_id, name, data.get('client_name'), data.get('description'), dest_type,
         dest_uri, total_allowed, concurrency, status),
        commit=True,
        fetch_result=True
    )

    if new_target_row:
        logger.info(f"User {user_id} created target {new_target_row['id']} ('{name}')")
        return jsonify({"status": "success", "message": "Target created", "target": dict(new_target_row)}), 201 # 201 Created
    else:
        logger.error(f"Failed to create target for user {user_id}, name '{name}'")
        return jsonify({"status": "error", "message": "Failed to create target"}), 500

@app.route('/api/targets', methods=['GET'])
@login_required
def get_targets():
    user_id = current_user.id
    # Fetch all targets belonging to the current user
    targets_raw = fetch_all("""
        SELECT * FROM targets
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))
    targets = [dict(row) for row in targets_raw]
    return jsonify({"status": "success", "targets": targets}), 200

@app.route('/api/targets/<int:target_id>', methods=['GET'])
@login_required
def get_target(target_id):
    # Check ownership or admin status
    if not check_target_owner(target_id):
         return jsonify({"status": "error", "message": "Target not found or access denied"}), 404

    target_row = fetch_one("SELECT * FROM targets WHERE id = %s", (target_id,))

    if target_row:
        return jsonify({"status": "success", "target": dict(target_row)}), 200
    else:
        # Should not happen if check_target_owner passed, but for safety
        logger.warning(f"Target {target_id} passed ownership check but not found in detail query.")
        return jsonify({"status": "error", "message": "Target not found"}), 404

@app.route('/api/targets/<int:target_id>', methods=['PUT'])
@login_required
def update_target(target_id):
    # Check ownership or admin status
    if not check_target_owner(target_id):
         return jsonify({"status": "error", "message": "Target not found or access denied"}), 404

    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    # --- Build SET clause dynamically, validating fields ---
    allowed_updates = ['name', 'client_name', 'description', 'destination_type',
                       'destination_uri', 'total_calls_allowed', 'concurrency_limit', 'status']
    update_fields = {}
    validation_errors = []

    for key in allowed_updates:
        if key in data:
            value = data[key]
            # --- Revised Validation Logic ---
            if key == 'name':
                if not isinstance(value, str) or not value.strip():
                    validation_errors.append("Name cannot be empty.")
                else:
                    value = value.strip() # Store the stripped value
            elif key == 'destination_type':
                if value not in ('SIP', 'IAX2'):
                    validation_errors.append("Invalid destination_type.")
            elif key == 'status':
                 if value not in ('active', 'inactive'):
                    validation_errors.append("Invalid status.")
            elif key == 'concurrency_limit':
                try:
                    value = int(value)
                    if value < 1:
                        validation_errors.append("Concurrency limit must be positive.")
                except (ValueError, TypeError):
                    validation_errors.append("Invalid concurrency_limit (must be an integer).")
            elif key == 'total_calls_allowed':
                if value is not None: # Allow null
                    try:
                        value = int(value)
                        if value < 0:
                             validation_errors.append("Total calls allowed cannot be negative.")
                    except (ValueError, TypeError):
                        validation_errors.append("Invalid total_calls_allowed (must be an integer or null).")
            elif key == 'client_name':
                 if not isinstance(value, str): # Optional: Allow empty?
                     # Decide if empty client_name is okay or needs validation
                     pass # No specific validation here, adjust if needed
            elif key == 'description':
                 if not isinstance(value, str):
                     pass # No specific validation here
            elif key == 'destination_uri':
                 if not isinstance(value, str) or not value.strip():
                     validation_errors.append("Destination URI cannot be empty.")
                 # Optional: Add regex check for basic format (e.g., starts with sip: or iax2:)
                 else:
                      value = value.strip()

            # Add the validated (and potentially type-converted) value if no errors occurred *for this key*
            # (Checking global validation_errors here prevents adding partially validated data if an earlier key failed)
            if not validation_errors:
                 update_fields[key] = value

    if validation_errors:
        # It's better to show all errors at once
        return jsonify({"status": "error", "message": "Validation failed", "errors": list(set(validation_errors))}), 400 # Use set to remove duplicates

    if not update_fields:
        # This might happen if only invalid fields were provided
        return jsonify({"status": "error", "message": "No valid fields provided for update"}), 400

    # --- Check for name uniqueness (rest of the function remains the same) ---
    if 'name' in update_fields:
         existing = fetch_one("SELECT id FROM targets WHERE user_id = %s AND name = %s AND id != %s",
                              (current_user.id, update_fields['name'], target_id))
         if existing:
             return jsonify({"status": "error", "message": f"Target name '{update_fields['name']}' already exists for this user"}), 409 # Conflict

    # --- Construct SQL query (remains the same) ---
    set_clause = ", ".join([f"{key} = %s" for key in update_fields])
    update_params = list(update_fields.values())
    update_params.append(target_id) # For WHERE id = %s

    updated_target_row = execute_db(
        f"UPDATE targets SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *;",
        update_params,
        commit=True,
        fetch_result=True
    )

    # --- Handle response (remains the same) ---
    if updated_target_row:
         logger.info(f"User {current_user.id} updated target {target_id}")
         return jsonify({"status": "success", "message": "Target updated", "target": dict(updated_target_row)}), 200
    else:
         logger.error(f"Failed to update target {target_id} for user {current_user.id}")
         # Could be DB error, or the row was deleted concurrently
         return jsonify({"status": "error", "message": "Failed to update target"}), 500

@app.route('/api/targets/<int:target_id>', methods=['DELETE'])
@login_required
def delete_target(target_id):
    # Check ownership or admin status
    if not check_target_owner(target_id):
         return jsonify({"status": "error", "message": "Target not found or access denied"}), 404

    # Check if target is linked to any active forwarding rules before deleting? (Optional)
    # linked_rules = fetch_all("SELECT rule_id FROM rule_targets WHERE target_id = %s", (target_id,))
    # if linked_rules:
    #    # Consider preventing deletion or just letting ON DELETE CASCADE handle rule_targets links
    #    logger.warning(f"Attempt to delete target {target_id} which is linked to rules: {[r['rule_id'] for r in linked_rules]}")
    #    # return jsonify({"status": "error", "message": "Cannot delete target, it is linked to active forwarding rules."}), 409 # Conflict

    # ON DELETE CASCADE on rule_targets table will automatically remove links
    success = execute_db("DELETE FROM targets WHERE id = %s", (target_id,), commit=True)

    if success:
        logger.info(f"User {current_user.id} deleted target {target_id}")
        return jsonify({"status": "success", "message": "Target deleted"}), 200
    else:
        logger.error(f"Failed to delete target {target_id} for user {current_user.id}")
        return jsonify({"status": "error", "message": "Failed to delete target"}), 500

# --- Internal API Routes (for Asterisk AGI) ---
# These should be secured, e.g., require specific token or only allow from localhost

# --- Forwarding Rule Management API ---

# Allowed routing strategies
ALLOWED_ROUTING_STRATEGIES = ['Primary', 'RoundRobin', 'Priority'] # Add others if needed

@app.route('/api/forwarding_rules', methods=['POST'])
@login_required
def create_forwarding_rule():
    data = request.json
    user_id = current_user.id

    # --- Basic Validation ---
    required_fields = ['name', 'routing_strategy', 'campaign_ids', 'target_details']
    if not data or not all(field in data for field in required_fields):
        missing = [field for field in required_fields if not data or field not in data]
        return jsonify({"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}), 400

    name = data.get('name')
    strategy = data.get('routing_strategy')
    min_delay = data.get('min_delay_between_calls', 0)
    min_duration = data.get('min_billable_duration', 0)
    status = data.get('status', 'active')
    campaign_ids = data.get('campaign_ids', [])
    target_details = data.get('target_details', []) # Expected format: [{"target_id": X, "priority": Y, "weight": Z}, ...]

    # --- Detailed Validation ---
    validation_errors = []
    if not isinstance(name, str) or not name.strip():
        validation_errors.append("Rule name cannot be empty.")
    if strategy not in ALLOWED_ROUTING_STRATEGIES:
        validation_errors.append(f"Invalid routing_strategy. Must be one of: {', '.join(ALLOWED_ROUTING_STRATEGIES)}")
    if status not in ('active', 'inactive'):
        validation_errors.append("Invalid status. Must be 'active' or 'inactive'.")
    try:
        min_delay = int(min_delay)
        if min_delay < 0: validation_errors.append("Minimum delay cannot be negative.")
    except (ValueError, TypeError): validation_errors.append("Invalid minimum delay.")
    try:
        min_duration = int(min_duration)
        if min_duration < 0: validation_errors.append("Minimum billable duration cannot be negative.")
    except (ValueError, TypeError): validation_errors.append("Invalid minimum billable duration.")
    if not isinstance(campaign_ids, list) or not campaign_ids:
         validation_errors.append("At least one campaign ID must be provided in 'campaign_ids' list.")
    if not isinstance(target_details, list) or not target_details:
         validation_errors.append("At least one target detail must be provided in 'target_details' list.")

    # Validate target_details format
    processed_targets = []
    if isinstance(target_details, list):
        for idx, t_detail in enumerate(target_details):
             if not isinstance(t_detail, dict) or 'target_id' not in t_detail:
                 validation_errors.append(f"Invalid format for target_details item {idx}: missing 'target_id'.")
                 continue
             try:
                 target_id = int(t_detail['target_id'])
                 priority = int(t_detail.get('priority', 0)) # Default priority 0
                 weight = int(t_detail.get('weight', 100))  # Default weight 100
                 if weight <= 0: validation_errors.append(f"Weight for target {target_id} must be positive.")
                 processed_targets.append({'target_id': target_id, 'priority': priority, 'weight': weight})
             except (ValueError, TypeError):
                 validation_errors.append(f"Invalid 'target_id', 'priority', or 'weight' for target_details item {idx}.")

    if validation_errors:
         return jsonify({"status": "error", "message": "Validation failed", "errors": list(set(validation_errors))}), 400

    # --- Check for duplicate name for this user ---
    if fetch_one("SELECT id FROM forwarding_rules WHERE user_id = %s AND name = %s", (user_id, name)):
        return jsonify({"status": "error", "message": f"Forwarding rule name '{name}' already exists for this user"}), 409

    # --- Transaction Time! ---
    conn = get_db_connection()
    if not conn: return jsonify({"status": "error", "message": "Database connection error"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # 1. Verify campaigns belong to user
            if campaign_ids:
                placeholders_c = ','.join(['%s'] * len(campaign_ids))
                cur.execute(f"SELECT COUNT(id) FROM campaigns WHERE id IN ({placeholders_c}) AND user_id = %s", campaign_ids + [user_id])
                if cur.fetchone()['count'] != len(campaign_ids):
                    conn.rollback()
                    return jsonify({"status": "error", "message": "One or more campaign IDs are invalid or do not belong to the user."}), 400

            # 2. Verify targets belong to user
            target_ids_only = [pt['target_id'] for pt in processed_targets]
            if target_ids_only:
                placeholders_t = ','.join(['%s'] * len(target_ids_only))
                cur.execute(f"SELECT COUNT(id) FROM targets WHERE id IN ({placeholders_t}) AND user_id = %s", target_ids_only + [user_id])
                if cur.fetchone()['count'] != len(target_ids_only):
                    conn.rollback()
                    return jsonify({"status": "error", "message": "One or more target IDs are invalid or do not belong to the user."}), 400

            # 3. Insert the rule
            cur.execute(
                """
                INSERT INTO forwarding_rules (user_id, name, routing_strategy, min_delay_between_calls, min_billable_duration, status)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
                """,
                (user_id, name.strip(), strategy, min_delay, min_duration, status)
            )
            new_rule_id = cur.fetchone()['id']

            # 4. Link campaigns
            if campaign_ids:
                campaign_link_data = [(new_rule_id, c_id) for c_id in campaign_ids]
                # Consider psycopg2.extras.execute_values for bulk insert if many links expected
                for link_data in campaign_link_data:
                    cur.execute("INSERT INTO rule_campaigns (rule_id, campaign_id) VALUES (%s, %s)", link_data)

            # 5. Link targets
            if processed_targets:
                target_link_data = [(new_rule_id, pt['target_id'], pt['priority'], pt['weight']) for pt in processed_targets]
                for link_data in target_link_data:
                     cur.execute("INSERT INTO rule_targets (rule_id, target_id, priority, weight) VALUES (%s, %s, %s, %s)", link_data)

            conn.commit()
            logger.info(f"User {user_id} created forwarding rule {new_rule_id} ('{name}')")

            # Fetch the created rule with details for the response
            # (Could optimize this, but it's clear)
            new_rule_details = fetch_one("SELECT * FROM forwarding_rules WHERE id = %s", (new_rule_id,))
            # Fetch linked items details similarly if needed for response, or just return the basic rule

            return jsonify({"status": "success", "message": "Forwarding rule created", "rule": dict(new_rule_details)}), 201

    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Database error creating forwarding rule for user {user_id}, name '{name}': {e}")
        return jsonify({"status": "error", "message": "Database error during rule creation"}), 500
    except Exception as e:
        conn.rollback()
        logger.error(f"Unexpected error creating forwarding rule for user {user_id}, name '{name}': {e}")
        return jsonify({"status": "error", "message": "Failed to create forwarding rule"}), 500
    finally:
        release_db_connection(conn)


@app.route('/api/forwarding_rules', methods=['GET'])
@login_required
def get_forwarding_rules():
    user_id = current_user.id
    # Fetch rules and aggregate linked campaign/target info
    rules_raw = fetch_all("""
        SELECT
            fr.*,
            COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id', c.id, 'name', c.name)) FILTER (WHERE c.id IS NOT NULL), '[]'::jsonb) AS campaigns,
            COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id', t.id, 'name', t.name, 'priority', rt.priority, 'weight', rt.weight)) FILTER (WHERE t.id IS NOT NULL), '[]'::jsonb) AS targets
        FROM forwarding_rules fr
        LEFT JOIN rule_campaigns rc ON fr.id = rc.rule_id
        LEFT JOIN campaigns c ON rc.campaign_id = c.id AND c.user_id = fr.user_id
        LEFT JOIN rule_targets rt ON fr.id = rt.rule_id
        LEFT JOIN targets t ON rt.target_id = t.id AND t.user_id = fr.user_id
        WHERE fr.user_id = %s
        GROUP BY fr.id
        ORDER BY fr.created_at DESC;
    """, (user_id,))

    rules = [dict(row) for row in rules_raw]
    return jsonify({"status": "success", "rules": rules}), 200


@app.route('/api/forwarding_rules/<int:rule_id>', methods=['GET'])
@login_required
def get_forwarding_rule(rule_id):
    # Check ownership or admin status
    if not check_rule_owner(rule_id):
         return jsonify({"status": "error", "message": "Forwarding rule not found or access denied"}), 404

    # Fetch specific rule details including linked campaigns and targets
    rule_row = fetch_one("""
        SELECT
            fr.*,
            COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id', c.id, 'name', c.name)) FILTER (WHERE c.id IS NOT NULL), '[]'::jsonb) AS campaigns,
            COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id', t.id, 'name', t.name, 'priority', rt.priority, 'weight', rt.weight)) FILTER (WHERE t.id IS NOT NULL), '[]'::jsonb) AS targets
        FROM forwarding_rules fr
        LEFT JOIN rule_campaigns rc ON fr.id = rc.rule_id
        LEFT JOIN campaigns c ON rc.campaign_id = c.id AND c.user_id = fr.user_id
        LEFT JOIN rule_targets rt ON fr.id = rt.rule_id
        LEFT JOIN targets t ON rt.target_id = t.id AND t.user_id = fr.user_id
        WHERE fr.id = %s AND fr.user_id = %s -- Double check user_id here for safety
        GROUP BY fr.id;
    """, (rule_id, current_user.id)) # Assuming non-admins can only GET their own

    if rule_row:
        return jsonify({"status": "success", "rule": dict(rule_row)}), 200
    else:
        # Should not happen if check_rule_owner passed, but for safety
        logger.warning(f"Rule {rule_id} passed ownership check but not found in detail query for user {current_user.id}.")
        return jsonify({"status": "error", "message": "Forwarding rule not found"}), 404

@app.route('/api/forwarding_rules/<int:rule_id>', methods=['PUT'])
@login_required
def update_forwarding_rule(rule_id):
    # Check ownership or admin status
    if not check_rule_owner(rule_id):
         return jsonify({"status": "error", "message": "Forwarding rule not found or access denied"}), 404

    data = request.json
    user_id = current_user.id
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    # --- Validation of basic rule fields ---
    allowed_updates = ['name', 'routing_strategy', 'min_delay_between_calls', 'min_billable_duration', 'status']
    update_fields = {}
    validation_errors = []
    # Validate fields present in data
    for key in allowed_updates:
         if key in data:
            value = data[key]
            # Add validation logic similar to create_forwarding_rule
            if key == 'name':
                 if not isinstance(value, str) or not value.strip(): validation_errors.append("Rule name cannot be empty.")
                 else: update_fields[key] = value.strip()
            elif key == 'routing_strategy':
                 if value not in ALLOWED_ROUTING_STRATEGIES: validation_errors.append("Invalid routing_strategy.")
                 else: update_fields[key] = value
            elif key == 'status':
                 if value not in ('active', 'inactive'): validation_errors.append("Invalid status.")
                 else: update_fields[key] = value
            elif key == 'min_delay_between_calls':
                 try:
                     val_int = int(value)
                     if val_int < 0: validation_errors.append("Minimum delay cannot be negative.")
                     else: update_fields[key] = val_int
                 except (ValueError, TypeError): validation_errors.append("Invalid minimum delay.")
            elif key == 'min_billable_duration':
                  try:
                     val_int = int(value)
                     if val_int < 0: validation_errors.append("Minimum billable duration cannot be negative.")
                     else: update_fields[key] = val_int
                  except (ValueError, TypeError): validation_errors.append("Invalid minimum billable duration.")

    # --- Validation of campaign_ids and target_details if provided ---
    campaign_ids = data.get('campaign_ids') # Optional: If not provided, links are not changed
    target_details = data.get('target_details') # Optional: If not provided, links are not changed
    processed_targets = None

    if campaign_ids is not None:
        if not isinstance(campaign_ids, list) or not campaign_ids: # Require at least one if provided
            validation_errors.append("If 'campaign_ids' is provided, it must be a non-empty list.")
        # Add check if list contains non-integers?

    if target_details is not None:
        if not isinstance(target_details, list) or not target_details: # Require at least one if provided
            validation_errors.append("If 'target_details' is provided, it must be a non-empty list.")
        else:
            processed_targets = []
            for idx, t_detail in enumerate(target_details):
                # Repeat validation from create route
                 if not isinstance(t_detail, dict) or 'target_id' not in t_detail:
                     validation_errors.append(f"Invalid format for target_details item {idx}: missing 'target_id'.")
                     continue
                 try:
                     target_id_val = int(t_detail['target_id'])
                     priority = int(t_detail.get('priority', 0))
                     weight = int(t_detail.get('weight', 100))
                     if weight <= 0: validation_errors.append(f"Weight for target {target_id_val} must be positive.")
                     processed_targets.append({'target_id': target_id_val, 'priority': priority, 'weight': weight})
                 except (ValueError, TypeError):
                     validation_errors.append(f"Invalid 'target_id', 'priority', or 'weight' for target_details item {idx}.")


    if validation_errors:
         return jsonify({"status": "error", "message": "Validation failed", "errors": list(set(validation_errors))}), 400

    # Check if anything is actually being updated
    if not update_fields and campaign_ids is None and target_details is None:
         return jsonify({"status": "error", "message": "No valid fields provided for update"}), 400

    # --- Check for name uniqueness if name is being updated ---
    if 'name' in update_fields:
         existing = fetch_one("SELECT id FROM forwarding_rules WHERE user_id = %s AND name = %s AND id != %s",
                              (user_id, update_fields['name'], rule_id))
         if existing:
             return jsonify({"status": "error", "message": f"Forwarding rule name '{update_fields['name']}' already exists for this user"}), 409

    # --- Transaction Time! ---
    conn = get_db_connection()
    if not conn: return jsonify({"status": "error", "message": "Database connection error"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # 1. Update basic rule fields if any were provided
            if update_fields:
                 set_clause = ", ".join([f"{key} = %s" for key in update_fields])
                 update_params = list(update_fields.values())
                 update_params.append(rule_id)
                 cur.execute(f"UPDATE forwarding_rules SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s", update_params)

            # 2. Update campaign links if campaign_ids were provided
            if campaign_ids is not None:
                 # Verify campaigns belong to user
                 placeholders_c = ','.join(['%s'] * len(campaign_ids))
                 cur.execute(f"SELECT COUNT(id) FROM campaigns WHERE id IN ({placeholders_c}) AND user_id = %s", campaign_ids + [user_id])
                 if cur.fetchone()['count'] != len(campaign_ids):
                     conn.rollback()
                     return jsonify({"status": "error", "message": "One or more campaign IDs are invalid or do not belong to the user."}), 400
                 # Delete existing links and insert new ones
                 cur.execute("DELETE FROM rule_campaigns WHERE rule_id = %s", (rule_id,))
                 campaign_link_data = [(rule_id, c_id) for c_id in campaign_ids]
                 for link_data in campaign_link_data:
                     cur.execute("INSERT INTO rule_campaigns (rule_id, campaign_id) VALUES (%s, %s)", link_data)

            # 3. Update target links if target_details were provided
            if processed_targets is not None: # Use the validated list
                 target_ids_only = [pt['target_id'] for pt in processed_targets]
                 # Verify targets belong to user
                 placeholders_t = ','.join(['%s'] * len(target_ids_only))
                 cur.execute(f"SELECT COUNT(id) FROM targets WHERE id IN ({placeholders_t}) AND user_id = %s", target_ids_only + [user_id])
                 if cur.fetchone()['count'] != len(target_ids_only):
                     conn.rollback()
                     return jsonify({"status": "error", "message": "One or more target IDs are invalid or do not belong to the user."}), 400
                 # Delete existing links and insert new ones
                 cur.execute("DELETE FROM rule_targets WHERE rule_id = %s", (rule_id,))
                 target_link_data = [(rule_id, pt['target_id'], pt['priority'], pt['weight']) for pt in processed_targets]
                 for link_data in target_link_data:
                     cur.execute("INSERT INTO rule_targets (rule_id, target_id, priority, weight) VALUES (%s, %s, %s, %s)", link_data)

            conn.commit()
            logger.info(f"User {user_id} updated forwarding rule {rule_id}")

            # Fetch updated rule details for response
            # --- Revised Fetching Logic for Response ---
            # Re-run the query used in get_forwarding_rule to get the latest state
            updated_rule_row = fetch_one("""
                SELECT
                    fr.*,
                    COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id', c.id, 'name', c.name)) FILTER (WHERE c.id IS NOT NULL), '[]'::jsonb) AS campaigns,
                    COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id', t.id, 'name', t.name, 'priority', rt.priority, 'weight', rt.weight)) FILTER (WHERE t.id IS NOT NULL), '[]'::jsonb) AS targets
                FROM forwarding_rules fr
                LEFT JOIN rule_campaigns rc ON fr.id = rc.rule_id
                LEFT JOIN campaigns c ON rc.campaign_id = c.id AND c.user_id = fr.user_id
                LEFT JOIN rule_targets rt ON fr.id = rt.rule_id
                LEFT JOIN targets t ON rt.target_id = t.id AND t.user_id = fr.user_id
                WHERE fr.id = %s AND fr.user_id = %s
                GROUP BY fr.id;
            """, (rule_id, user_id)) # Use user_id from the current context

            # Check if the fetch was successful (it should be, as we just updated it)
            updated_rule_details = dict(updated_rule_row) if updated_rule_row else None

            return jsonify({"status": "success", "message": "Forwarding rule updated", "rule": updated_rule_details}), 200

    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Database error updating forwarding rule {rule_id} for user {user_id}: {e}")
        return jsonify({"status": "error", "message": "Database error during rule update"}), 500
    except Exception as e:
        conn.rollback()
        # Log the detailed traceback for unexpected errors
        logger.exception(f"Unexpected error updating forwarding rule {rule_id} for user {user_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to update forwarding rule"}), 500
    finally:
        release_db_connection(conn)


@app.route('/api/forwarding_rules/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_forwarding_rule(rule_id):
    # Check ownership or admin status
    if not check_rule_owner(rule_id):
         return jsonify({"status": "error", "message": "Forwarding rule not found or access denied"}), 404

    # ON DELETE CASCADE on rule_campaigns and rule_targets handles link deletion
    success = execute_db("DELETE FROM forwarding_rules WHERE id = %s", (rule_id,), commit=True)

    if success:
        logger.info(f"User {current_user.id} deleted forwarding rule {rule_id}")
        return jsonify({"status": "success", "message": "Forwarding rule deleted"}), 200
    else:
        logger.error(f"Failed to delete forwarding rule {rule_id} for user {current_user.id}")
        return jsonify({"status": "error", "message": "Failed to delete forwarding rule"}), 500

# --- DID Management API (User Facing) ---

@app.route('/api/dids', methods=['GET'])
@login_required
def get_assigned_dids():
    """Gets a list of DIDs assigned to the currently logged-in user."""
    user_id = current_user.id

    # Query DIDs assigned to the user.
    # Optionally, join with campaigns to show which campaign(s) a DID is linked to.
    dids_raw = fetch_all("""
        SELECT
            d.id,
            d.number,
            d.country_code,
            d.number_type,
            d.assignment_status,
            d.provider_source, -- Optional: maybe hide from regular users?
            d.created_at,
            d.updated_at,
            -- Aggregate linked campaign names into an array
            COALESCE(jsonb_agg(DISTINCT c.name) FILTER (WHERE c.id IS NOT NULL), '[]'::jsonb) AS linked_campaigns
        FROM dids d
        LEFT JOIN campaign_dids cd ON d.id = cd.did_id
        LEFT JOIN campaigns c ON cd.campaign_id = c.id AND c.user_id = d.assigned_user_id
        WHERE d.assigned_user_id = %s
        GROUP BY d.id
        ORDER BY d.number;
    """, (user_id,))

    dids = [dict(row) for row in dids_raw]
    return jsonify({"status": "success", "dids": dids}), 200

@app.route('/api/did_requests', methods=['POST'])
@login_required
def create_did_request():
    """Allows a user to submit a request for a new DID."""
    user_id = current_user.id
    data = request.json

    # --- Validation ---
    if not data or not data.get('request_details'):
        return jsonify({"status": "error", "message": "Missing 'request_details' field"}), 400

    request_details = data.get('request_details')
    if not isinstance(request_details, str) or len(request_details.strip()) < 10: # Basic check
        return jsonify({"status": "error", "message": "'request_details' must be a non-empty string (min 10 chars recommended)."}), 400

    # --- Insert into DB ---
    new_request_row = execute_db(
        """
        INSERT INTO did_requests (user_id, request_details, status)
        VALUES (%s, %s, %s) RETURNING *;
        """,
        (user_id, request_details.strip(), 'pending'), # Default status is 'pending'
        commit=True,
        fetch_result=True
    )

    if new_request_row:
        logger.info(f"User {user_id} submitted DID request {new_request_row['id']}")
        # Optional: Create a notification for the admin? (Requires admin notification logic)
        # Optional: Create a notification for the user confirming submission?
        return jsonify({"status": "success", "message": "DID request submitted successfully.", "request": dict(new_request_row)}), 201
    else:
        logger.error(f"Failed to create DID request for user {user_id}")
        return jsonify({"status": "error", "message": "Failed to submit DID request"}), 500

# --- CDR Listing API ---

@app.route('/api/cdrs', methods=['GET'])
@login_required
def get_cdrs():
    """Gets a list of Call Detail Records for the currently logged-in user, with optional filtering."""
    user_id = current_user.id

    # --- Filtering ---
    # Get filter parameters from query string (e.g., /api/cdrs?start_date=...&end_date=...)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    campaign_id_filter = request.args.get('campaign_id')
    target_id_filter = request.args.get('target_id')
    # Add more filters as needed: final_status, incoming_did, caller_id_num, etc.

    # Build the WHERE clause and parameters dynamically
    where_clauses = ["user_id = %s"]
    params = [user_id]

    # Date filtering
    try:
        if start_date_str:
            # Attempt to parse YYYY-MM-DD format
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            where_clauses.append("timestamp_start >= %s")
            params.append(start_date)
        if end_date_str:
            # Add 1 day to end_date to make it inclusive (timestamp_start < day after end_date)
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            # Or adjust based on desired behavior (e.g., include times on the end_date)
            # For simplicity, let's filter for calls starting strictly before the day *after* end_date
            from datetime import timedelta
            end_date_inclusive = end_date + timedelta(days=1)
            where_clauses.append("timestamp_start < %s")
            params.append(end_date_inclusive)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid date format. Please use YYYY-MM-DD."}), 400

    # Campaign filtering
    if campaign_id_filter:
        try:
            campaign_id = int(campaign_id_filter)
            # Optional: Verify this campaign ID actually belongs to the user?
            where_clauses.append("campaign_id = %s")
            params.append(campaign_id)
        except ValueError:
             return jsonify({"status": "error", "message": "Invalid campaign_id format. Must be an integer."}), 400

    # Target filtering
    if target_id_filter:
         try:
            target_id = int(target_id_filter)
            # Optional: Verify target ID belongs to user?
            where_clauses.append("target_id = %s")
            params.append(target_id)
         except ValueError:
             return jsonify({"status": "error", "message": "Invalid target_id format. Must be an integer."}), 400


    # --- Construct and Execute Query ---
    base_query = "SELECT * FROM call_detail_records"
    where_clause = " AND ".join(where_clauses)
    # Add ordering and pagination later if needed
    order_clause = "ORDER BY timestamp_start DESC"
    limit_clause = "LIMIT 1000" # Add a sensible default limit

    final_query = f"{base_query} WHERE {where_clause} {order_clause} {limit_clause};"

    logger.debug(f"Executing CDR query: {final_query} with params: {params}") # Use debug level

    cdrs_raw = fetch_all(final_query, tuple(params)) # Pass params as a tuple

    # Convert Decimal types for JSON serialization if necessary
    cdrs = []
    for row in cdrs_raw:
        row_dict = dict(row)
        # Check for Decimal fields (like calculated_cost) and convert to string or float
        if 'calculated_cost' in row_dict and row_dict['calculated_cost'] is not None:
             # Example: Convert Decimal to string to preserve precision
             row_dict['calculated_cost'] = str(row_dict['calculated_cost'])
             # Or convert to float: float(row_dict['calculated_cost']) - might lose precision
        cdrs.append(row_dict)


    return jsonify({"status": "success", "cdrs": cdrs}), 200

# --- Notification API ---

@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Gets a list of notifications for the currently logged-in user."""
    user_id = current_user.id

    # Fetch notifications, ordering by read status (unread first) and then by time (newest first)
    # Add a limit to avoid fetching thousands of old read notifications, maybe paginate later
    limit = request.args.get('limit', default=100, type=int) # Example limit
    if limit > 500: limit = 500 # Max limit

    notifications_raw = fetch_all("""
        SELECT * FROM notifications
        WHERE user_id = %s
        ORDER BY is_read ASC, created_at DESC
        LIMIT %s;
    """, (user_id, limit))

    notifications = [dict(row) for row in notifications_raw]
    return jsonify({"status": "success", "notifications": notifications}), 200

@app.route('/api/notifications/<int:notification_id>/read', methods=['PUT'])
@login_required
def mark_notification_read(notification_id):
    """Marks a specific notification as read for the current user."""
    user_id = current_user.id

    # Update the notification status, ensuring it belongs to the user
    # Using execute_db which returns success status (True/False)
    success = execute_db(
        """
        UPDATE notifications
        SET is_read = TRUE, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s AND is_read = FALSE;
        """,
        (notification_id, user_id),
        commit=True
        # We don't need fetch_result here, just confirmation
    )

    if success:
        # Check if any row was actually updated (optional but good practice)
        # If the notification didn't exist, didn't belong to user, or was already read,
        # the execute_db might return success=True but 0 rows affected.
        # If we need to distinguish, we'd need to use conn/cursor directly to check rowcount.
        # For now, assume success means it likely worked or was already done.
        logger.info(f"User {user_id} marked notification {notification_id} as read.")
        # You could return the updated notification, but a simple success is often enough
        return jsonify({"status": "success", "message": "Notification marked as read"}), 200
    else:
        # This indicates a DB error occurred during the update attempt
        logger.error(f"Database error marking notification {notification_id} as read for user {user_id}.")
        return jsonify({"status": "error", "message": "Failed to mark notification as read"}), 500
    # Note: This doesn't return 404 if the notification doesn't exist for the user,
    # as the UPDATE simply wouldn't affect any rows. Adjust if 404 is desired.

# --- Admin API Endpoints ---

# --- Admin: User Management ---

@app.route('/admin/users', methods=['GET'])
@login_required
@admin_required
def admin_get_users():
    """Admin: Get a list of all users."""
    # Add filtering/pagination later if needed
    users_raw = fetch_all("SELECT id, username, email, role, balance, status, contact_name, company_name, created_at FROM users ORDER BY created_at DESC")
    users = [dict(row) for row in users_raw]
    # Convert balance Decimal to string/float if necessary for JSON
    for user in users:
        if 'balance' in user and user['balance'] is not None:
            user['balance'] = str(user['balance']) # Use string to preserve precision
    return jsonify({"status": "success", "users": users}), 200


@app.route('/admin/users', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    """Admin: Create a new user."""
    data = request.json
    required_fields = ['username', 'email', 'password', 'role', 'status']
    if not data or not all(field in data for field in required_fields):
        missing = [field for field in required_fields if not data or field not in data]
        return jsonify({"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}), 400

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'user')
    status = data.get('status', 'active')
    balance = data.get('balance', 0.0) # Allow setting initial balance
    contact_name = data.get('contact_name')
    company_name = data.get('company_name')

    # --- Validation ---
    validation_errors = []
    if not isinstance(username, str) or len(username) < 3: validation_errors.append("Username is too short.")
    if not isinstance(email, str) or '@' not in email: validation_errors.append("Invalid email format.") # Basic check
    if not isinstance(password, str) or len(password) < 8: validation_errors.append("Password must be at least 8 characters.")
    if role not in ('admin', 'user'): validation_errors.append("Invalid role.")
    if status not in ('active', 'inactive', 'suspended'): validation_errors.append("Invalid status.")
    try:
        balance = float(balance) # Or use Decimal for precision if needed throughout
    except (ValueError, TypeError): validation_errors.append("Invalid initial balance.")

    if validation_errors:
        return jsonify({"status": "error", "message": "Validation failed", "errors": validation_errors}), 400

    # Check if user/email exists
    existing_user = fetch_one("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
    if existing_user:
        return jsonify({"status": "error", "message": "Username or Email already exists."}), 409 # Conflict

    # Hash password and insert
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user_row = execute_db(
        """
        INSERT INTO users (username, email, password_hash, role, status, balance, contact_name, company_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, username, email, role, balance, status, contact_name, company_name, created_at;
        """,
        (username, email, hashed_password, role, status, balance, contact_name, company_name),
        commit=True,
        fetch_result=True
    )

    if new_user_row:
        new_user_dict = dict(new_user_row)
        if 'balance' in new_user_dict and new_user_dict['balance'] is not None:
             new_user_dict['balance'] = str(new_user_dict['balance'])
        logger.info(f"Admin {current_user.username} created user {new_user_dict['username']} (ID: {new_user_dict['id']})")
        return jsonify({"status": "success", "message": "User created successfully", "user": new_user_dict}), 201
    else:
        logger.error(f"Admin {current_user.username} failed to create user {username}")
        return jsonify({"status": "error", "message": "Failed to create user"}), 500


@app.route('/admin/users/<int:user_id>', methods=['GET'])
@login_required
@admin_required
def admin_get_user(user_id):
    """Admin: Get details for a specific user."""
    user_row = fetch_one("SELECT id, username, email, role, balance, status, contact_name, company_name, created_at, updated_at FROM users WHERE id = %s", (user_id,))
    if not user_row:
        return jsonify({"status": "error", "message": "User not found"}), 404

    user_dict = dict(user_row)
    if 'balance' in user_dict and user_dict['balance'] is not None:
         user_dict['balance'] = str(user_dict['balance'])
    return jsonify({"status": "success", "user": user_dict}), 200


@app.route('/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def admin_update_user(user_id):
    """Admin: Update user details (excluding password and balance)."""
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    # Ensure admin cannot update themselves via this endpoint? Or add checks.
    # if user_id == current_user.id:
    #    return jsonify({"status": "error", "message": "Admin cannot update their own basic details via this endpoint."}), 403

    # Fields admin can update here
    allowed_updates = ['email', 'role', 'status', 'contact_name', 'company_name']
    update_fields = {}
    validation_errors = []

    for key in allowed_updates:
        if key in data:
            value = data[key]
            # Add validation
            if key == 'email':
                 if not isinstance(value, str) or '@' not in value: validation_errors.append("Invalid email format.")
                 else: update_fields[key] = value
            elif key == 'role':
                 if value not in ('admin', 'user'): validation_errors.append("Invalid role.")
                 else: update_fields[key] = value
            elif key == 'status':
                 if value not in ('active', 'inactive', 'suspended'): validation_errors.append("Invalid status.")
                 else: update_fields[key] = value
            elif key in ['contact_name', 'company_name']:
                  # Allow empty strings? Or add length checks?
                 update_fields[key] = value # Assuming empty strings are ok

    if validation_errors:
         return jsonify({"status": "error", "message": "Validation failed", "errors": validation_errors}), 400

    if not update_fields:
        return jsonify({"status": "error", "message": "No valid fields provided for update"}), 400

    # Check for email uniqueness if email is being updated
    if 'email' in update_fields:
         existing = fetch_one("SELECT id FROM users WHERE email = %s AND id != %s", (update_fields['email'], user_id))
         if existing:
             return jsonify({"status": "error", "message": f"Email '{update_fields['email']}' is already in use."}), 409 # Conflict

    # Construct SQL query
    set_clause = ", ".join([f"{key} = %s" for key in update_fields])
    update_params = list(update_fields.values())
    update_params.append(user_id) # For WHERE id = %s

    updated_user_row = execute_db(
        f"UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING id, username, email, role, balance, status, contact_name, company_name, created_at, updated_at;",
        update_params,
        commit=True,
        fetch_result=True
    )

    if updated_user_row:
        updated_user_dict = dict(updated_user_row)
        if 'balance' in updated_user_dict and updated_user_dict['balance'] is not None:
             updated_user_dict['balance'] = str(updated_user_dict['balance'])
        logger.info(f"Admin {current_user.username} updated details for user ID {user_id}")
        return jsonify({"status": "success", "message": "User updated", "user": updated_user_dict}), 200
    else:
        # Check if user existed in the first place
        user_exists = fetch_one("SELECT id FROM users WHERE id = %s", (user_id,))
        if not user_exists:
             return jsonify({"status": "error", "message": "User not found"}), 404
        else:
             logger.error(f"Admin {current_user.username} failed to update user ID {user_id}")
             return jsonify({"status": "error", "message": "Failed to update user"}), 500


@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Admin: Delete a user."""
    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        return jsonify({"status": "error", "message": "Admin cannot delete their own account."}), 403

    # Check if user exists before attempting delete
    user_to_delete = fetch_one("SELECT username FROM users WHERE id = %s", (user_id,))
    if not user_to_delete:
        return jsonify({"status": "error", "message": "User not found"}), 404

    username_deleted = user_to_delete['username']

    # ON DELETE CASCADE should handle user's campaigns, targets, rules, notifications, requests.
    # ON DELETE SET NULL should handle dids.assigned_user_id and cdrs.user_id.
    # Balance adjustments might remain but reference a non-existent user ID. Consider cleanup.
    success = execute_db("DELETE FROM users WHERE id = %s", (user_id,), commit=True)

    if success:
        logger.info(f"Admin {current_user.username} deleted user {username_deleted} (ID: {user_id})")
        return jsonify({"status": "success", "message": "User deleted successfully"}), 200
    else:
        logger.error(f"Admin {current_user.username} failed to delete user ID {user_id}")
        return jsonify({"status": "error", "message": "Failed to delete user"}), 500

# --- Admin: Balance Adjustment ---

@app.route('/admin/balance', methods=['POST'])
@login_required
@admin_required
def admin_adjust_balance():
    """Admin: Adjust a target user's balance and log the adjustment."""
    data = request.json
    admin_user_id = current_user.id

    # --- Validation ---
    required_fields = ['target_user_id', 'amount', 'reason']
    if not data or not all(field in data for field in required_fields):
        missing = [field for field in required_fields if not data or field not in data]
        return jsonify({"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}), 400

    target_user_id_str = data.get('target_user_id')
    amount_str = data.get('amount')
    reason = data.get('reason')

    validation_errors = []
    target_user_id = None
    amount_decimal = None

    # Validate target_user_id
    try:
        target_user_id = int(target_user_id_str)
        if target_user_id <= 0:
             validation_errors.append("Invalid target_user_id.")
    except (ValueError, TypeError):
        validation_errors.append("target_user_id must be a positive integer.")

    # Validate amount (use Decimal for currency)
    try:
        amount_decimal = decimal.Decimal(amount_str)
        # Optional: Check if amount is zero? Allow it?
        # if amount_decimal == decimal.Decimal(0):
        #    validation_errors.append("Adjustment amount cannot be zero.")
    except (decimal.InvalidOperation, TypeError):
        validation_errors.append("Invalid amount format. Must be a valid number.")

    # Validate reason
    if not isinstance(reason, str) or not reason.strip():
        validation_errors.append("Reason cannot be empty.")

    if validation_errors:
         return jsonify({"status": "error", "message": "Validation failed", "errors": validation_errors}), 400

    # --- Transaction Time! ---
    conn = get_db_connection()
    if not conn: return jsonify({"status": "error", "message": "Database connection error"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # 1. Verify the target user exists
            cur.execute("SELECT balance FROM users WHERE id = %s FOR UPDATE", (target_user_id,))
            target_user = cur.fetchone()
            if not target_user:
                conn.rollback() # Release lock
                return jsonify({"status": "error", "message": f"Target user with ID {target_user_id} not found."}), 404

            current_balance = target_user['balance'] # This is a Decimal from the DB
            new_balance = current_balance + amount_decimal

            # Optional: Check if adjustment would result in negative balance
            # if new_balance < decimal.Decimal(0):
            #     # Decide whether to allow negative balances or return an error
            #     conn.rollback()
            #     return jsonify({"status": "error", "message": "Adjustment would result in a negative balance.", "new_balance_preview": str(new_balance)}), 400

            # 2. Update the user's balance
            cur.execute(
                "UPDATE users SET balance = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (new_balance, target_user_id)
            )

            # 3. Log the adjustment
            cur.execute(
                """
                INSERT INTO balance_adjustments (admin_user_id, target_user_id, amount, reason, adjustment_timestamp)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id;
                """,
                (admin_user_id, target_user_id, amount_decimal, reason.strip())
            )
            adjustment_log_id = cur.fetchone()['id']

            conn.commit()

            logger.info(f"Admin {admin_user_id} adjusted balance for user {target_user_id} by {amount_decimal}. Reason: {reason.strip()}. New balance: {new_balance}. Log ID: {adjustment_log_id}")

            # Return confirmation, including the new balance
            return jsonify({
                "status": "success",
                "message": "Balance adjusted successfully.",
                "target_user_id": target_user_id,
                "adjustment_amount": str(amount_decimal), # Return as string
                "new_balance": str(new_balance),         # Return as string
                "adjustment_log_id": adjustment_log_id
            }), 200

    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Database error adjusting balance for user {target_user_id}: {e}")
        return jsonify({"status": "error", "message": "Database error during balance adjustment"}), 500
    except Exception as e:
        conn.rollback()
        logger.exception(f"Unexpected error adjusting balance for user {target_user_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to adjust balance"}), 500
    finally:
        release_db_connection(conn)

# --- Admin: DID Request Management ---

@app.route('/admin/did_requests', methods=['GET'])
@login_required
@admin_required
def admin_get_did_requests():
    """Admin: Get a list of DID requests, optionally filtered by status."""
    allowed_statuses = ['pending', 'processing', 'assigned', 'rejected', 'all']
    status_filter = request.args.get('status', default='pending').lower()

    if status_filter not in allowed_statuses:
        return jsonify({"status": "error", "message": f"Invalid status filter. Must be one of: {', '.join(allowed_statuses)}"}), 400

    query = """
        SELECT dr.*, u.username as requesting_username
        FROM did_requests dr
        JOIN users u ON dr.user_id = u.id
    """
    params = []
    if status_filter != 'all':
        query += " WHERE dr.status = %s"
        params.append(status_filter)

    query += " ORDER BY dr.requested_at ASC;" # Oldest requests first

    requests_raw = fetch_all(query, tuple(params))
    did_requests = [dict(row) for row in requests_raw]

    return jsonify({"status": "success", "did_requests": did_requests}), 200


@app.route('/admin/did_requests/<int:request_id>/process', methods=['PUT'])
@login_required
@admin_required
def admin_process_did_request(request_id):
    """Admin: Process a DID request (assign DID or reject)."""
    data = request.json
    admin_user_id = current_user.id

    required_fields = ['status'] # Status is always required for processing
    if not data or 'status' not in data:
        return jsonify({"status": "error", "message": "Missing required 'status' field."}), 400

    new_status = data.get('status').lower()
    admin_notes = data.get('admin_notes', '').strip()
    did_id_to_assign = data.get('did_id') # Required only if status is 'assigned'

    # --- Validation ---
    validation_errors = []
    valid_processing_statuses = ['assigned', 'rejected', 'processing'] # Can't set back to 'pending' via this route
    if new_status not in valid_processing_statuses:
         validation_errors.append(f"Invalid processing status. Must be one of: {', '.join(valid_processing_statuses)}")

    did_id_int = None
    if new_status == 'assigned':
        if not did_id_to_assign:
             validation_errors.append("Missing 'did_id' field, required when status is 'assigned'.")
        else:
            try:
                did_id_int = int(did_id_to_assign)
                if did_id_int <= 0: validation_errors.append("Invalid 'did_id'.")
            except (ValueError, TypeError):
                 validation_errors.append("Invalid 'did_id' format.")
    elif did_id_to_assign is not None:
         # Prevent accidentally providing did_id when rejecting/processing
         validation_errors.append("'did_id' should only be provided when status is 'assigned'.")


    if validation_errors:
         return jsonify({"status": "error", "message": "Validation failed", "errors": validation_errors}), 400

    # --- Transaction Time! ---
    conn = get_db_connection()
    if not conn: return jsonify({"status": "error", "message": "Database connection error"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # 1. Get the request and lock it
            cur.execute("SELECT * FROM did_requests WHERE id = %s FOR UPDATE", (request_id,))
            did_request = cur.fetchone()
            if not did_request:
                conn.rollback()
                return jsonify({"status": "error", "message": f"DID Request with ID {request_id} not found."}), 404
            # Optional: Check if already processed?
            # if did_request['status'] in ['assigned', 'rejected']:
            #    conn.rollback()
            #    return jsonify({"status": "error", "message": "This request has already been processed."}), 409 # Conflict

            target_user_id = did_request['user_id'] # User who made the request

            # 2. If assigning, verify the DID exists and is assignable
            if new_status == 'assigned':
                # Check if DID exists, is unassigned, and lock it
                cur.execute("SELECT id, assignment_status, assigned_user_id FROM dids WHERE id = %s FOR UPDATE", (did_id_int,))
                did_to_assign = cur.fetchone()
                if not did_to_assign:
                     conn.rollback()
                     return jsonify({"status": "error", "message": f"DID with ID {did_id_int} not found."}), 404
                if did_to_assign['assignment_status'] == 'assigned' and did_to_assign['assigned_user_id'] != target_user_id:
                     # Allow re-assigning to the same user if status was weird? Maybe not.
                     conn.rollback()
                     return jsonify({"status": "error", "message": f"DID {did_id_int} is already assigned to another user."}), 409 # Conflict
                # All checks passed for DID assignment

                # Update the DID status and assign user
                cur.execute(
                    "UPDATE dids SET assignment_status = 'assigned', assigned_user_id = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (target_user_id, did_id_int)
                )
                assigned_did_column_value = did_id_int
            else:
                # Rejecting or marking as processing, no DID is assigned via the request
                assigned_did_column_value = None
                # If rejecting a previously assigned request (edge case?), maybe unassign the linked DID? Needs careful thought.


            # 3. Update the DID Request status and details
            cur.execute(
                """
                UPDATE did_requests
                SET status = %s, admin_notes = %s, assigned_did_id = %s, processed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (new_status, admin_notes, assigned_did_column_value, request_id)
            )

            conn.commit()

            logger.info(f"Admin {admin_user_id} processed DID request {request_id}. Status set to '{new_status}'. Assigned DID: {assigned_did_column_value}. Notes: '{admin_notes}'")

            # Optional: Create notification for the requesting user
            # notify_user(target_user_id, f"Your DID request #{request_id} has been {new_status}.", 'info')

            # Fetch the updated request to return
            updated_request = fetch_one("SELECT dr.*, u.username as requesting_username FROM did_requests dr JOIN users u ON dr.user_id = u.id WHERE dr.id = %s", (request_id,))

            return jsonify({"status": "success", "message": f"DID Request {request_id} processed.", "request": dict(updated_request)}), 200

    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Database error processing DID request {request_id}: {e}")
        return jsonify({"status": "error", "message": "Database error during DID request processing"}), 500
    except Exception as e:
        conn.rollback()
        logger.exception(f"Unexpected error processing DID request {request_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to process DID request"}), 500
    finally:
        release_db_connection(conn)

# --- Admin: DID Inventory Management ---

@app.route('/admin/dids', methods=['POST'])
@login_required
@admin_required
def admin_add_did():
    """Admin: Manually add a new DID to the inventory."""
    data = request.json
    required_fields = ['number', 'country_code', 'number_type']
    if not data or not all(field in data for field in required_fields):
        missing = [field for field in required_fields if not data or field not in data]
        return jsonify({"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}), 400

    number = data.get('number')
    country_code = data.get('country_code')
    number_type = data.get('number_type')
    provider_source = data.get('provider_source') # Optional
    monthly_cost = data.get('monthly_cost')     # Optional
    # Admin could potentially assign it directly on creation, but let's keep it simple: add as unassigned by default.
    assignment_status = 'unassigned'
    assigned_user_id = None

    # --- Validation ---
    validation_errors = []
    if not isinstance(number, str) or not number.strip(): # Add E.164 format validation?
        validation_errors.append("DID Number cannot be empty.")
    if not isinstance(country_code, str) or len(country_code) > 5: # Basic check
         validation_errors.append("Invalid Country Code.")
    if number_type not in ('TFN', 'Local', 'Mobile', 'Other'):
         validation_errors.append("Invalid Number Type.")
    if monthly_cost is not None:
        try:
            # Use Decimal for currency precision
            monthly_cost = decimal.Decimal(monthly_cost)
            if monthly_cost < 0: validation_errors.append("Monthly cost cannot be negative.")
        except (decimal.InvalidOperation, TypeError):
            validation_errors.append("Invalid monthly_cost format.")

    if validation_errors:
         return jsonify({"status": "error", "message": "Validation failed", "errors": validation_errors}), 400

    # Check if number already exists
    if fetch_one("SELECT id FROM dids WHERE number = %s", (number.strip(),)):
        return jsonify({"status": "error", "message": f"DID number '{number.strip()}' already exists."}), 409

    # --- Insert ---
    new_did_row = execute_db(
        """
        INSERT INTO dids (number, country_code, number_type, assignment_status, assigned_user_id, provider_source, monthly_cost)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *;
        """,
        (number.strip(), country_code, number_type, assignment_status, assigned_user_id, provider_source, monthly_cost),
        commit=True,
        fetch_result=True
    )

    if new_did_row:
        new_did_dict = dict(new_did_row)
        if 'monthly_cost' in new_did_dict and new_did_dict['monthly_cost'] is not None:
            new_did_dict['monthly_cost'] = str(new_did_dict['monthly_cost']) # Convert decimal
        logger.info(f"Admin {current_user.username} added DID {new_did_dict['number']} (ID: {new_did_dict['id']}) to inventory.")
        return jsonify({"status": "success", "message": "DID added to inventory.", "did": new_did_dict}), 201
    else:
        logger.error(f"Admin {current_user.username} failed to add DID {number.strip()}")
        return jsonify({"status": "error", "message": "Failed to add DID"}), 500


@app.route('/admin/dids', methods=['GET'])
@login_required
@admin_required
def admin_get_dids():
    """Admin: Get a list of ALL DIDs, with filtering options."""
    # Potential filters: status, user_id, number contains, type, country
    status_filter = request.args.get('status')
    user_id_filter = request.args.get('user_id')
    # Add more filters as needed...

    base_query = """
        SELECT
            d.*, u.username as assigned_username,
            COALESCE(jsonb_agg(DISTINCT c.name) FILTER (WHERE c.id IS NOT NULL), '[]'::jsonb) AS linked_campaigns
        FROM dids d
        LEFT JOIN users u ON d.assigned_user_id = u.id
        LEFT JOIN campaign_dids cd ON d.id = cd.did_id
        LEFT JOIN campaigns c ON cd.campaign_id = c.id
    """
    where_clauses = []
    params = []

    if status_filter and status_filter in ('unassigned', 'assigned', 'pending_request'):
        where_clauses.append("d.assignment_status = %s")
        params.append(status_filter)
    if user_id_filter:
         try:
             user_id = int(user_id_filter)
             where_clauses.append("d.assigned_user_id = %s")
             params.append(user_id)
         except ValueError:
              return jsonify({"status": "error", "message": "Invalid user_id filter."}), 400

    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    base_query += " GROUP BY d.id, u.username ORDER BY d.number;" # Group by necessary fields

    dids_raw = fetch_all(base_query, tuple(params))
    dids = []
    for row in dids_raw:
        row_dict = dict(row)
        if 'monthly_cost' in row_dict and row_dict['monthly_cost'] is not None:
            row_dict['monthly_cost'] = str(row_dict['monthly_cost']) # Convert decimal
        dids.append(row_dict)

    return jsonify({"status": "success", "dids": dids}), 200


@app.route('/admin/dids/<int:did_id>', methods=['GET'])
@login_required
@admin_required
def admin_get_did(did_id):
    """Admin: Get details for a specific DID."""
    did_row = fetch_one("""
        SELECT
            d.*, u.username as assigned_username,
            COALESCE(jsonb_agg(DISTINCT c.name) FILTER (WHERE c.id IS NOT NULL), '[]'::jsonb) AS linked_campaigns
        FROM dids d
        LEFT JOIN users u ON d.assigned_user_id = u.id
        LEFT JOIN campaign_dids cd ON d.id = cd.did_id
        LEFT JOIN campaigns c ON cd.campaign_id = c.id
        WHERE d.id = %s
        GROUP BY d.id, u.username;
    """, (did_id,))

    if not did_row:
        return jsonify({"status": "error", "message": "DID not found"}), 404

    did_dict = dict(did_row)
    if 'monthly_cost' in did_dict and did_dict['monthly_cost'] is not None:
        did_dict['monthly_cost'] = str(did_dict['monthly_cost']) # Convert decimal

    return jsonify({"status": "success", "did": did_dict}), 200


@app.route('/admin/dids/<int:did_id>', methods=['PUT'])
@login_required
@admin_required
def admin_update_did(did_id):
    """Admin: Update details for a specific DID (cost, provider, assignment)."""
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    # Check if DID exists first
    did_current = fetch_one("SELECT * FROM dids WHERE id = %s", (did_id,))
    if not did_current:
        return jsonify({"status": "error", "message": "DID not found"}), 404

    # Fields admin can update
    allowed_updates = ['country_code', 'number_type', 'provider_source', 'monthly_cost', 'assignment_status', 'assigned_user_id']
    update_fields = {}
    validation_errors = []

    new_assigned_user_id = data.get('assigned_user_id', 'UNCHANGED') # Special marker
    new_assignment_status = data.get('assignment_status', did_current['assignment_status']) # Default to current

    # Validate assignment logic first
    target_user_id = None
    if new_assigned_user_id != 'UNCHANGED':
        if new_assigned_user_id is None:
            # Request to unassign
            new_assignment_status = 'unassigned'
            target_user_id = None
        else:
            # Request to assign to a specific user
            try:
                target_user_id = int(new_assigned_user_id)
                if target_user_id <= 0: raise ValueError()
                # Verify target user exists
                if not fetch_one("SELECT id FROM users WHERE id = %s", (target_user_id,)):
                     validation_errors.append(f"User with ID {target_user_id} not found.")
                else:
                     new_assignment_status = 'assigned' # Force status if assigning user
            except (ValueError, TypeError):
                 validation_errors.append("Invalid assigned_user_id format.")

        update_fields['assigned_user_id'] = target_user_id # Store None or the valid int
        update_fields['assignment_status'] = new_assignment_status
    else:
         # If user_id not changing, but status is - validate status
         if 'assignment_status' in data:
             if new_assignment_status not in ('unassigned', 'assigned', 'pending_request'):
                 validation_errors.append("Invalid assignment_status.")
             # Logic check: Cannot set 'assigned' without a user_id, cannot set 'unassigned/pending' if user_id is present
             elif new_assignment_status == 'assigned' and did_current['assigned_user_id'] is None:
                  validation_errors.append("Cannot set status to 'assigned' without providing a valid assigned_user_id.")
             elif new_assignment_status in ('unassigned', 'pending_request') and did_current['assigned_user_id'] is not None:
                  validation_errors.append(f"Cannot set status to '{new_assignment_status}' while a user is assigned. Set assigned_user_id to null first.")
             else:
                 update_fields['assignment_status'] = new_assignment_status


    # Validate other fields if present
    for key in allowed_updates:
        if key in data and key not in ['assigned_user_id', 'assignment_status']: # Already handled
            value = data[key]
            if key == 'number_type':
                 if value not in ('TFN', 'Local', 'Mobile', 'Other'): validation_errors.append("Invalid Number Type.")
                 else: update_fields[key] = value
            elif key == 'monthly_cost':
                 if value is None:
                     update_fields[key] = None
                 else:
                     try:
                         value_dec = decimal.Decimal(value)
                         if value_dec < 0: validation_errors.append("Monthly cost cannot be negative.")
                         else: update_fields[key] = value_dec
                     except (decimal.InvalidOperation, TypeError): validation_errors.append("Invalid monthly_cost format.")
            else: # country_code, provider_source (basic string checks)
                if value is not None and not isinstance(value, str):
                     validation_errors.append(f"Invalid format for {key}.")
                else:
                     update_fields[key] = value


    if validation_errors:
         return jsonify({"status": "error", "message": "Validation failed", "errors": list(set(validation_errors))}), 400

    if not update_fields:
        return jsonify({"status": "error", "message": "No valid fields provided for update"}), 400

    # --- Update Database ---
    set_clause = ", ".join([f"{key} = %s" for key in update_fields])
    update_params = list(update_fields.values())
    update_params.append(did_id) # For WHERE id = %s

    updated_did_row = execute_db(
        f"UPDATE dids SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *;",
        update_params,
        commit=True,
        fetch_result=True
    )

    if updated_did_row:
        updated_did_dict = dict(updated_did_row)
        if 'monthly_cost' in updated_did_dict and updated_did_dict['monthly_cost'] is not None:
             updated_did_dict['monthly_cost'] = str(updated_did_dict['monthly_cost'])
        logger.info(f"Admin {current_user.username} updated DID ID {did_id}")
        # Important: If DID was unassigned, need to remove from any campaigns it was linked to!
        if updated_did_dict.get('assignment_status') == 'unassigned':
            execute_db("DELETE FROM campaign_dids WHERE did_id = %s", (did_id,), commit=True)
            logger.info(f"Removed campaign links for unassigned DID ID {did_id}")

        return jsonify({"status": "success", "message": "DID updated", "did": updated_did_dict}), 200
    else:
         # Should not happen if initial check passed, unless DB error
         logger.error(f"Admin {current_user.username} failed to update DID ID {did_id}")
         return jsonify({"status": "error", "message": "Failed to update DID"}), 500


@app.route('/admin/dids/<int:did_id>', methods=['DELETE'])
@login_required
@admin_required
def admin_delete_did(did_id):
    """Admin: Delete a DID from the system."""
    # Check if DID exists before attempting delete
    did_to_delete = fetch_one("SELECT number FROM dids WHERE id = %s", (did_id,))
    if not did_to_delete:
        return jsonify({"status": "error", "message": "DID not found"}), 404

    did_number_deleted = did_to_delete['number']

    # ON DELETE CASCADE should handle campaign_dids links.
    # ON DELETE SET NULL should handle did_requests.assigned_did_id.
    # CDRs retain the number string but lose the FK link (if DID ID was stored there, but we store the number).
    # Need to consider implications if calls are *active* using this DID? (Advanced)
    success = execute_db("DELETE FROM dids WHERE id = %s", (did_id,), commit=True)

    if success:
        logger.info(f"Admin {current_user.username} deleted DID {did_number_deleted} (ID: {did_id})")
        return jsonify({"status": "success", "message": "DID deleted successfully"}), 200
    else:
        logger.error(f"Admin {current_user.username} failed to delete DID ID {did_id}")
        return jsonify({"status": "error", "message": "Failed to delete DID"}), 500

# --- Admin: System Settings ---

@app.route('/admin/settings', methods=['GET'])
@login_required
@admin_required
def admin_get_settings():
    """Admin: Get all system settings."""
    settings_raw = fetch_all("SELECT setting_key, setting_value, description, updated_at FROM system_settings ORDER BY setting_key;")
    # Convert rows to a dictionary {key: {value: v, description: d, updated_at: t}} for easier access
    settings_dict = {row['setting_key']: {'value': row['setting_value'], 'description': row['description'], 'updated_at': row['updated_at']} for row in settings_raw}
    return jsonify({"status": "success", "settings": settings_dict}), 200


@app.route('/admin/settings/<string:setting_key>', methods=['PUT'])
@login_required
@admin_required
def admin_update_setting(setting_key):
    """Admin: Update a specific system setting."""
    data = request.json
    if not data or 'value' not in data:
         return jsonify({"status": "error", "message": "Missing 'value' field in request body."}), 400

    new_value = data.get('value') # Value is stored as TEXT, validation depends on the key

    # --- Validation (Optional - depends on the setting) ---
    validation_errors = []
    # Example: Validate billing rate
    if setting_key == 'billing_rate_per_minute':
        try:
            # Use Decimal for financial values
            rate_decimal = decimal.Decimal(new_value)
            if rate_decimal < 0:
                 validation_errors.append("Billing rate cannot be negative.")
            # Format the value consistently before saving (e.g., 4 decimal places)
            new_value = f"{rate_decimal:.4f}" # Store as string with fixed precision
        except (decimal.InvalidOperation, TypeError):
            validation_errors.append("Invalid format for billing_rate_per_minute. Must be a number.")
    # Add validation for other setting keys as needed...

    if validation_errors:
        return jsonify({"status": "error", "message": "Validation failed", "errors": validation_errors}), 400


    # --- Check if setting exists and Update ---
    # Use INSERT ... ON CONFLICT UPDATE (Upsert) to handle existing or new keys robustly
    # Requires setting_key to be the PRIMARY KEY or have a UNIQUE constraint
    updated_setting_row = execute_db(
        """
        INSERT INTO system_settings (setting_key, setting_value, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (setting_key) DO UPDATE SET
            setting_value = EXCLUDED.setting_value,
            updated_at = CURRENT_TIMESTAMP
        RETURNING setting_key, setting_value, description, updated_at;
        """,
        (setting_key, str(new_value)), # Ensure value is stored as string (TEXT column)
        commit=True,
        fetch_result=True
    )

    if updated_setting_row:
         updated_setting = {
            'value': updated_setting_row['setting_value'],
            'description': updated_setting_row['description'],
            'updated_at': updated_setting_row['updated_at']
         }
         logger.info(f"Admin {current_user.username} updated system setting '{setting_key}' to '{new_value}'")
         return jsonify({"status": "success", "message": f"Setting '{setting_key}' updated.", "setting": {setting_key: updated_setting}}), 200
    else:
         # This path might be hard to reach with ON CONFLICT unless there's a DB error
         logger.error(f"Admin {current_user.username} failed to update setting '{setting_key}'")
         # Could check if the key exists if we didn't use ON CONFLICT
         return jsonify({"status": "error", "message": f"Failed to update setting '{setting_key}'"}), 500

# --- Internal API Routes (for Asterisk AGI) ---

# !! IMPORTANT: Secure this endpoint properly in a production environment !!
# Allow only localhost or use a secret token authentication.
# Example basic IP check:
# def require_local(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if request.remote_addr != '127.0.0.1':
#             logger.warning(f"Unauthorized access attempt to internal API from {request.remote_addr}")
#             return jsonify({"status": "error", "reason": "forbidden"}), 403
#         return f(*args, **kwargs)
#     return decorated_function

@app.route('/internal_api/route_info', methods=['GET'])
# @require_local # Uncomment to apply basic IP restriction if require_local decorator is defined
def internal_route_info():
    """
    Internal endpoint called by Asterisk AGI.
    Determines routing based on DID, checks caps and balance.
    Returns routing info or rejection reason.
    """
    # Get DID from request args safely
    did_param = request.args.get('did')
    did_for_log = did_param if did_param else 'UNKNOWN' # Use for logging in exceptions/finally

    if not did_param:
        logger.warning("Internal route_info call missing 'did' parameter.")
        return jsonify({"status": "reject", "reject_reason": "missing_did_parameter"}), 400

    logger.info(f"Internal route_info request received for DID: {did_param}")

    conn = get_db_connection()
    if not conn:
        logger.error(f"Internal route_info: Failed to get DB connection for DID {did_for_log}.")
        # Return a generic failure, Asterisk should handle this (e.g., fast busy)
        return jsonify({"status": "reject", "reject_reason": "internal_server_error"}), 503 # 503 Service Unavailable

    # --- Variables to store results ---
    rejection_reason = None
    routing_info = {}

    try:
        # --- Start Transaction ---
        # We need a transaction especially for the cap checking/resetting logic.
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

            # 1. Find the DID and its owner
            logger.debug(f"Querying for DID number: '{did_param}'") # Log the exact param
            cur.execute("""
                SELECT id, assigned_user_id, assignment_status
                FROM dids
                WHERE number = %s FOR UPDATE
            """, (did_param,)) # Lock DID row briefly
            did_data = cur.fetchone()
            logger.debug(f"Query result for DID {did_param}: {did_data}") # Log the result


            if not did_data:
                rejection_reason = "did_not_found"
                # No need to rollback here as nothing was changed yet
                logger.warning(f"DID not found: {did_param}")
                # Don't release connection here, finally block will do it
                return jsonify({"status": "reject", "reject_reason": rejection_reason}), 404
            if did_data['assignment_status'] != 'assigned' or did_data['assigned_user_id'] is None:
                rejection_reason = "did_inactive_or_unassigned"
                # No need to rollback
                logger.warning(f"DID {did_param} is not active/assigned. Status: {did_data['assignment_status']}")
                return jsonify({"status": "reject", "reject_reason": rejection_reason}), 403 # Use 403 Forbidden?

            did_id = did_data['id']
            user_id = did_data['assigned_user_id']
            routing_info['user_id'] = user_id

            # 2. Find the Active Campaign linked to this DID
            cur.execute("""
                SELECT
                    c.id, c.status, c.cap_hourly, c.cap_daily, c.cap_total,
                    c.current_hourly_calls, c.current_daily_calls, c.current_total_calls,
                    c.last_hourly_reset, c.last_daily_reset
                FROM campaigns c
                JOIN campaign_dids cd ON c.id = cd.campaign_id
                WHERE cd.did_id = %s AND c.user_id = %s AND c.status = 'active'
                LIMIT 1 FOR UPDATE;
            """, (did_id, user_id)) # Lock campaign row
            campaign_data = cur.fetchone()

            if not campaign_data:
                rejection_reason = "no_active_campaign_for_did"
                conn.rollback() # Release row locks
                logger.warning(f"No active campaign found for DID ID {did_id} (User: {user_id})")
                return jsonify({"status": "reject", "reject_reason": rejection_reason}), 404

            campaign_id = campaign_data['id']
            routing_info['campaign_id'] = campaign_id

            # 3. Check Campaign Volume Caps (and reset if necessary)
            now = datetime.now(timezone.utc)
            update_campaign_caps = {} # Store fields to update

            # Hourly Cap Check/Reset
            if campaign_data['cap_hourly'] is not None:
                last_reset = campaign_data['last_hourly_reset']
                if now.date() != last_reset.date() or now.hour != last_reset.hour:
                    logger.info(f"Resetting hourly cap for campaign {campaign_id}. Previous hour: {last_reset}")
                    current_hourly = 0
                    update_campaign_caps['current_hourly_calls'] = 0
                    update_campaign_caps['last_hourly_reset'] = now
                else:
                    current_hourly = campaign_data['current_hourly_calls']

                if current_hourly >= campaign_data['cap_hourly']:
                    rejection_reason = "volume_cap_hourly"
                    conn.rollback()
                    logger.warning(f"Campaign {campaign_id} rejected: Hourly cap ({campaign_data['cap_hourly']}) reached.")
                    return jsonify({"status": "reject", "reject_reason": rejection_reason}), 429

            # Daily Cap Check/Reset
            if campaign_data['cap_daily'] is not None:
                last_reset = campaign_data['last_daily_reset']
                if now.date() != last_reset.date():
                    logger.info(f"Resetting daily cap for campaign {campaign_id}. Previous day: {last_reset}")
                    current_daily = 0
                    update_campaign_caps['current_daily_calls'] = 0
                    update_campaign_caps['last_daily_reset'] = now
                else:
                    current_daily = campaign_data['current_daily_calls']

                if current_daily >= campaign_data['cap_daily']:
                    rejection_reason = "volume_cap_daily"
                    conn.rollback()
                    logger.warning(f"Campaign {campaign_id} rejected: Daily cap ({campaign_data['cap_daily']}) reached.")
                    return jsonify({"status": "reject", "reject_reason": rejection_reason}), 429

            # Total Cap Check
            if campaign_data['cap_total'] is not None:
                if campaign_data['current_total_calls'] >= campaign_data['cap_total']:
                    rejection_reason = "volume_cap_total"
                    conn.rollback()
                    logger.warning(f"Campaign {campaign_id} rejected: Total cap ({campaign_data['cap_total']}) reached.")
                    return jsonify({"status": "reject", "reject_reason": rejection_reason}), 429

            # Apply cap counter resets if any occurred
            if update_campaign_caps:
                 set_clauses = [f"{key} = %s" for key in update_campaign_caps]
                 params = list(update_campaign_caps.values()) + [campaign_id]
                 cur.execute(f"UPDATE campaigns SET {', '.join(set_clauses)} WHERE id = %s", tuple(params))
                 logger.info(f"Updated cap resets for campaign {campaign_id}: {update_campaign_caps}")

            # 4. Check User Balance
            cur.execute("SELECT balance FROM users WHERE id = %s FOR UPDATE", (user_id,)) # Lock user row
            user_data = cur.fetchone()
            if not user_data:
                rejection_reason = "user_not_found"
                conn.rollback()
                logger.error(f"User not found for ID {user_id} associated with DID {did_param}")
                return jsonify({"status": "reject", "reject_reason": rejection_reason}), 500

            if user_data['balance'] <= decimal.Decimal(0):
                 rejection_reason = "balance_low"
                 conn.rollback()
                 logger.warning(f"User {user_id} rejected: Low balance ({user_data['balance']}).")
                 return jsonify({"status": "reject", "reject_reason": rejection_reason}), 402

            routing_info['balance_ok'] = True

            # 5. Find Active Forwarding Rule linked to the Campaign
            cur.execute("""
                SELECT id, routing_strategy, min_billable_duration
                FROM forwarding_rules fr
                JOIN rule_campaigns rc ON fr.id = rc.rule_id
                WHERE rc.campaign_id = %s AND fr.user_id = %s AND fr.status = 'active'
                LIMIT 1;
            """, (campaign_id, user_id))
            rule_data = cur.fetchone()

            if not rule_data:
                rejection_reason = "no_active_rule_for_campaign"
                conn.rollback()
                logger.warning(f"No active forwarding rule found for campaign {campaign_id} (User: {user_id})")
                return jsonify({"status": "reject", "reject_reason": rejection_reason}), 404

            routing_info['rule_id'] = rule_data['id']
            routing_info['routing_strategy'] = rule_data['routing_strategy']
            routing_info['min_billable_duration'] = rule_data['min_billable_duration']

            # 6. Find Eligible Targets linked to the Rule
            cur.execute("""
                SELECT
                    t.id, t.destination_uri, t.concurrency_limit,
                    t.total_calls_allowed, t.current_total_calls_delivered,
                    rt.priority, rt.weight
                FROM targets t
                JOIN rule_targets rt ON t.id = rt.target_id
                WHERE rt.rule_id = %s AND t.user_id = %s AND t.status = 'active'
                ORDER BY rt.priority ASC, rt.weight DESC;
            """, (routing_info['rule_id'], user_id))
            all_targets_raw = cur.fetchall()

            if not all_targets_raw:
                rejection_reason = "no_active_targets_in_rule"
                conn.rollback()
                logger.warning(f"No active targets found for rule {routing_info['rule_id']} (User: {user_id})")
                return jsonify({"status": "reject", "reject_reason": rejection_reason}), 404

            # 7. Filter Targets by Total Cap
            eligible_targets = []
            for target in all_targets_raw:
                is_capped = False
                if target['total_calls_allowed'] is not None:
                    if target['current_total_calls_delivered'] >= target['total_calls_allowed']:
                        is_capped = True
                        logger.info(f"Target ID {target['id']} skipped: Total cap ({target['total_calls_allowed']}) reached.")
                if not is_capped:
                    eligible_targets.append({
                        "id": target['id'],
                        "uri": target['destination_uri'],
                        "concurrency_limit": target['concurrency_limit'],
                        "priority": target['priority'],
                        "weight": target['weight']
                    })

            if not eligible_targets:
                rejection_reason = "all_targets_cap_reached"
                conn.rollback()
                logger.warning(f"All active targets for rule {routing_info['rule_id']} have reached their total call cap.")
                return jsonify({"status": "reject", "reject_reason": rejection_reason}), 429

            # 8. Select Target(s) based on Strategy
            routing_info['targets'] = eligible_targets

            # 9. Get System Settings (Billing Rate)
            cur.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'billing_rate_per_minute'")
            rate_setting = cur.fetchone()
            try:
                 rate_decimal = decimal.Decimal(rate_setting['setting_value']) if rate_setting else decimal.Decimal('0.00')
            except (decimal.InvalidOperation, TypeError):
                 logger.error("Invalid billing_rate_per_minute format in system_settings.")
                 rate_decimal = decimal.Decimal('0.00')

            routing_info['cost_rate_per_minute'] = str(rate_decimal) # Store as string in response

            # --- All checks passed, Commit Transaction (cap resets) ---
            conn.commit()

            logger.info(f"Routing info generated for DID {did_param}: Proceeding to targets for rule {routing_info['rule_id']}")
            return jsonify({"status": "proceed", **routing_info}), 200 # Combine dicts

    except psycopg2.Error as db_err:
        conn.rollback() # Rollback on any DB error during the process
        logger.error(f"Database error processing route_info for DID {did_for_log}: {db_err}")
        return jsonify({"status": "reject", "reject_reason": "internal_db_error"}), 500
    except Exception as e:
        conn.rollback() # Rollback on any unexpected error
        logger.exception(f"Unexpected error processing route_info for DID {did_for_log}: {e}") # Log full traceback
        return jsonify({"status": "reject", "reject_reason": "internal_server_error"}), 500
    finally:
        # Release the connection back to the pool
        logger.debug(f"Finished processing route_info for DID {did_for_log}. Releasing DB connection.")
        release_db_connection(conn)

@app.route('/internal_api/log_cdr', methods=['POST'])
# @require_local # Uncomment to apply basic IP restriction
def internal_log_cdr():
    """
    Internal endpoint called by Asterisk AGI after a call attempt.
    Logs the CDR and performs balance/counter updates if applicable.
    """
    cdr_data = request.json
    # Use Asterisk Unique ID for logging correlation if available
    log_call_id = cdr_data.get('asterisk_uniqueid', 'UNKNOWN_ID') if cdr_data else 'UNKNOWN_ID_NO_DATA'

    if not cdr_data:
        logger.error(f"Internal log_cdr ({log_call_id}): Received empty request body.")
        return jsonify({"status": "error", "message": "No CDR data received"}), 400

    # --- Basic Validation (AGI script must send these) ---
    required_fields = [
        'user_id', 'timestamp_start', 'caller_id_num', 'incoming_did',
        'final_status', 'asterisk_uniqueid'
    ]
    missing = [field for field in required_fields if field not in cdr_data]
    if missing:
        logger.error(f"Internal log_cdr ({log_call_id}): Missing required fields: {', '.join(missing)}. Data: {cdr_data}")
        return jsonify({"status": "error", "message": f"Missing required CDR fields: {', '.join(missing)}"}), 400

    logger.info(f"Internal log_cdr request received: AsteriskID {log_call_id}, Status {cdr_data.get('final_status')}")

    # --- Sanitize/Prepare Data ---
    try:
        user_id = int(cdr_data['user_id'])
        campaign_id = int(cdr_data['campaign_id']) if cdr_data.get('campaign_id') is not None else None
        target_id = int(cdr_data['target_id']) if cdr_data.get('target_id') is not None else None
        duration = int(cdr_data['duration']) if cdr_data.get('duration') is not None else None
        billable_duration = int(cdr_data['billable_duration']) if cdr_data.get('billable_duration') is not None else 0 # Default to 0
        cost_rate_per_minute = decimal.Decimal(cdr_data.get('cost_rate_per_minute', '0.00'))
        # Ensure required string fields exist for logging clarity, even if empty
        incoming_did = cdr_data.get('incoming_did', '')
        caller_id_num = cdr_data.get('caller_id_num', '')
        final_status = cdr_data.get('final_status', 'UNKNOWN')

    except (ValueError, TypeError, decimal.InvalidOperation) as e:
        logger.error(f"Internal log_cdr ({log_call_id}): Invalid data type for numeric/decimal fields. Error: {e}. Data: {cdr_data}")
        return jsonify({"status": "error", "message": "Invalid data type in CDR fields."}), 400

    calculated_cost = decimal.Decimal('0.00')
    perform_billing_updates = False

    if billable_duration > 0:
        perform_billing_updates = True
        calculated_cost = (decimal.Decimal(billable_duration) / decimal.Decimal(60)) * cost_rate_per_minute
        calculated_cost = calculated_cost.quantize(decimal.Decimal("0.00001"), rounding=decimal.ROUND_HALF_UP)
        logger.info(f"Internal log_cdr ({log_call_id}): Calculated cost: {calculated_cost} (Duration: {billable_duration}s, Rate: {cost_rate_per_minute}/min)")
    else:
         logger.info(f"Internal log_cdr ({log_call_id}): No billing updates needed (Billable duration: {billable_duration}s).")


    # --- Transaction Time! ---
    conn = get_db_connection()
    if not conn:
        logger.error(f"Internal log_cdr ({log_call_id}): Failed to get DB connection.")
        return jsonify({"status": "error", "message": "Database connection error"}), 503

    new_cdr_id = None # Initialize in case insert fails but we reach finally
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            logger.debug(f"Internal log_cdr ({log_call_id}): Starting transaction.")

            # 1. Insert the base CDR record
            logger.debug(f"Internal log_cdr ({log_call_id}): Attempting CDR insert.")
            cur.execute(
                """
                INSERT INTO call_detail_records (
                    user_id, timestamp_start, timestamp_answer, timestamp_end,
                    duration, billable_duration, caller_id_num, caller_id_name,
                    incoming_did, campaign_id, target_id, final_status,
                    asterisk_status_code, recording_path, calculated_cost,
                    asterisk_uniqueid, asterisk_linkedid
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id;
                """,
                (
                    user_id, cdr_data.get('timestamp_start'), cdr_data.get('timestamp_answer'),
                    cdr_data.get('timestamp_end'), duration,
                    billable_duration if perform_billing_updates else 0,
                    caller_id_num, cdr_data.get('caller_id_name'), incoming_did,
                    campaign_id, target_id, final_status,
                    cdr_data.get('asterisk_status_code'), cdr_data.get('recording_path'),
                    calculated_cost if perform_billing_updates else decimal.Decimal('0.00'),
                    log_call_id, # Use the variable we defined earlier
                    cdr_data.get('asterisk_linkedid')
                )
            )
            new_cdr_id = cur.fetchone()['id']
            logger.info(f"Internal log_cdr ({log_call_id}): Inserted CDR ID {new_cdr_id}.")

            # 2. Perform billing/counter updates IF required
            if perform_billing_updates:
                logger.debug(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Performing billing updates.")

                # a) Decrement user balance (atomic update)
                logger.debug(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Attempting balance update for user {user_id} by {-calculated_cost}.")
                cur.execute(
                    "UPDATE users SET balance = balance - %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING balance;", # Return new balance for logging
                    (calculated_cost, user_id)
                )
                new_balance_result = cur.fetchone()
                if new_balance_result:
                     logger.info(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Decremented balance by {calculated_cost} for user {user_id}. New balance: {new_balance_result['balance']}")
                else:
                     logger.warning(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): User {user_id} not found during balance update, but CDR inserted.")
                     # Decide if this should cause a rollback - likely yes.
                     # conn.rollback()
                     # return jsonify({"status":"error", "message":"User inconsistency"}), 500


                # b) Increment target total calls delivered (if target involved)
                if target_id:
                    logger.debug(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Attempting target counter update for target {target_id}.")
                    cur.execute(
                        "UPDATE targets SET current_total_calls_delivered = current_total_calls_delivered + 1, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING current_total_calls_delivered;",
                        (target_id,)
                    )
                    calls_delivered_result = cur.fetchone()
                    if calls_delivered_result:
                         logger.info(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Incremented total calls delivered for target {target_id}. New count: {calls_delivered_result['current_total_calls_delivered']}")
                    else:
                         logger.warning(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Target {target_id} not found during counter update, but CDR inserted.")
                         # Decide if this should cause a rollback
                         # conn.rollback()
                         # return jsonify({"status":"error", "message":"Target inconsistency"}), 500
                else:
                     logger.debug(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): No target ID provided, skipping target counter update.")


                # c) Increment campaign counters (if campaign involved)
                if campaign_id:
                    logger.debug(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Attempting campaign counter update for campaign {campaign_id}.")
                    cur.execute(
                        """
                        UPDATE campaigns SET
                            current_hourly_calls = current_hourly_calls + 1,
                            current_daily_calls = current_daily_calls + 1,
                            current_total_calls = current_total_calls + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s RETURNING current_hourly_calls, current_daily_calls, current_total_calls;
                        """,
                        (campaign_id,)
                    )
                    campaign_counters_result = cur.fetchone()
                    if campaign_counters_result:
                         logger.info(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Incremented hourly/daily/total calls for campaign {campaign_id}. New counts: H={campaign_counters_result['current_hourly_calls']}, D={campaign_counters_result['current_daily_calls']}, T={campaign_counters_result['current_total_calls']}")
                    else:
                          logger.warning(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Campaign {campaign_id} not found during counter update, but CDR inserted.")
                          # Decide if this should cause a rollback
                          # conn.rollback()
                          # return jsonify({"status":"error", "message":"Campaign inconsistency"}), 500
                else:
                    logger.debug(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): No campaign ID provided, skipping campaign counter update.")

            # --- All updates successful (or skipped) ---
            logger.info(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Attempting to commit transaction...")
            conn.commit()
            logger.info(f"Internal log_cdr ({log_call_id}, CDR: {new_cdr_id}): Successfully committed transaction.")
            return jsonify({"status": "success", "message": "CDR logged successfully", "cdr_id": new_cdr_id}), 201

    except psycopg2.IntegrityError as int_err:
         conn.rollback()
         logger.warning(f"Internal log_cdr ({log_call_id}): Integrity error logging CDR (likely duplicate uniqueid): {int_err}")
         return jsonify({"status": "error", "message": "Integrity constraint violation (e.g., duplicate call ID)"}), 409
    except psycopg2.Error as db_err:
        conn.rollback()
        logger.error(f"Internal log_cdr ({log_call_id}, Attempted CDR: {new_cdr_id}): Database error during transaction: {db_err}")
        return jsonify({"status": "error", "message": "Database error during CDR logging"}), 500
    except Exception as e:
        conn.rollback()
        logger.exception(f"Internal log_cdr ({log_call_id}, Attempted CDR: {new_cdr_id}): Unexpected error during transaction: {e}")
        return jsonify({"status": "error", "message": "Internal server error during CDR logging"}), 500
    finally:
        logger.debug(f"Internal log_cdr ({log_call_id}, Attempted CDR: {new_cdr_id}): Releasing DB connection.")
        release_db_connection(conn)

# --- Main Execution ---
if __name__ == '__main__':
    # Debug will be True if FLASK_ENV=development in .env
    # Host 0.0.0.0 makes it accessible externally (within your local network)
    # Port 5000 is the Flask default
    app.run(host='0.0.0.0', port=5000, debug=True) # Ensure debug=True for development
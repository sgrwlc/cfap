# /opt/call_platform/app.py  <- This path comment is now just illustrative
# Should be saved as ~/projects/cfap/app.py

import os
import psycopg2
import psycopg2.pool
import psycopg2.extras # For dictionary cursor if preferred
from flask import Flask, request, jsonify, session, redirect, url_for, flash # Added redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import logging
from functools import wraps # For role checking decorator

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


# --- TODO: Add API endpoints for Targets, Forwarding Rules, DIDs, CDRs, Admin functions ---


# --- Internal API Routes (for Asterisk AGI) ---
# These should be secured, e.g., require specific token or only allow from localhost
@app.route('/internal_api/route_info', methods=['GET'])
def internal_route_info():
    # !! Add security check here (e.g., check request.remote_addr == '127.0.0.1' or check for a secret token) !!
    # Example basic IP check:
    # if request.remote_addr != '127.0.0.1':
    #    logger.warning(f"Unauthorized access attempt to internal_route_info from {request.remote_addr}")
    #    return jsonify({"status": "error", "reason": "forbidden"}), 403

    logger.info(f"Received internal route_info request: {request.args}")
    did_param = request.args.get('did')
    if not did_param:
        return jsonify({"status": "error", "reason": "missing_did_parameter"}), 400

    # --- !!! Placeholder - Replace with Actual Database Lookup and Logic !!! ---
    # 1. Find DID in `dids` table. Get `assigned_user_id`. Check if assigned.
    # 2. Find active Campaign(s) linked to this DID via `campaign_dids`. Check campaign status.
    # 3. Check Campaign Volume Caps (hourly/daily/total). Reset if needed. If capped -> reject.
    # 4. Find active Forwarding Rule(s) linked to the Campaign(s) via `rule_campaigns`.
    # 5. Based on Rule's `routing_strategy`, select Target(s) linked via `rule_targets`.
    # 6. Check selected Target's `total_calls_allowed` vs `current_total_calls_delivered`. If capped -> reject (or try next target).
    # 7. Check User's `balance`. If insufficient -> reject.
    # 8. Get Target's `destination_uri`, `concurrency_limit`.
    # 9. Get Rule's `min_billable_duration`.
    # 10. Get global `billing_rate_per_minute` from `system_settings`.
    # 11. Format response for AGI script (include target URI, concurrency limit, user info, etc.)

    # Example hardcoded route for testing (REMOVE THIS LATER)
    if did_param == '+15551234567':
         logger.info(f"Using hardcoded test route for DID {did_param}")
         return jsonify({
           "status": "proceed", # proceed | reject
           "reject_reason": None, # e.g., "volume_cap_hourly", "concurrency_limit", "balance_low", "no_active_route"
           "user_id": 1,
           "campaign_id": 1,
           "rule_id": 1,
           "balance_ok": True,
           "min_billable_duration": 30, # From rule
           "cost_rate_per_minute": 0.0600, # From system_settings
           # List of targets selected by the rule/strategy
           "targets": [
               {
                   "id": 1,
                   "uri": "sip:test@127.0.0.1:5080", # Target's destination_uri
                   "concurrency_limit": 2,       # Target's concurrency_limit
                   "priority": 0,                # From rule_targets (optional)
                   "weight": 100                 # From rule_targets (optional)
                   # "total_calls_remaining": 999 # Calculated if cap exists
               }
               # Add more targets if strategy is RoundRobin/Priority etc.
           ],
           "routing_strategy": "Primary" # From rule
         }), 200
    else:
        logger.warning(f"No route found for DID {did_param} (placeholder logic)")
        return jsonify({"status": "reject", "reject_reason": "no_route_found"}), 404 # Use 404 or specific status


@app.route('/internal_api/log_cdr', methods=['POST'])
def internal_log_cdr():
     # !! Add security check here !!
     # if request.remote_addr != '127.0.0.1': return jsonify({"status": "error", "reason": "forbidden"}), 403

     cdr_data = request.json
     logger.info(f"Received internal log_cdr request: {cdr_data}")
     if not cdr_data:
          return jsonify({"status": "error", "message": "No CDR data received"}), 400

     # --- !!! Placeholder - Replace with Actual Database Insert/Update Logic !!! ---
     # 1. Validate incoming cdr_data fields.
     # 2. Insert record into `call_detail_records` table.
     # 3. If call was connected & met `min_billable_duration`:
     #    a. Calculate `calculated_cost` (billable_duration * rate / 60).
     #    b. Decrement `users.balance` for the `user_id`. Use atomic update (UPDATE users SET balance = balance - %s...).
     #    c. Increment `targets.current_total_calls_delivered` for the `target_id`. Use atomic update.
     #    d. Increment `campaigns.current_total_calls`, `current_daily_calls`, `current_hourly_calls`. Use atomic updates.
     # 4. Ensure database operations are within a transaction (use execute_db helper carefully or manage conn manually).

     # Example placeholder response
     inserted_cdr_id = 12345 # Get actual ID after insert
     logger.info(f"CDR logged successfully (placeholder). ID: {inserted_cdr_id}")
     return jsonify({"status": "success", "message": "CDR logged", "cdr_id": inserted_cdr_id}), 201


# --- Main Execution ---
if __name__ == '__main__':
    # Debug will be True if FLASK_ENV=development in .env
    # Host 0.0.0.0 makes it accessible externally (within your local network)
    # Port 5000 is the Flask default
    app.run(host='0.0.0.0', port=5000, debug=True) # Ensure debug=True for development
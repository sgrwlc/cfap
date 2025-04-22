# CapConduit Call Forwarding Platform (CFAP - v3.1 Regenerated)

## Overview

CapConduit is a specialized, multi-tenant platform designed to bridge Call Sellers (lead generators) with Call Centers (Clients). It allows Sellers to manage marketing campaigns linked to specific phone numbers (DIDs) and route incoming calls to registered Call Center Clients based on defined rules, concurrency limits, and volume caps.

This version utilizes Asterisk Realtime Architecture (ARA) for dynamic PJSIP endpoint configuration sourced from the platform's PostgreSQL database. The core application is built with Flask (Python).

**Key Features:**

*   **Admin Management:** Manage Users (Admin, Staff, Seller), Clients (Call Centers), and Client PJSIP (ARA) configurations.
*   **Seller Management:** Manage own DIDs, Campaigns, link DIDs to Campaigns, link Campaigns to Clients with specific routing rules (priority, weight) and caps (concurrency, total calls).
*   **Call Logging:** Records detailed information for each call attempt processed by the system.
*   **ARA Integration:** Designed for Asterisk to read PJSIP configurations directly from the database.
*   **Internal API:** Provides endpoints for Asterisk (e.g., call logging).

## Project Structure

cfap/
├── app/ # Main Flask application package
│ ├── init.py # Application factory (create_app)
│ ├── api/ # API Blueprints and Schemas
│ │ ├── init.py
│ │ ├── routes/ # API route definitions (auth, admin, seller, internal)
│ │ │ ├── init.py
│ │ │ └── ... (admin_clients.py, seller_campaigns.py, etc.)
│ │ └── schemas/ # Marshmallow schemas for API validation/serialization
│ │ ├── init.py
│ │ └── ... (user_schemas.py, client_schemas.py, etc.)
│ ├── database/ # Database models
│ │ ├── init.py
│ │ └── models/
│ │ ├── init.py
│ │ └── ... (user.py, client.py, pjsip.py, campaign.py, etc.)
│ ├── services/ # Business logic layer
│ │ ├── init.py
│ │ └── ... (user_service.py, client_service.py, etc.)
│ ├── utils/ # Utility functions, decorators, exceptions
│ │ ├── init.py
│ │ ├── decorators.py
│ │ └── exceptions.py
│ ├── config.py # Configuration classes (Development, Testing, Production)
│ └── extensions.py # Flask extension instances (db, migrate, bcrypt, login_manager)
├── migrations/ # Database migration scripts (Alembic)
│ ├── versions/
│ └── ... (env.py, alembic.ini, etc.)
├── tests/ # Pytest integration tests
│ ├── init.py
│ ├── conftest.py # Pytest fixtures
│ └── integration/
│ └── api/
│ └── ... (test_auth_api.py, test_admin_user_api.py, etc.)
├── .env # Environment variables (DB URI, secrets) - DO NOT COMMIT ACTUAL SECRETS
├── .flaskenv # Environment variables for 'flask' CLI
├── .gitignore # Git ignore rules
├── .python-version # Target Python version (for pyenv)
├── dbcleanup.sh # Utility script to clean PostgreSQL DB
├── requirements.txt # Python package dependencies
├── sample_data.sql # SQL script to populate DB with sample data
├── run.py # Basic script to run Flask development server
├── wsgi.py # WSGI entry point for production servers (Gunicorn/uWSGI)
├── handoff.md # Project handoff/context document (if applicable)
├── masterplan.md # Project goals and design document
└── progress.md # Project progress tracking document
└── README.md # This file

## Setup and Installation

1.  **Prerequisites:**
    *   Python 3.11.6 (as specified in `.python-version`, ideally managed with `pyenv`)
    *   PostgreSQL Server (e.g., v14+) running locally or accessible.
    *   `psql` command-line tool (PostgreSQL client) available in PATH (for loading sample data via fixture).
    *   Git

2.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd cfap
    ```

3.  **Set up Python Environment:**
    *   (Recommended) Use `pyenv` to install and select the correct Python version:
        ```bash
        pyenv install 3.11.6
        pyenv local 3.11.6
        ```
    *   Create and activate a virtual environment:
        ```bash
        python -m venv venv
        source venv/bin/activate  # On Windows use `venv\Scripts\activate`
        ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Environment Variables:**
    *   Copy the `.env.template` (if provided) or the regenerated `.env` file structure to a new file named `.env` in the project root.
    *   **Edit `.env` and provide actual values for:**
        *   `SECRET_KEY`: Generate a strong secret key (e.g., `python -c 'import secrets; print(secrets.token_hex(32))'`).
        *   `DATABASE_URI`: Set the correct connection string for your PostgreSQL database (e.g., `postgresql://user:password@host:port/call_platform_db`).
        *   `TEST_DATABASE_URI`: Set the connection string for your **separate** test database (e.g., `postgresql://user:password@host:port/call_platform_test_db`).
        *   `INTERNAL_API_TOKEN`: Generate a secure random token for internal API calls.
    *   Review other settings in `.env` (like `FLASK_ENV`).

6.  **Setup PostgreSQL Database:**
    *   Ensure your PostgreSQL server is running.
    *   Create the main application database and the test database specified in your `.env` file.
    *   Create the database user and grant necessary privileges on both databases.
        ```sql
        -- Example SQL commands (run as PostgreSQL superuser like 'postgres')
        CREATE USER call_platform_user WITH PASSWORD 'YourSecurePassword';
        CREATE DATABASE call_platform_db OWNER call_platform_user;
        CREATE DATABASE call_platform_test_db OWNER call_platform_user;
        GRANT ALL PRIVILEGES ON DATABASE call_platform_db TO call_platform_user;
        GRANT ALL PRIVILEGES ON DATABASE call_platform_test_db TO call_platform_user;
        ```
        *Replace `YourSecurePassword` and ensure it matches the (URL-encoded) password in your `.env` URIs.*

7.  **Apply Database Migrations:**
    *   Ensure your virtual environment is activated and you are in the project root (`cfap/`).
    *   Run the following Flask-Migrate command:
        ```bash
        flask db upgrade
        ```
        This will apply the migrations found in the `migrations/versions` directory to the database specified by `DATABASE_URI` in your `.env` file.

8.  **Load Sample Data (Optional, Recommended for Dev/Test):**
    *   Ensure the `psql` command is available and configured correctly to connect to your database (it uses the URI).
    *   Run the sample data script against your main database:
        ```bash
        psql $DATABASE_URI -f sample_data.sql
        # Or if DATABASE_URI env var isn't exported, provide it directly:
        # psql postgresql://user:password@host:port/call_platform_db -f sample_data.sql
        ```
    *   *(Note: The test suite automatically loads sample data into the test database via the `db` fixture in `conftest.py`)*

## Running the Application

1.  **Development Server:**
    *   Ensure your virtual environment is activated.
    *   Make sure `FLASK_ENV=development` is set in `.env` or `.flaskenv`.
    *   Run the Flask development server:
        ```bash
        flask run
        ```
        The application should be accessible at `http://127.0.0.1:5000` (or the host/port specified in your environment).

2.  **Production Server (Example with Gunicorn):**
    *   Ensure `FLASK_ENV=production` is set in your production environment's `.env` file or system environment variables.
    *   Install Gunicorn (already in `requirements.txt`).
    *   Run Gunicorn, pointing it to the `wsgi:application` entry point:
        ```bash
        gunicorn --bind 0.0.0.0:5000 wsgi:application
        ```
        Adjust the bind address/port and add other Gunicorn options (like `--workers`, `--log-file`) as needed for your production setup, typically behind a reverse proxy like Nginx.

## Running Tests

1.  **Prerequisites:**
    *   Ensure the **test database** specified in `TEST_DATABASE_URI` exists and the user has privileges.
    *   The test runner will automatically create tables, load `sample_data.sql`, and drop tables in the test database.

2.  **Execute Tests:**
    *   Ensure your virtual environment is activated.
    *   Run Pytest from the project root (`cfap/`):
        ```bash
        pytest
        ```
        Or with more verbosity:
        ```bash
        pytest -v
        ```

## Next Steps (Asterisk Integration)

This codebase provides the backend API and database structure. The next major phase involves configuring an Asterisk instance:

1.  **ARA Setup:** Configure `extconfig.conf`, `res_config_pgsql.so`, `res_pjsip.conf`, `sorcery.conf` in Asterisk to read PJSIP configurations from the `pjsip_*` tables in the application database.
2.  **Dialplan (`extensions.conf`):** Develop dialplan logic to:
    *   Receive incoming calls.
    *   Look up DID -> Campaign -> Eligible Clients (querying DB or potentially a simplified API).
    *   Check concurrency and total call caps.
    *   Select target client based on routing strategy.
    *   Execute `Dial(PJSIP/{client_identifier},...)`.
    *   Handle dial statuses (ANSWER, BUSY, NOANSWER, etc.).
3.  **AGI Script (`cdr_logger.agi`):** Develop a script (e.g., in Python) called from the dialplan's `h` extension to:
    *   Collect call details (UniqueID, CallerID, Timestamps, Status, Dialed Client Setting ID, etc.).
    *   Send a POST request to the application's `/api/internal/log_call` endpoint with the details and the `INTERNAL_API_TOKEN`.


# run.py
import os
# from dotenv import load_dotenv # REMOVED - Handled by config.py/create_app

# Load .env before importing app factory # REMOVED
# dotenv_path = os.path.join(os.path.dirname(__file__), '.env') # REMOVED
# if os.path.exists(dotenv_path): # REMOVED
#     load_dotenv(dotenv_path) # REMOVED

from app import create_app

# Use the app factory to create the app instance
# It will load configuration based on FLASK_ENV (from .env or .flaskenv) via config.py
app = create_app() # create_app internally loads config which loads .env

if __name__ == '__main__':
    # Get host and port from environment variables or use defaults
    # Note: Flask's built-in server is for development only. Use Gunicorn/uWSGI in production.
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))

    # Debug mode is controlled by FLASK_ENV=development or FLASK_DEBUG=1 in environment/config
    # app.run() respects these variables.
    # Add any additional run options here if needed, e.g., ssl_context
    app.run(host=host, port=port)
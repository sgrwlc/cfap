# wsgi.py
import os
# from dotenv import load_dotenv # REMOVED - Handled by config.py/create_app

# Load environment variables from .env file first # REMOVED
# dotenv_path = os.path.join(os.path.dirname(__file__), '.env') # REMOVED
# if os.path.exists(dotenv_path): # REMOVED
#     load_dotenv(dotenv_path) # REMOVED

from app import create_app

# Create the Flask app instance using the factory for the WSGI server (e.g., Gunicorn)
# create_app() loads the appropriate config (which loads .env) based on FLASK_ENV
application = create_app()

# The 'application' variable is the entry point for WSGI servers like Gunicorn.
# Example Gunicorn command: gunicorn --bind 0.0.0.0:5000 wsgi:application

if __name__ == "__main__":
    # This block is typically not executed by a WSGI server.
    # It might be useful for some specific debugging scenarios.
    print("WSGI entry point. To run the application, use a WSGI server like Gunicorn:")
    print("Example: gunicorn wsgi:application")
    # Avoid running the dev server from here in production contexts.
    # application.run(host='0.0.0.0') # Example if running directly (NOT recommended for prod)
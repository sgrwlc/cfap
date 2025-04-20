import os
from dotenv import load_dotenv

# Load environment variables from .env file first
# This ensures DATABASE_URI etc. are available when the app is created
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

from app import create_app

# Create the Flask app instance using the factory
# Pass the environment name explicitly if needed, otherwise it defaults based on FLASK_ENV
# config_name = os.getenv('FLASK_ENV', 'production')
# application = create_app(config_name=config_name)
application = create_app() # create_app should handle loading config based on FLASK_ENV

if __name__ == "__main__":
    # This part is typically not run by Gunicorn/uWSGI but can be useful
    # for certain deployment scenarios or direct execution checks.
    # Gunicorn runs the 'application' callable defined above.
    print("WSGI entry point. Run with a WSGI server like Gunicorn: gunicorn wsgi:application")
    # Example: application.run() # Not recommended for production via wsgi.py
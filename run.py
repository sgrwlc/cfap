import os
from dotenv import load_dotenv

# Load .env before importing app factory
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

from app import create_app

# Use the app factory to create the app instance
# It will load configuration based on FLASK_ENV (from .env or .flaskenv)
app = create_app()

if __name__ == '__main__':
    # Get host and port from environment variables or use defaults
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    # Debug mode is typically controlled by FLASK_ENV=development or FLASK_DEBUG=1
    # app.run() will respect these environment variables
    app.run(host=host, port=port)
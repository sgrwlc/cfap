# app/__init__.py
# -*- coding: utf-8 -*-
"""Main application package setup."""

import os
import logging
from flask import Flask, jsonify, abort, request
from dotenv import load_dotenv

# Import configurations and extensions
from .config import config # Import config dictionary
from .extensions import db, migrate, bcrypt, login_manager

# Import custom exceptions (optional, if handled globally)
# from .utils.exceptions import ServiceError


def create_app(config_name=None):
    """
    Create and configure an instance of the Flask application using the App Factory pattern.

    Args:
        config_name (str, optional): The name of the configuration to use ('development', 'testing', 'production').
                                     Defaults to FLASK_ENV environment variable or 'default'.

    Returns:
        Flask: The configured Flask application instance.
    """

    # Determine configuration name
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')
        # Ensure default maps to a valid config key
        if config_name not in config:
             print(f"WARNING: Invalid FLASK_ENV '{config_name}', defaulting to 'development'.")
             config_name = 'development'

    # Load .env file from project root (basedir determined relative to this file)
    # basedir = os.path.abspath(os.path.dirname(__file__))
    # dotenv_path = os.path.join(basedir, '..', '.env') # Assumes __init__.py is in app/
    # Redundant if run.py/wsgi.py already load it, but harmless.
    # load_dotenv(dotenv_path)

    app = Flask(__name__)

    # Load configuration from config object
    try:
        app.config.from_object(config[config_name])
        config[config_name].init_app(app) # Allow config to perform extra init steps
        print(f"INFO: App created with configuration: '{config_name}'")
    except KeyError:
         print(f"ERROR: Configuration '{config_name}' not found. Check config.py.")
         # Optionally raise an error or exit
         raise ValueError(f"Invalid configuration name: {config_name}")

    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # Configure logging level (Moved from config.py init_app for clarity)
    log_level_name = app.config.get('LOG_LEVEL', 'INFO' if not app.debug else 'DEBUG').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    app.logger.setLevel(log_level)
    # Ensure handlers respect the level too (applies to default StreamHandler)
    for handler in app.logger.handlers:
         handler.setLevel(log_level)
    app.logger.info(f"Flask logger initialized with level: {log_level_name}")


    # --- Register Blueprints ---
    # Authentication
    from .api.routes.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')

    # Internal APIs (Asterisk)
    from .api.routes.internal_routing import internal_routing_bp
    app.register_blueprint(internal_routing_bp, url_prefix='/api/internal')
    from .api.routes.internal_logging import internal_logging_bp
    app.register_blueprint(internal_logging_bp, url_prefix='/api/internal') # Shares prefix

    # Admin APIs
    from .api.routes.admin_users import admin_users_bp
    app.register_blueprint(admin_users_bp, url_prefix='/api/admin/users')
    from .api.routes.admin_clients import admin_clients_bp
    app.register_blueprint(admin_clients_bp, url_prefix='/api/admin/clients')

    # Seller APIs
    from .api.routes.seller_dids import seller_dids_bp
    app.register_blueprint(seller_dids_bp, url_prefix='/api/seller/dids')
    from .api.routes.seller_campaigns import seller_campaigns_bp
    app.register_blueprint(seller_campaigns_bp, url_prefix='/api/seller/campaigns')
    from .api.routes.seller_logs import seller_logs_bp
    app.register_blueprint(seller_logs_bp, url_prefix='/api/seller/logs')

    # --- Basic Routes & Health Check ---
    @app.route('/health')
    def health_check():
        # Basic health check endpoint
        return {"status": "ok", "message": "Application is running."}, 200

    # --- Configure Flask-Login ---
    # The user_loader callback is defined in extensions.py
    @login_manager.unauthorized_handler
    def unauthorized():
        """Handles unauthorized access attempts for @login_required routes."""
        app.logger.debug("Unauthorized access attempt caught by login_manager.")
        # Use abort to trigger the standard 401 error handler below
        abort(401, description="Authentication required to access this resource.")

    # --- Global HTTP Error Handlers ---
    # These handlers catch errors raised by abort() or unhandled HTTP exceptions.
    # They ensure consistent JSON error responses.

    @app.errorhandler(400)
    def bad_request_error(error):
        app.logger.warning(f"Bad Request (400): {error.description}")
        return jsonify(message=error.description or "Bad request."), 400

    @app.errorhandler(401)
    def unauthorized_error(error):
        app.logger.warning(f"Unauthorized (401): {error.description}")
        return jsonify(message=error.description or "Unauthorized."), 401

    @app.errorhandler(403)
    def forbidden_error(error):
        app.logger.warning(f"Forbidden (403): {error.description}")
        return jsonify(message=error.description or "Forbidden."), 403

    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.info(f"Not Found (404): {error.description} (Path: {request.path})")
        return jsonify(message=error.description or "Resource not found."), 404

    @app.errorhandler(409)
    def conflict_error(error):
        app.logger.warning(f"Conflict (409): {error.description}")
        return jsonify(message=error.description or "Conflict."), 409

    @app.errorhandler(500)
    def internal_error(error):
        # Log the original exception if available (Flask often attaches it)
        original_exception = getattr(error, "original_exception", error)
        app.logger.error(f"Internal Server Error (500): {error.description}", exc_info=original_exception)
        # Ensure DB session is rolled back in case of unexpected 500 errors during a request
        try:
            db.session.rollback()
            app.logger.info("Rolled back database session due to 500 error.")
        except Exception as rb_err:
             app.logger.error(f"Error during automatic rollback after 500 error: {rb_err}", exc_info=True)
        return jsonify(message=error.description or "Internal server error."), 500

    # Optional: Handler for custom base ServiceError if needed, but abort() is preferred
    # @app.errorhandler(ServiceError)
    # def handle_service_error(error):
    #     app.logger.error(f"Service Error ({error.status_code}): {error}", exc_info=True)
    #     db.session.rollback() # Ensure rollback on service errors
    #     return jsonify(error.to_dict()), error.status_code


    # --- Shell Context Processor ---
    # Makes variables available in 'flask shell'
    @app.shell_context_processor
    def make_shell_context():
        from .database import models # Import models package
        from . import services # Import services package
        # Expose db, models package, and services package
        return {'db': db, 'models': models, 'services': services}

    return app
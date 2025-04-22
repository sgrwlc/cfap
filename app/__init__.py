# -*- coding: utf-8 -*-
"""Main application package."""

import os
from flask import Flask, jsonify
from dotenv import load_dotenv
import logging
from .config import config
from .extensions import db, migrate, bcrypt, login_manager

# Import Marshmallow for potential global error handling (optional)
# from marshmallow import ValidationError

def create_app(config_name=None):
    """Create and configure an instance of the Flask application."""

    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')

    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # --- Add Log Level Configuration ---
    if app.config.get('LOG_LEVEL'):
         app.logger.setLevel(app.config['LOG_LEVEL'])
    elif app.debug:
         app.logger.setLevel(logging.DEBUG)
    else:
         app.logger.setLevel(logging.INFO)
    # --- End Log Level Configuration ---
    
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # --- Register Blueprints ---
    from .api.routes.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')

    from .api.routes.internal_routing import internal_routing_bp
    app.register_blueprint(internal_routing_bp, url_prefix='/api/internal')

    from .api.routes.internal_logging import internal_logging_bp
    app.register_blueprint(internal_logging_bp, url_prefix='/api/internal')

    # Admin Blueprints
    from .api.routes.admin_users import admin_users_bp
    app.register_blueprint(admin_users_bp, url_prefix='/api/admin/users')

    from .api.routes.admin_clients import admin_clients_bp
    app.register_blueprint(admin_clients_bp, url_prefix='/api/admin/clients')

    # Seller Blueprints
    from .api.routes.seller_dids import seller_dids_bp
    app.register_blueprint(seller_dids_bp, url_prefix='/api/seller/dids')

    from .api.routes.seller_campaigns import seller_campaigns_bp
    app.register_blueprint(seller_campaigns_bp, url_prefix='/api/seller/campaigns')

    from .api.routes.seller_logs import seller_logs_bp
    app.register_blueprint(seller_logs_bp, url_prefix='/api/seller/logs')

    # ... register other blueprints as they are created ...


    # Optional: Add a simple root route for health check or basic info
    @app.route('/health')
    def health_check():
        return {"status": "ok"}, 200

    # --- Configure Flask-Login unauthorized handler ---
    @login_manager.unauthorized_handler
    def unauthorized():
        app.logger.debug("Unauthorized access attempt intercepted by login_manager.")
        return jsonify(message="Authentication required to access this resource."), 401


    # --- Optional: Global Error Handlers ---
    # Example: Handle Marshmallow validation errors globally
    # @app.errorhandler(ValidationError)
    # def handle_marshmallow_validation(err):
    #     return jsonify(err.messages), 400

    @app.errorhandler(400)
    def bad_request_error(error):
        return jsonify(message=error.description or "Bad request."), 400

    @app.errorhandler(401)
    def unauthorized_error(error):
         return jsonify(message=error.description or "Unauthorized."), 401

    @app.errorhandler(403)
    def forbidden_error(error):
        return jsonify(message=error.description or "Forbidden."), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify(message=error.description or "Resource not found."), 404

    @app.errorhandler(409)
    def conflict_error(error):
        return jsonify(message=error.description or "Conflict."), 409

    @app.errorhandler(500)
    def internal_error(error):
        # Log the original exception if possible
        # db.session.rollback() # Rollback DB session in case of 500 error during request
        app.logger.error(f"Internal Server Error: {error.description or error}")
        return jsonify(message=error.description or "Internal server error."), 500


    # Shell context for flask shell
    @app.shell_context_processor
    def make_shell_context():
        from .database import models
        from . import services # Import services package
        return {'db': db, 'models': models, 'services': services}

    return app
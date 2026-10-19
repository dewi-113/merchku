def register_blueprints(app):
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp)

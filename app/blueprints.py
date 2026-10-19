def register_blueprints(app):
    from app.admin.routes import bp as admin_bp
    from app.auth.routes import bp as auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

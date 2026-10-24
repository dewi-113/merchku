def register_blueprints(app):
    from app.admin.routes import bp as admin_bp
    from app.auth.routes import bp as auth_bp
    from app.chat.routes import bp as chat_bp
    from app.cs.routes import bp as cs_bp
    from app.katalog.routes import bp as katalog_bp
    from app.keranjang.routes import bp as keranjang_bp
    from app.pesanan.routes import bp as pesanan_bp
    from app.profil.routes import bp as profil_bp
    from app.seller.routes import bp as seller_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(seller_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(cs_bp)
    app.register_blueprint(katalog_bp)
    app.register_blueprint(keranjang_bp)
    app.register_blueprint(pesanan_bp)
    app.register_blueprint(profil_bp)

import click
from flask.cli import with_appcontext

from app import db
from app.auth.models import User
from app.auth.security import hash_password


@click.command('create-admin')
@click.option('--email', default='admin@merchku.local')
@click.option('--password', default='admin12345678') # min 10
@with_appcontext
def create_admin(email, password):
    if len(password) < 10:
        raise click.BadParameter('password min 10')
    u = User.query.filter_by(email=email.lower()).first()
    if u:
        u.password_hash = hash_password(password)
        u.role = 'admin'
        u.is_active = True
        db.session.commit()
        click.echo('updated admin')
        return
    u = User(email=email.lower(), password_hash=hash_password(password), role='admin', is_active=True)
    db.session.add(u)
    db.session.commit()
    click.echo('admin created')

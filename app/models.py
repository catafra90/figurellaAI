from datetime import datetime
from app import db

class Client(db.Model):
    __tablename__ = 'clients'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(128), nullable=False)
    email      = db.Column(db.String(256))
    phone      = db.Column(db.String(50))
    status     = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Client {self.name}>'

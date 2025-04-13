from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///learning.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    interests = db.Column(db.String(200))
    difficulty_preference = db.Column(db.String(20), default='any')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

# UserProgress Model
class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    video_id = db.Column(db.String(100))
    video_title = db.Column(db.String(200))
    video_length = db.Column(db.Integer)
    difficulty_level = db.Column(db.String(50))
    completion_status = db.Column(db.Boolean, default=False)
    watch_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    rating = db.Column(db.Integer)

# UserData Model
class UserData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    subject = db.Column(db.String(100))
    score = db.Column(db.Integer)
    topic = db.Column(db.String(200))

if __name__ == '__main__':
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Database tables created successfully!") 
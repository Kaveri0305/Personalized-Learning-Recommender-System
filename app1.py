from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import pickle
import numpy as np
import isodate
from datetime import datetime, timedelta

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///learning.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # Session expires after 30 minutes
app.config['SESSION_PROTECTION'] = 'strong'  # Provides better session security

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    interests = db.Column(db.String(200))
    difficulty_preference = db.Column(db.String(20), default='any')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Define a database model for user data
class UserData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    subject = db.Column(db.String(100))
    score = db.Column(db.Integer)
    topic = db.Column(db.String(200))

# Add after the UserData model
class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    video_id = db.Column(db.String(100))
    video_title = db.Column(db.String(200))
    video_length = db.Column(db.Integer)  # in seconds
    difficulty_level = db.Column(db.String(50))
    completion_status = db.Column(db.Boolean, default=False)
    watch_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    rating = db.Column(db.Integer)  # 1-5 rating

# Load the ML model if available (for predicting proficiency level)
try:
    with open('ml_model.pkl', 'rb') as f:
        ml_model = pickle.load(f)
except Exception as e:
    ml_model = None
    print("ML model not loaded:", e)

# Dummy function to encode subject into a numeric value (customize as needed)
def encode_subject(subject):
    # For example: "Math" -> 0, "English" -> 1
    return 0 if subject.lower() == 'math' else 1

# Replace with your actual YouTube Data API key
YOUTUBE_API_KEY = "AIzaSyByL4KmcoiNmpAiwCftX6YrJ9dB3oacfyY"

# --- Routes ---

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return redirect(url_for('study_form'))

@app.route('/study_form', methods=['GET', 'POST'])
@login_required
def study_form():
    if request.method == 'POST':
        score = request.form.get('score')
        subject = request.form.get('subject')
        
        # Save the data in the database
        user_data = UserData(
            username=current_user.username,
            score=int(score),
            subject=subject,
            topic=''
        )
        db.session.add(user_data)
        db.session.commit()
        
        return redirect(url_for('topic', score=score, subject=subject))
    
    return render_template('study_form.html')

@app.route('/topic', methods=['GET', 'POST'])
@login_required
def topic():
    """
    Page 2: Ask the user for a specific topic they want to work on.
    """
    # Retrieve query parameters
    score = request.args.get('score')
    subject = request.args.get('subject')
    
    if request.method == 'POST':
        user_topic = request.form.get('topic')
        # Update the latest user record with the topic (simple example)
        user_data = UserData.query.filter_by(
            username=current_user.username,
            subject=subject
        ).order_by(UserData.id.desc()).first()
        if user_data:
            user_data.topic = user_topic
            db.session.commit()
        
        # Redirect to the recommendations page with all the user data
        return redirect(url_for('recommendations', score=score, subject=subject, topic=user_topic))
    
    return render_template('topic.html', score=score, subject=subject)


@app.route('/recommendations')
@login_required
def recommendations():
    try:
        score = request.args.get('score')
        subject = request.args.get('subject')
        topic = request.args.get('topic')
        
        # Get filter parameters
        video_length = request.args.get('video_length', 'any')
        difficulty = request.args.get('difficulty', 'any')
        
        # Build YouTube search query
        search_query = f"{subject} {topic} tutorial"
        
        # YouTube API request
        search_url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": search_query,
            "type": "video",
            "maxResults": 20,
            "key": YOUTUBE_API_KEY
        }
        
        response = requests.get(search_url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"YouTube API error: {response.json()}")
            raise Exception("Failed to fetch videos")
            
        data = response.json()
        
        # Process videos
        videos = []
        for item in data.get("items", []):
            try:
                video_id = item["id"]["videoId"]
                video_details = get_video_details(video_id)
                
                duration = video_details.get("duration", 0)
                view_count = int(video_details.get("viewCount", 0))
                like_count = int(video_details.get("likeCount", 0))
                
                # Apply length filter
                if video_length != 'any':
                    if video_length == 'short' and duration > 600:
                        continue
                    elif video_length == 'medium' and (duration < 600 or duration > 1800):
                        continue
                    elif video_length == 'long' and duration < 1800:
                        continue
                
                # Determine video difficulty
                video_difficulty = 'basic'
                if view_count > 50000:
                    video_difficulty = 'intermediate'
                if view_count > 200000:
                    video_difficulty = 'advanced'
                
                # Apply difficulty filter
                if difficulty != 'any' and difficulty != video_difficulty:
                    continue
                
                videos.append({
                    'id': video_id,
                    'title': item["snippet"]["title"],
                    'description': item["snippet"]["description"],
                    'thumbnail': item["snippet"]["thumbnails"]["medium"]["url"],
                    'duration': duration,
                    'duration_text': format_duration(duration),
                    'views': view_count,
                    'likes': like_count,
                    'difficulty': video_difficulty,
                    'url': f"https://www.youtube.com/watch?v={video_id}"
                })
                
            except Exception as e:
                print(f"Error processing video {video_id}: {str(e)}")
                continue
        
        if not videos:
            return render_template(
                'recommendations.html',
                username=current_user.username,
                subject=subject,
                score=score,
                topic=topic,
                videos=[],
                current_filters={
                    'video_length': video_length,
                    'difficulty': difficulty
                },
                message="No videos found with current filters. Try different filter options."
            )
        
        return render_template(
            'recommendations.html',
            username=current_user.username,
            subject=subject,
            score=score,
            topic=topic,
            videos=videos,
            current_filters={
                'video_length': video_length,
                'difficulty': difficulty
            }
        )
        
    except Exception as e:
        print(f"Error in recommendations: {str(e)}")
        return render_template(
            'error.html',
            error_message="We're having trouble getting video recommendations. Here are some alternative resources:",
            subject=subject if 'subject' in locals() else 'general',
            topic=topic if 'topic' in locals() else 'learning',
            alternative_resources=[
                {
                    'title': f'{subject if "subject" in locals() else "General"} - {topic if "topic" in locals() else "Learning"} on Khan Academy',
                    'url': f'https://www.khanacademy.org/search?page_search_query={subject if "subject" in locals() else ""}+{topic if "topic" in locals() else ""}'
                },
                {
                    'title': f'{subject if "subject" in locals() else "General"} - {topic if "topic" in locals() else "Learning"} on MIT OpenCourseWare',
                    'url': f'https://ocw.mit.edu/search/?q={subject if "subject" in locals() else ""}+{topic if "topic" in locals() else ""}'
                }
            ]
        )

def format_duration(seconds):
    """Convert seconds to readable duration"""
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    if minutes < 60:
        return f"{minutes}:{remaining_seconds:02d}"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}:{remaining_minutes:02d}:{remaining_seconds:02d}"

def get_video_details(video_id):
    """Helper function to get video details using YouTube API"""
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "contentDetails,statistics",
            "id": video_id,
            "key": "AIzaSyByL4KmcoiNmpAiwCftX6YrJ9dB3oacfyY"
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if "items" in data and len(data["items"]) > 0:
            item = data["items"][0]
            try:
                duration = parse_duration(item["contentDetails"]["duration"])
            except:
                duration = 0
                
            return {
                "duration": duration,
                "viewCount": item["statistics"].get("viewCount", "0"),
                "likeCount": item["statistics"].get("likeCount", "0")
            }
    except Exception as e:
        print(f"Error in get_video_details: {str(e)}")
    
    return {
        "duration": 0,
        "viewCount": "0",
        "likeCount": "0"
    }

def parse_duration(duration_str):
    """Convert YouTube duration format (PT1H2M10S) to seconds"""
    import re
    import isodate
    return int(isodate.parse_duration(duration_str).total_seconds())

@app.route('/dashboard/<username>')
@login_required
def dashboard(username):
    if username != current_user.username:
        flash('You can only view your own dashboard', 'error')
        return redirect(url_for('dashboard', username=current_user.username))
    # Get user's learning history
    user_history = UserProgress.query.filter_by(username=username).order_by(UserProgress.watch_date.desc()).all()
    
    # Calculate statistics
    total_videos = len(user_history)
    completed_videos = len([v for v in user_history if v.completion_status])
    completion_rate = (completed_videos / total_videos * 100) if total_videos > 0 else 0
    
    # Get video completion by difficulty level
    difficulty_stats = {}
    for level in ['basic', 'intermediate', 'advanced']:
        count = UserProgress.query.filter_by(
            username=username,
            difficulty_level=level
        ).count()
        if count > 0:
            difficulty_stats[level] = count
    
    # Get dates for progress chart (last 7 days)
    dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    
    # Get progress data
    progress_data = []
    for date in dates:
        count = UserProgress.query.filter(
            UserProgress.username == username,
            db.func.date(UserProgress.watch_date) == date
        ).count()
        progress_data.append(count)
    
    return render_template(
        'dashboard.html',
        username=username,
        user_history=user_history,
        stats={
            'total_videos': total_videos,
            'completed_videos': completed_videos,
            'completion_rate': completion_rate,
            'difficulty_stats': difficulty_stats
        },
        dates=dates,
        progress_data=progress_data
    )

@app.route('/track_video', methods=['POST'])
def track_video():
    if request.method == 'POST':
        video_id = request.form.get('video_id')
        username = request.form.get('username')
        video_title = request.form.get('video_title')
        video_length = int(request.form.get('video_length'))
        difficulty_level = request.form.get('difficulty_level')
        completion_status = request.form.get('completion_status') == 'true'
        rating = int(request.form.get('rating', 0))
        
        # Create or update progress
        progress = UserProgress.query.filter_by(
            username=username,
            video_id=video_id
        ).first()
        
        if progress:
            progress.completion_status = completion_status
            progress.rating = rating
        else:
            progress = UserProgress(
                username=username,
                video_id=video_id,
                video_title=video_title,
                video_length=video_length,
                difficulty_level=difficulty_level,
                completion_status=completion_status,
                rating=rating
            )
            db.session.add(progress)
        
        db.session.commit()
        return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('study_form'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('study_form'))
        else:
            flash('Invalid username or password', 'error')
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('study_form'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('signup'))
            
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('study_form'))
        
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Get user progress statistics
    user_progress = {
        'total_videos': UserProgress.query.filter_by(username=current_user.username).count(),
        'completed_videos': UserProgress.query.filter_by(
            username=current_user.username,
            completion_status=True
        ).count(),
        'favorite_subject': None
    }
    
    # Calculate completion rate
    if user_progress['total_videos'] > 0:
        user_progress['completion_rate'] = (user_progress['completed_videos'] / user_progress['total_videos']) * 100
    else:
        user_progress['completion_rate'] = 0

    # Find favorite subject based on most watched videos
    subject_counts = db.session.query(
        UserData.subject,
        db.func.count(UserData.subject).label('count')
    ).filter_by(
        username=current_user.username
    ).group_by(UserData.subject).order_by(db.desc('count')).first()

    if subject_counts:
        user_progress['favorite_subject'] = subject_counts[0]

    if request.method == 'POST':
        # Update user profile
        current_user.interests = request.form.get('interests')
        current_user.difficulty_preference = request.form.get('difficulty_preference')
        
        # Update password if provided
        new_password = request.form.get('new_password')
        if new_password:
            current_user.set_password(new_password)
            
        db.session.commit()
        flash('Profile updated successfully', 'success')
        
    return render_template('profile.html', user=current_user, user_progress=user_progress)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

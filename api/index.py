from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session as flask_session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import os
import secrets
import string
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Create Flask app with explicit template and static paths
app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
            static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'arndale-academy-secret-key-2024')

# Neon PostgreSQL Configuration - FIXED for Vercel
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///voting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True
}

# Remove file upload configurations for Vercel (serverless doesn't support file writes)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Cloudinary Configuration
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

db = SQLAlchemy(app)

# Hardcoded admin credentials
ADMIN_CREDENTIALS = {
    'username': 'election-admin',
    'password': 'arndale2025'
}

# Database Models (Updated for PostgreSQL)
class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    academic_year = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    created_date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    description = db.Column(db.Text)
    
    positions = db.relationship('Position', backref='session', lazy=True, cascade='all, delete-orphan')

class Position(db.Model):
    __tablename__ = 'positions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    grade_filter = db.Column(db.String(50), nullable=True)  # e.g., "YEAR 7", "YEAR 8", or null for all grades
    
    candidates = db.relationship('Candidate', backref='position', lazy=True, cascade='all, delete-orphan')

class Candidate(db.Model):
    __tablename__ = 'candidates'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id', ondelete='CASCADE'), nullable=False)
    photo_url = db.Column(db.String(500))
    grade = db.Column(db.String(50))
    manifesto = db.Column(db.Text)
    votes = db.Column(db.Integer, default=0)

class Voter(db.Model):
    __tablename__ = 'voters'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    photo_url = db.Column(db.String(500))
    voter_code = db.Column(db.String(10), unique=True, nullable=False)
    registered_date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    has_voted = db.Column(db.Boolean, default=False)
    
    @staticmethod
    def generate_voter_code():
        """Generate a unique 6-digit voter code"""
        while True:
            code = ''.join(secrets.choice(string.digits) for _ in range(6))
            if not Voter.query.filter_by(voter_code=code).first():
                return code

    @staticmethod
    def generate_student_id():
        """Generate a unique student ID in format: AA-STU-YYYY-XXXX"""
        current_year = datetime.now().year
        
        # Get the highest student ID number for this year
        last_voter = Voter.query.filter(
            Voter.student_id.like(f"AA-STU-{current_year}-%")
        ).order_by(Voter.student_id.desc()).first()
        
        if last_voter:
            # Extract the number part and increment
            last_id = last_voter.student_id
            last_number = int(last_id.split('-')[-1])
            new_number = last_number + 1
        else:
            # First student of the year
            new_number = 1
        
        # Format: AA-STU-YYYY-XXXX (4-digit number)
        student_id = f"AA-STU-{current_year}-{new_number:04d}"
        return student_id

class VotingLog(db.Model):
    __tablename__ = 'voting_log'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id', ondelete='CASCADE'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey('voters.id', ondelete='CASCADE'), nullable=False)
    vote_timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    session = db.relationship('Session')
    position = db.relationship('Position')
    candidate = db.relationship('Candidate')
    voter = db.relationship('Voter')

# Initialize database - ONLY when needed
def init_database():
    """Initialize database tables - call this from routes, not on import"""
    try:
        # This will create tables if they don't exist
        db.create_all()
        print("SUCCESS: Database tables created/verified successfully")
        return True
    except Exception as e:
        print(f"ERROR: Database initialization failed: {e}")
        return False

# Cloudinary Helper Functions
def upload_to_cloudinary(file, folder):
    """Upload file to Cloudinary and return URL"""
    try:
        result = cloudinary.uploader.upload(
            file,
            folder=f"arndale-voting/{folder}",
            resource_type="image"
        )
        return result['secure_url']
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def delete_from_cloudinary(url):
    """Delete image from Cloudinary"""
    try:
        # Extract public_id from URL
        if 'arndale-voting/' in url:
            public_id = url.split('/')[-1].split('.')[0]
            full_public_id = f"arndale-voting/{public_id}"
            cloudinary.uploader.destroy(full_public_id)
    except Exception as e:
        print(f"Cloudinary delete error: {e}")

# Helper functions
def get_active_session():
    return Session.query.filter_by(is_active=True).first()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

def get_voter_stats():
    total_voters = Voter.query.count()
    voted_count = Voter.query.filter_by(has_voted=True).count()
    not_voted_count = total_voters - voted_count
    participation_rate = (voted_count / total_voters * 100) if total_voters > 0 else 0
    
    return {
        'total': total_voters,
        'voted': voted_count,
        'not_voted': not_voted_count,
        'participation_rate': round(participation_rate, 1)
    }

# Routes
# Admin Login Routes
@app.route('/', methods=['GET', 'POST'])
def admin_login():
    # If already logged in, redirect to admin dashboard
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        # Check credentials
        if (username.lower() == ADMIN_CREDENTIALS['username'] and 
            password.lower() == ADMIN_CREDENTIALS['password']):
            
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')
            
@app.route('/home')
def index():
    init_database()  # Initialize only when route is called
    active_session = get_active_session()
    sessions = Session.query.order_by(Session.created_date.desc()).all()
    voters = Voter.query.order_by(Voter.registered_date.desc()).all()
    voter_stats = get_voter_stats()
    
    return render_template('index.html', 
                         active_session=active_session,
                         sessions=sessions,
                         voters=voters,
                         voter_stats=voter_stats)

# Session Management API
@app.route('/api/sessions', methods=['GET', 'POST'])
def handle_sessions():
    if request.method == 'POST':
        data = request.get_json()
        session_name = data.get('name', '').strip()
        academic_year = data.get('academic_year', '').strip()
        description = data.get('description', '').strip()
        
        if not session_name or not academic_year:
            return jsonify({'error': 'Session name and academic year are required'}), 400
        
        # Check if session already exists
        existing_session = Session.query.filter_by(name=session_name).first()
        if existing_session:
            return jsonify({'error': 'A session with this name already exists'}), 400
        
        try:
            new_session = Session(
                name=session_name,
                academic_year=academic_year,
                description=description,
                created_date=datetime.now(timezone.utc)
            )
            db.session.add(new_session)
            db.session.commit()
            
            # If this is the first session, make it active
            if Session.query.count() == 1:
                new_session.is_active = True
                db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Session "{session_name}" created successfully',
                'session': {
                    'id': new_session.id,
                    'name': new_session.name,
                    'academic_year': new_session.academic_year,
                    'is_active': new_session.is_active
                }
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Failed to create session: {str(e)}'}), 500
    
    else:  # GET request
        sessions = Session.query.order_by(Session.created_date.desc()).all()
        sessions_data = []
        for session in sessions:
            sessions_data.append({
                'id': session.id,
                'name': session.name,
                'academic_year': session.academic_year,
                'is_active': session.is_active,
                'created_date': session.created_date.strftime('%Y-%m-%d %H:%M'),
                'description': session.description
            })
        return jsonify({'sessions': sessions_data})

@app.route('/api/sessions/<int:session_id>/activate', methods=['POST'])
def activate_session(session_id):
    session_to_activate = Session.query.get_or_404(session_id)
    
    try:
        # Deactivate all sessions
        Session.query.update({'is_active': False})
        
        # Activate the selected session
        session_to_activate.is_active = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Session "{session_to_activate.name}" activated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to activate session: {str(e)}'}), 500

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    session_to_delete = Session.query.get_or_404(session_id)
    session_name = session_to_delete.name
    
    try:
        db.session.delete(session_to_delete)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Session "{session_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete session: {str(e)}'}), 500

# Position Management API
@app.route('/api/positions', methods=['POST'])
def create_position():
    data = request.get_json()
    name = data.get('name', '').strip()
    session_id = data.get('session_id')
    display_order = data.get('display_order', 0)
    description = data.get('description', '').strip()
    grade_filter = data.get('grade_filter', '').strip() or None  # New field
    
    if not name or not session_id:
        return jsonify({'error': 'Position name and session are required'}), 400
    
    session = Session.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    # Check if position already exists in this session
    existing_position = Position.query.filter_by(name=name, session_id=session_id).first()
    if existing_position:
        return jsonify({'error': 'A position with this name already exists in this session'}), 400
    
    try:
        new_position = Position(
            name=name,
            session_id=session_id,
            display_order=display_order,
            description=description,
            grade_filter=grade_filter  # Add this
        )
        db.session.add(new_position)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Position "{name}" created successfully',
            'position': {
                'id': new_position.id,
                'name': new_position.name,
                'display_order': new_position.display_order,
                'description': new_position.description,
                'grade_filter': new_position.grade_filter  # Include in response
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create position: {str(e)}'}), 500

@app.route('/api/sessions/<int:session_id>/positions')
def get_session_positions(session_id):
    positions = Position.query.filter_by(session_id=session_id).order_by(Position.display_order, Position.name).all()
    positions_data = []
    
    for position in positions:
        candidate_count = Candidate.query.filter_by(position_id=position.id).count()
        positions_data.append({
            'id': position.id,
            'name': position.name,
            'display_order': position.display_order,
            'description': position.description,
            'candidate_count': candidate_count
        })
    
    return jsonify({'positions': positions_data})

@app.route('/api/positions/<int:position_id>', methods=['DELETE'])
def delete_position(position_id):
    position_to_delete = Position.query.get_or_404(position_id)
    position_name = position_to_delete.name
    
    try:
        db.session.delete(position_to_delete)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Position "{position_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete position: {str(e)}'}), 500

# Candidate Management API
@app.route('/api/candidates', methods=['POST'])
def create_candidate():
    try:
        name = request.form.get('name', '').strip()
        position_id = request.form.get('position_id')
        grade = request.form.get('grade', '').strip()
        manifesto = request.form.get('manifesto', '').strip()
        
        if not name or not position_id:
            return jsonify({'error': 'Candidate name and position are required'}), 400
        
        position = Position.query.get(position_id)
        if not position:
            return jsonify({'error': 'Position not found'}), 404
        
        # Handle photo upload to Cloudinary
        photo_url = None
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename and allowed_file(photo.filename):
                photo_url = upload_to_cloudinary(photo, 'candidates')
                if not photo_url:
                    return jsonify({'error': 'Failed to upload photo'}), 500
        
        new_candidate = Candidate(
            name=name,
            position_id=position_id,
            grade=grade,
            manifesto=manifesto,
            photo_url=photo_url
        )
        db.session.add(new_candidate)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Candidate "{name}" created successfully',
            'candidate': {
                'id': new_candidate.id,
                'name': new_candidate.name,
                'grade': new_candidate.grade,
                'photo_url': new_candidate.photo_url,
                'manifesto': new_candidate.manifesto
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create candidate: {str(e)}'}), 500

@app.route('/api/positions/<int:position_id>/candidates')
def get_position_candidates(position_id):
    candidates = Candidate.query.filter_by(position_id=position_id).order_by(Candidate.name).all()
    candidates_data = []
    
    for candidate in candidates:
        candidates_data.append({
            'id': candidate.id,
            'name': candidate.name,
            'grade': candidate.grade,
            'photo_url': candidate.photo_url,
            'manifesto': candidate.manifesto,
            'votes': candidate.votes
        })
    
    return jsonify({'candidates': candidates_data})

@app.route('/api/candidates/<int:candidate_id>', methods=['DELETE'])
def delete_candidate(candidate_id):
    candidate_to_delete = Candidate.query.get_or_404(candidate_id)
    candidate_name = candidate_to_delete.name
    
    try:
        # Delete photo from Cloudinary if exists
        if candidate_to_delete.photo_url:
            delete_from_cloudinary(candidate_to_delete.photo_url)
        
        db.session.delete(candidate_to_delete)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Candidate "{candidate_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete candidate: {str(e)}'}), 500

# Voter Management API
@app.route('/api/voters', methods=['POST'])
def create_voter():
    try:
        name = request.form.get('name', '').strip()
        grade = request.form.get('grade', '').strip()
        
        if not name or not grade:
            return jsonify({'error': 'Voter name and grade are required'}), 400
        
        # Check if voter name already exists
        existing_voter = Voter.query.filter_by(name=name).first()
        if existing_voter:
            return jsonify({'error': f'Voter "{name}" is already registered'}), 400
        
        # Handle photo upload to Cloudinary
        photo_url = None
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename and allowed_file(photo.filename):
                photo_url = upload_to_cloudinary(photo, 'voters')
                if not photo_url:
                    return jsonify({'error': 'Failed to upload photo'}), 500
        
        # Generate unique student ID and voter code
        student_id = Voter.generate_student_id()
        voter_code = Voter.generate_voter_code()
        
        new_voter = Voter(
            student_id=student_id,
            name=name,
            grade=grade,
            photo_url=photo_url,
            voter_code=voter_code,
            registered_date=datetime.now(timezone.utc)
        )
        db.session.add(new_voter)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Voter "{name}" registered successfully',
            'voter': {
                'id': new_voter.id,
                'student_id': new_voter.student_id,
                'name': new_voter.name,
                'grade': new_voter.grade,
                'voter_code': new_voter.voter_code,
                'photo_url': new_voter.photo_url
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to register voter: {str(e)}'}), 500
    
@app.route('/api/voters')
def get_voters():
    voters = Voter.query.order_by(Voter.registered_date.desc()).all()
    voters_data = []
    
    for voter in voters:
        voters_data.append({
            'id': voter.id,
            'student_id': voter.student_id,
            'name': voter.name,
            'grade': voter.grade,
            'photo_url': voter.photo_url,
            'voter_code': voter.voter_code,
            'registered_date': voter.registered_date.strftime('%Y-%m-%d'),
            'has_voted': voter.has_voted
        })
    
    return jsonify({'voters': voters_data})

@app.route('/api/voters/<int:voter_id>', methods=['DELETE'])
def delete_voter(voter_id):
    voter_to_delete = Voter.query.get_or_404(voter_id)
    voter_name = voter_to_delete.name
    
    try:
        # Delete photo from Cloudinary if exists
        if voter_to_delete.photo_url:
            delete_from_cloudinary(voter_to_delete.photo_url)
        
        if voter_to_delete.has_voted:
            # If the voter has voted, we need to remove their vote
            VotingLog.query.filter_by(voter_id=voter_to_delete.id).delete()
            # Optionally, decrement vote counts for candidates they voted for
            votes = VotingLog.query.filter_by(voter_id=voter_to_delete.id).all()
            for vote in votes:
                candidate = Candidate.query.get(vote.candidate_id)
                if candidate and candidate.votes > 0:
                    candidate.votes -= 1
        db.session.delete(voter_to_delete)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Voter "{voter_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete voter: {str(e)}'}), 500

# Voting API
@app.route('/api/voting/verify', methods=['POST'])
def verify_voter():
    data = request.get_json()
    voter_code = data.get('voter_code', '').strip()
    
    if not voter_code:
        return jsonify({'error': 'Voter code is required'}), 400
    
    voter = Voter.query.filter_by(voter_code=voter_code).first()
    if not voter:
        return jsonify({'error': 'Invalid voter code'}), 404
    
    if voter.has_voted:
        return jsonify({'error': 'This voter has already voted'}), 400
    
    active_session = get_active_session()
    if not active_session:
        return jsonify({'error': 'No active election session'}), 400
    
    # Store voter ID in session for voting
    flask_session['voter_id'] = voter.id
    flask_session['voter_name'] = voter.name
    
    return jsonify({
        'success': True,
        'message': f'Voter verified: {voter.name}',
        'voter': {
            'id': voter.id,
            'name': voter.name,
            'student_id': voter.student_id
        }
    })

@app.route('/api/voting/positions')
def get_voting_positions():
    active_session = get_active_session()
    if not active_session:
        return jsonify({'error': 'No active election session'}), 400
    
    # Get voter information from session
    if 'voter_id' not in flask_session:
        return jsonify({'error': 'Voter not verified'}), 401
    
    voter_id = flask_session['voter_id']
    voter = Voter.query.get(voter_id)
    if not voter:
        return jsonify({'error': 'Voter not found'}), 404
    
    # Get positions that are either for all grades or specifically for this voter's grade
    positions = Position.query.filter_by(session_id=active_session.id).filter(
        (Position.grade_filter.is_(None)) |  # Positions for all grades
        (Position.grade_filter == voter.grade)  # Positions specifically for this grade
    ).order_by(Position.display_order).all()
    
    positions_data = []
    
    for position in positions:
        candidates = Candidate.query.filter_by(position_id=position.id).all()
        candidates_data = []
        
        for candidate in candidates:
            candidates_data.append({
                'id': candidate.id,
                'name': candidate.name,
                'grade': candidate.grade,
                'photo_url': candidate.photo_url,
                'manifesto': candidate.manifesto,
                'votes': candidate.votes
            })
        
        positions_data.append({
            'id': position.id,
            'name': position.name,
            'description': position.description,
            'grade_filter': position.grade_filter,  # Include grade filter info
            'candidates': candidates_data
        })
    
    return jsonify({'positions': positions_data})

@app.route('/api/voting/vote', methods=['POST'])
def cast_vote():
    data = request.get_json()
    position_id = data.get('position_id')
    candidate_id = data.get('candidate_id')
    
    if 'voter_id' not in flask_session:
        return jsonify({'error': 'Voter not verified'}), 401
    
    voter_id = flask_session['voter_id']
    active_session = get_active_session()
    
    if not active_session or not position_id or not candidate_id:
        return jsonify({'error': 'Invalid vote data'}), 400
    
    try:
        # Check if voter has already voted for this position
        existing_vote = VotingLog.query.filter_by(
            session_id=active_session.id,
            position_id=position_id,
            voter_id=voter_id
        ).first()
        
        if existing_vote:
            return jsonify({'error': 'You have already voted for this position'}), 400
        
        # Record the vote
        candidate = Candidate.query.get(candidate_id)
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
        
        # Update candidate vote count
        candidate.votes += 1
        
        # Create voting log entry
        voting_log = VotingLog(
            session_id=active_session.id,
            position_id=position_id,
            candidate_id=candidate_id,
            voter_id=voter_id,
            vote_timestamp=datetime.now(timezone.utc)
        )
        db.session.add(voting_log)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Vote cast successfully for {candidate.name}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to cast vote: {str(e)}'}), 500

@app.route('/api/voting/complete', methods=['POST'])
def complete_voting():
    if 'voter_id' not in flask_session:
        return jsonify({'error': 'Voter not verified'}), 401
    
    voter_id = flask_session['voter_id']
    
    try:
        # Mark voter as voted
        voter = Voter.query.get(voter_id)
        voter.has_voted = True
        db.session.commit()
        
        # Clear voting session
        flask_session.pop('voter_id', None)
        flask_session.pop('voter_name', None)
        
        return jsonify({
            'success': True,
            'message': 'Voting completed successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to complete voting: {str(e)}'}), 500

# Results API
@app.route('/api/results/<int:session_id>')
def get_session_results(session_id):
    session = Session.query.get_or_404(session_id)
    positions = Position.query.filter_by(session_id=session_id).order_by(Position.display_order).all()
    
    results_data = {
        'session': {
            'id': session.id,
            'name': session.name,
            'academic_year': session.academic_year
        },
        'positions': []
    }
    
    total_positions = len(positions)
    total_candidates = 0
    total_votes = 0
    
    for position in positions:
        candidates = Candidate.query.filter_by(position_id=position.id).order_by(Candidate.votes.desc()).all()
        position_votes = sum(candidate.votes for candidate in candidates)
        total_votes += position_votes
        total_candidates += len(candidates)
        
        candidates_data = []
        for i, candidate in enumerate(candidates):
            percentage = (candidate.votes / position_votes * 100) if position_votes > 0 else 0
            is_winner = (i == 0 and len(candidates) > 1 and candidate.votes > 0)
            
            candidates_data.append({
                'id': candidate.id,
                'name': candidate.name,
                'grade': candidate.grade,
                'photo_url': candidate.photo_url,
                'manifesto': candidate.manifesto,
                'votes': candidate.votes,
                'percentage': round(percentage, 1),
                'is_winner': is_winner,
                'rank': i + 1
            })
        
        results_data['positions'].append({
            'id': position.id,
            'name': position.name,
            'description': position.description,
            'total_votes': position_votes,
            'candidates': candidates_data
        })
    
    results_data['statistics'] = {
        'total_positions': total_positions,
        'total_candidates': total_candidates,
        'total_votes': total_votes,
        'average_votes_per_position': total_votes // total_positions if total_positions > 0 else 0
    }
    
    return jsonify(results_data)

# Test database connection
@app.route('/test-db')
def test_db():
    try:
        # Test basic queries
        session_count = Session.query.count()
        voter_count = Voter.query.count()
        position_count = Position.query.count()
        candidate_count = Candidate.query.count()
        
        return jsonify({
            'status': 'success',
            'message': 'PostgreSQL database connection successful',
            'counts': {
                'sessions': session_count,
                'voters': voter_count,
                'positions': position_count,
                'candidates': candidate_count
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Database connection failed: {str(e)}'
        }), 500

# Health check
@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'message': 'Arndale Voting System is running'})

# Vercel handler - THIS MUST BE AT THE END
app

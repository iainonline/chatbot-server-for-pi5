from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, disconnect, join_room, leave_room
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta
import time
from bs4 import BeautifulSoup
from models import db, User, ChatSession, ChatMessage, ModelRating, SystemConfig, UserFeedback
from forms import LoginForm, RegisterForm, ChangePasswordForm, FeedbackForm

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///chatbot.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'connect_args': {'check_same_thread': False}
}
app.config['WTF_CSRF_TIME_LIMIT'] = None  # Disable CSRF timeout for development
app.config['WTF_CSRF_ENABLED'] = False  # Temporarily disable CSRF for testing
# Allow remember me functionality with 30-day duration
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Initialize extensions
db.init_app(app)
csrf = CSRFProtect(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.session_protection = 'strong'  # Strong session protection
login_manager.remember_cookie_duration = timedelta(days=30)  # 30-day remember me duration
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database and create admin user
def init_database():
    """Initialize database tables and create admin user if needed"""
    try:
        with app.app_context():
            db.create_all()
            
            # Create admin user if it doesn't exist
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                admin_user = User(
                    username='admin',
                    email='admin@example.com',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True
                )
                db.session.add(admin_user)
                db.session.commit()
                print("Admin user created: username=admin, password=admin123")
                
            # Initialize default system prompt if it doesn't exist
            from models import SystemConfig
            existing_prompt = SystemConfig.query.filter_by(key='system_prompt').first()
            if not existing_prompt:
                prompt_config = SystemConfig(
                    key='system_prompt',
                    value='You are a helpful AI assistant running on a Raspberry Pi. Be concise and helpful in your responses.',
                    description='Default system prompt for AI responses',
                    updated_by=admin_user.id if admin_user else None
                )
                db.session.add(prompt_config)
                db.session.commit()
                print("Default system prompt initialized")
                
    except Exception as e:
        print(f"Database initialization error: {e}")

# Call initialization
init_database()

# Ollama configuration
OLLAMA_BASE_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')

# Global variable to track streaming states per user session
streaming_sessions = {}

def get_system_config(key, default=None):
    """Get a system configuration value"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default

def set_system_config(key, value, description=None, user_id=None):
    """Set a system configuration value"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = value
        config.updated_at = datetime.utcnow()
        config.updated_by = user_id
    else:
        config = SystemConfig(
            key=key,
            value=value,
            description=description,
            updated_by=user_id
        )
        db.session.add(config)
    db.session.commit()
    return config

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def force_fresh_login():
    """Force fresh authentication for sensitive operations"""
    # Skip for static files and login/logout routes
    if (request.endpoint and 
        (request.endpoint.startswith('static') or 
         request.endpoint in ['login', 'logout', 'index', 'register'])):
        return
    
    # For all other routes, ensure user is logged in
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    # Optional: Force re-authentication after certain time (uncomment if needed)
    # from flask import session
    # from datetime import timedelta
    # if 'login_time' not in session:
    #     session['login_time'] = time.time()
    # elif time.time() - session['login_time'] > 3600:  # 1 hour
    #     logout_user()
    #     flash('Session expired. Please log in again.', 'info')
    #     return redirect(url_for('login'))

# Available Ollama models
AVAILABLE_MODELS = [
    'tinyllama',
    'llama2',
    'llama2:13b',
    'codellama',
    'mistral',
    'mixtral',
    'phi',
    'neural-chat',
    'openchat',
    'vicuna'
]

def get_available_models():
    """Get list of available models from Ollama"""
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            # Always include tinyllama as fallback
            if models and 'tinyllama' not in models:
                models.insert(0, 'tinyllama')
            return models if models else ['tinyllama'] + AVAILABLE_MODELS
        else:
            print(f"Failed to get models from Ollama: {response.status_code}")
            return ['tinyllama'] + AVAILABLE_MODELS
    except Exception as e:
        print(f"Error getting models from Ollama: {e}")
        return ['tinyllama'] + AVAILABLE_MODELS

# Web search functionality
def should_search_web(message):
    """Determine if a message should trigger a web search"""
    search_keywords = [
        'latest', 'recent', 'current', 'today', 'news', 'search', 'find',
        'what is happening', 'what happened', 'when did', 'price of',
        'weather', 'stock', 'current events', 'breaking news',
        'latest news', 'recent news', 'search for', 'look up', 'now',
        'currently', 'this year', 'this month', 'update', 'status'
    ]
    
    message_lower = message.lower()
    triggered_keywords = [keyword for keyword in search_keywords if keyword in message_lower]
    
    if triggered_keywords:
        print(f"Web search triggered by keywords: {triggered_keywords}")
        return True
    
    print(f"No web search keywords detected in: '{message}'")
    return False

def search_web(query, max_results=3):
    """Search the web using DuckDuckGo and return relevant results"""
    try:
        print(f"Starting web search for: '{query}'")
        
        # Use DuckDuckGo search (no API key required)
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print(f"Sending request to DuckDuckGo: {search_url}")
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Search request failed with status code: {response.status_code}")
            return None
        
        print("Parsing search results...")
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        # Find search result links
        result_links = soup.find_all('a', {'class': 'result__a'})
        print(f"Found {len(result_links)} potential search result links")
        
        for i, link in enumerate(result_links[:max_results]):
            if link.get('href'):
                url = link.get('href')
                title = link.get_text(strip=True)
                
                print(f"Processing result {i+1}: {title[:50]}...")
                print(f"  URL: {url}")
                
                # Try to get a snippet of content from the page
                snippet = get_page_snippet(url)
                print(f"  Content snippet length: {len(snippet)} characters")
                
                results.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet
                })
        
        print(f"Successfully processed {len(results)} search results")
        return results if results else None
        
    except Exception as e:
        print(f"Web search error: {e}")
        return None

def get_page_snippet(url, max_length=300):
    """Get a snippet of text content from a web page"""
    try:
        print(f"    Fetching content from: {url[:60]}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            print(f"    Failed to fetch content: HTTP {response.status_code}")
            return "Content not available"
        
        print(f"    Successfully fetched {len(response.content)} bytes")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Return first part of text
        result = text[:max_length] + "..." if len(text) > max_length else text
        print(f"    Extracted snippet: {len(result)} characters")
        return result
        
    except Exception as e:
        print(f"    Error fetching content: {e}")
        return "Content not available"

def format_search_results(results):
    """Format search results for the LLM"""
    if not results:
        return "No search results found."
    
    formatted = "[WEB_SEARCH_START]=== WEB SEARCH RESULTS ===[WEB_SEARCH_END]\n\n"
    formatted += f"[WEB_SEARCH_START]Search completed successfully. Found {len(results)} relevant sources:[WEB_SEARCH_END]\n\n"
    
    for i, result in enumerate(results, 1):
        formatted += f"[WEB_SEARCH_START]Source {i} of {len(results)}:[WEB_SEARCH_END]\n"
        formatted += f"[WEB_SEARCH_START]Title: {result['title']}[WEB_SEARCH_END]\n"
        formatted += f"[WEB_SEARCH_START]URL: {result['url']}[WEB_SEARCH_END]\n"
        formatted += f"[WEB_SEARCH_START]Content Summary: {result['snippet']}[WEB_SEARCH_END]\n"
        formatted += "[WEB_SEARCH_START]" + "-" * 60 + "[WEB_SEARCH_END]\n\n"
    
    formatted += "[WEB_SEARCH_START]Please use the above information to provide an accurate, current response.[WEB_SEARCH_END]\n"
    formatted += "[WEB_SEARCH_START]When referencing these sources, mention them by their source number (e.g., 'According to Source 1...').[WEB_SEARCH_END]\n\n"
    
    return formatted

@app.route('/')
def index():
    # Check if user is already authenticated (including remember me)
    if current_user.is_authenticated:
        # Redirect based on user role
        if current_user.is_admin:
            return redirect(url_for('admin'))
        else:
            return redirect(url_for('chat'))
    # If not authenticated, redirect to login
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    form = LoginForm()
    print(f"Form submitted: {form.is_submitted()}")
    print(f"Form validation: {form.validate_on_submit()}")
    print(f"Request method: {request.method}")
    
    if request.method == 'POST':
        print(f"POST data: {request.form}")
        print(f"Form data - username: {form.username.data}, password: {'*' * len(form.password.data) if form.password.data else 'None'}")
    
    if form.validate_on_submit():
        print(f"Looking for user: {form.username.data}")
        user = User.query.filter_by(username=form.username.data).first()
        print(f"User found: {user is not None}")
        
        if user:
            password_check = check_password_hash(user.password_hash, form.password.data)
            print(f"Password check: {password_check}")
            
            if password_check:
                # Use remember_me option from form
                remember_me = form.remember_me.data
                login_user(user, remember=remember_me, force=True, fresh=True)
                print(f"User logged in: {current_user.is_authenticated}, Remember me: {remember_me}")
                # Redirect admin users to admin dashboard, regular users to chat
                if user.is_admin:
                    return redirect(url_for('admin'))
                else:
                    return redirect(url_for('chat'))
            else:
                flash('Invalid username or password', 'error')
        else:
            flash('Invalid username or password', 'error')
    else:
        if form.is_submitted():
            print(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{field.title()}: {error}', 'error')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists')
            return render_template('register.html', form=form)
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        db.session.commit()
        
        # Log in new user with default remember=False
        login_user(user, remember=False, force=True, fresh=True)
        return redirect(url_for('chat'))
    
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # Verify current password
        if not check_password_hash(current_user.password_hash, form.current_password.data):
            flash('Current password is incorrect.', 'error')
            return render_template('change_password.html', form=form)
        
        # Update password
        current_user.password_hash = generate_password_hash(form.new_password.data)
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        # Redirect based on user role
        if current_user.is_admin:
            return redirect(url_for('admin'))
        else:
            return redirect(url_for('chat'))
    
    return render_template('change_password.html', form=form)

@app.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback():
    form = FeedbackForm()
    
    if form.validate_on_submit():
        feedback = UserFeedback(
            user_id=current_user.id,
            feedback_type=form.feedback_type.data,
            title=form.title.data,
            description=form.description.data,
            priority=form.priority.data
        )
        db.session.add(feedback)
        db.session.commit()
        
        flash('Thank you for your feedback! We appreciate your input.', 'success')
        return redirect(url_for('chat'))
    
    return render_template('feedback.html', form=form)

@app.route('/chat')
@login_required
def chat():
    sessions = ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).all()
    
    # Get the session parameter if provided
    selected_session_id = request.args.get('session', type=int)
    
    # Convert sessions to dictionaries with parameters
    sessions_data = []
    for session in sessions:
        sessions_data.append({
            'id': session.id,
            'title': session.title,
            'model_name': session.model_name,
            'created_at': session.created_at,
            'parameters': {
                'temperature': session.temperature,
                'max_tokens': session.max_tokens,
                'top_p': session.top_p,
                'top_k': session.top_k,
                'repeat_penalty': session.repeat_penalty
            }
        })
    
    return render_template('chat.html', sessions=sessions_data, selected_session=selected_session_id)

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('chat'))
    
    # Get statistics
    total_users = User.query.count()
    total_sessions = ChatSession.query.count()
    total_messages = ChatMessage.query.count()
    
    # Get model usage statistics
    model_stats = db.session.query(
        ChatSession.model_name,
        db.func.count(ChatSession.id).label('usage_count'),
        db.func.avg(ModelRating.rating).label('avg_rating')
    ).outerjoin(ModelRating, ChatSession.id == ModelRating.session_id)\
     .group_by(ChatSession.model_name).all()
    
    # Get recent activity
    recent_sessions = ChatSession.query.order_by(ChatSession.created_at.desc()).limit(10).all()
    
    # Get user feedback
    user_feedback = UserFeedback.query.order_by(UserFeedback.created_at.desc()).limit(20).all()
    
    return render_template('admin.html', 
                         total_users=total_users,
                         total_sessions=total_sessions,
                         total_messages=total_messages,
                         model_stats=model_stats,
                         recent_sessions=recent_sessions,
                         user_feedback=user_feedback,
                         system_prompt=get_system_config('system_prompt', ''))

@app.route('/admin/system-config', methods=['POST'])
@login_required
def update_system_config():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    system_prompt = data.get('system_prompt', '').strip()
    
    set_system_config(
        'system_prompt', 
        system_prompt, 
        'System prompt that defines how the AI should behave',
        current_user.id
    )
    
    return jsonify({
        'status': 'success',
        'message': 'System prompt updated successfully'
    })

@app.route('/admin/save-default-parameters', methods=['POST'])
@login_required
def save_default_parameters():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data received'
            }), 400
        
        # Save each parameter as system config
        parameters = {
            'default_temperature': data.get('temperature', 0.7),
            'default_max_tokens': data.get('max_tokens', 2048),
            'default_top_p': data.get('top_p', 0.9),
            'default_top_k': data.get('top_k', 50),
            'default_repeat_penalty': data.get('repeat_penalty', 1.0)
        }
        
        for key, value in parameters.items():
            set_system_config(
                key, 
                str(value), 
                f'Default {key.replace("default_", "").replace("_", " ")} parameter',
                current_user.id
            )
        
        return jsonify({
            'status': 'success',
            'message': 'Default parameters saved successfully!'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error saving parameters: {str(e)}'
        }), 500

@app.route('/api/default-parameters')
@login_required 
def get_default_parameters():
    """Get current default parameters set by admin"""
    try:
        defaults = {
            'temperature': float(get_system_config('default_temperature', '0.7')),
            'max_tokens': int(get_system_config('default_max_tokens', '2048')),
            'top_p': float(get_system_config('default_top_p', '0.9')),
            'top_k': int(get_system_config('default_top_k', '50')),
            'repeat_penalty': float(get_system_config('default_repeat_penalty', '1.0'))
        }
        
        return jsonify({
            'status': 'success',
            'parameters': defaults
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error getting default parameters: {str(e)}'
        }), 500

@app.route('/admin/save-default-model', methods=['POST'])
@login_required
def save_default_model():
    """Save the default model for new chat sessions"""
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    model_name = data.get('model_name', '').strip()
    
    if not model_name:
        return jsonify({
            'status': 'error',
            'message': 'Model name is required'
        }), 400
    
    # Verify model exists in Ollama
    available_models = get_available_models()
    if model_name not in available_models:
        return jsonify({
            'status': 'error',
            'message': f'Model "{model_name}" is not available in Ollama'
        }), 400
    
    try:
        # Save default model as system config
        set_system_config(
            'default_model', 
            model_name, 
            f'Default model for new chat sessions',
            current_user.id
        )
        
        return jsonify({
            'status': 'success',
            'message': f'Default model set to "{model_name}" successfully!'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error saving default model: {str(e)}'
        }), 500

@app.route('/api/current-default-model')
@login_required
def get_current_default_model():
    """Get the current default model"""
    try:
        available_models = get_available_models()
        default_model = get_system_config('default_model', available_models[0] if available_models else 'tinyllama')
        
        return jsonify({
            'status': 'success',
            'model': default_model
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error getting default model: {str(e)}'
        }), 500

@app.route('/api/models')
@login_required
def get_models():
    """Get available models from Ollama"""
    try:
        models = get_available_models()
        return jsonify({
            'status': 'success',
            'models': models
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to get models: {str(e)}'
        }), 500

@app.route('/api/download-model', methods=['POST'])
@login_required
def download_model():
    """Download a model via Ollama with progress tracking"""
    print(f"Download model request received from user: {current_user.username}")
    
    if not current_user.is_admin:
        print(f"Access denied for non-admin user: {current_user.username}")
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    model_name = data.get('model_name', '').strip()
    
    print(f"Model name requested: {model_name}")
    
    if not model_name:
        return jsonify({
            'status': 'error',
            'message': 'Model name is required'
        }), 400
    
    try:
        # Start download in background and return immediately
        print(f"Starting background task for model: {model_name}")
        socketio.start_background_task(target=download_model_with_progress, model_name=model_name, user_id=current_user.id)
        
        return jsonify({
            'status': 'success',
            'message': f'Download started for {model_name}. Watch the progress below.'
        })
            
    except Exception as e:
        print(f"Error starting download: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error starting download: {str(e)}'
        }), 500

def download_model_with_progress(model_name, user_id):
    """Download model with real-time progress updates via WebSocket"""
    try:
        url = f"{OLLAMA_BASE_URL}/api/pull"
        payload = {"name": model_name}
        
        # Emit start event to all clients (simplified)
        socketio.emit('download_progress', {
            'model': model_name,
            'status': 'starting',
            'message': f'Starting download of {model_name}...',
            'progress': 0
        })
        
        print(f"Starting download of {model_name}")
        response = requests.post(url, json=payload, stream=True, timeout=1800)
        
        if response.status_code != 200:
            socketio.emit('download_progress', {
                'model': model_name,
                'status': 'error',
                'message': f'Failed to start download: {response.text}',
                'progress': 0
            })
            return
        
        print(f"Download response status: {response.status_code}")
        
        # Process streaming response
        for line in response.iter_lines():
            if line:
                try:
                    progress_data = json.loads(line.decode('utf-8'))
                    print(f"Progress data: {progress_data}")
                    
                    # Extract progress information
                    status = progress_data.get('status', '')
                    total = progress_data.get('total', 0)
                    completed = progress_data.get('completed', 0)
                    
                    # Calculate progress percentage
                    progress = 0
                    if total > 0:
                        progress = int((completed / total) * 100)
                    
                    # Emit progress update to all clients
                    socketio.emit('download_progress', {
                        'model': model_name,
                        'status': 'downloading',
                        'message': f'{status}: {progress}%' if status else f'Downloading: {progress}%',
                        'progress': progress,
                        'completed': completed,
                        'total': total
                    })
                    
                    # Check if download is complete
                    if progress >= 100 or 'success' in status.lower() or status == 'success':
                        socketio.emit('download_progress', {
                            'model': model_name,
                            'status': 'completed',
                            'message': f'Successfully downloaded {model_name}!',
                            'progress': 100
                        })
                        print(f"Download completed: {model_name}")
                        break
                        
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"Error processing progress line: {e}")
                    continue
                    
    except Exception as e:
        print(f"Download error: {e}")
        socketio.emit('download_progress', {
            'model': model_name,
            'status': 'error',
            'message': f'Download failed: {str(e)}',
            'progress': 0
        })

@app.route('/api/sessions', methods=['POST'])
@login_required
def create_session():
    try:
        data = request.get_json()
        available_models = get_available_models()
        
        print(f"Creating session for user: {current_user.username}")
        print(f"Available models: {available_models}")
        
        # Get the admin-set default model with better error handling
        try:
            default_model = get_system_config('default_model', 'tinyllama')
            print(f"Retrieved default model from config: {default_model}")
            
            # Always ensure we have a fallback model
            if not default_model:
                default_model = 'tinyllama'
                print(f"No default model found, using fallback: {default_model}")
                
            # If available models list is empty, use the default anyway
            if not available_models:
                print("No models available from Ollama, using default model anyway")
                available_models = [default_model]
                
            # If default model is not in available models, add it or use first available
            if default_model not in available_models:
                if available_models:
                    print(f"Default model '{default_model}' not available, using first available: {available_models[0]}")
                    default_model = available_models[0]
                else:
                    print(f"Using configured default model: {default_model}")
                    available_models.append(default_model)
                    
        except Exception as e:
            print(f"Error getting default model, using tinyllama fallback: {e}")
            default_model = 'tinyllama'
            if not available_models:
                available_models = ['tinyllama']
            
        print(f"Final default model: {default_model}")
        
        if hasattr(current_user, 'is_admin') and current_user.is_admin:
            model_name = data.get('model', default_model)
        else:
            # Regular users always use the admin-set default
            model_name = default_model

        # Ensure we always have a valid model
        if not model_name:
            model_name = 'tinyllama'
            
        print(f"Selected model: {model_name}")

        # Get parameters with defaults
        temperature = float(data.get('temperature', 0.7))
        max_tokens = int(data.get('max_tokens', 2048))
        top_p = float(data.get('top_p', 0.9))
        top_k = int(data.get('top_k', 40))
        repeat_penalty = float(data.get('repeat_penalty', 1.1))
        
        # Validate parameter ranges
        temperature = max(0.1, min(2.0, temperature))
        max_tokens = max(100, min(4096, max_tokens))
        top_p = max(0.1, min(1.0, top_p))
        top_k = max(1, min(100, top_k))
        repeat_penalty = max(0.5, min(2.0, repeat_penalty))

        session = ChatSession(
            user_id=current_user.id,
            model_name=model_name,
            title=f"Chat with {model_name}",
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty
        )
        db.session.add(session)
        db.session.commit()

        # Add welcome message from PiBot
        welcome_message = ChatMessage(
            session_id=session.id,
            role='assistant',
            content='Welcome to PiBot, how can I help you?'
        )
        db.session.add(welcome_message)
        db.session.commit()

        return jsonify({
            'session_id': session.id,
            'title': session.title,
            'model': session.model_name,
            'parameters': {
                'temperature': session.temperature,
                'max_tokens': session.max_tokens,
                'top_p': session.top_p,
                'top_k': session.top_k,
                'repeat_penalty': session.repeat_penalty
            },
            'status': 'success'
        })
    except Exception as e:
        print(f"Error creating session: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error creating session: {str(e)}'
        }), 500

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    # Verify session belongs to current user
    session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        return jsonify({'error': 'Session not found or access denied'}), 404
    
    # Delete associated messages and ratings first (cascade delete)
    ChatMessage.query.filter_by(session_id=session_id).delete()
    ModelRating.query.filter_by(session_id=session_id).delete()
    
    # Delete the session
    db.session.delete(session)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Session deleted successfully'})

@app.route('/api/sessions/<int:session_id>/parameters', methods=['PUT'])
@login_required
def update_session_parameters(session_id):
    # Verify session belongs to current user
    session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        return jsonify({'error': 'Session not found or access denied'}), 404
    
    data = request.get_json()
    
    # Update parameters with validation
    if 'temperature' in data:
        session.temperature = max(0.1, min(2.0, float(data['temperature'])))
    if 'max_tokens' in data:
        session.max_tokens = max(100, min(4096, int(data['max_tokens'])))
    if 'top_p' in data:
        session.top_p = max(0.1, min(1.0, float(data['top_p'])))
    if 'top_k' in data:
        session.top_k = max(1, min(100, int(data['top_k'])))
    if 'repeat_penalty' in data:
        session.repeat_penalty = max(0.5, min(2.0, float(data['repeat_penalty'])))
    
    session.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'parameters': {
            'temperature': session.temperature,
            'max_tokens': session.max_tokens,
            'top_p': session.top_p,
            'top_k': session.top_k,
            'repeat_penalty': session.repeat_penalty
        }
    })

@app.route('/api/sessions/<int:session_id>/messages')
@login_required
def get_messages(session_id):
    session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    messages = ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.timestamp).all()
    
    return jsonify([{
        'id': msg.id,
        'role': msg.role,
        'content': msg.content,
        'timestamp': msg.timestamp.isoformat()
    } for msg in messages])

@app.route('/api/rate', methods=['POST'])
@login_required
def rate_response():
    data = request.get_json()
    session_id = data.get('session_id')
    rating = data.get('rating')
    
    session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    
    # Check if rating already exists
    existing_rating = ModelRating.query.filter_by(session_id=session_id, user_id=current_user.id).first()
    if existing_rating:
        existing_rating.rating = rating
    else:
        model_rating = ModelRating(
            session_id=session_id,
            user_id=current_user.id,
            model_name=session.model_name,
            rating=rating
        )
        db.session.add(model_rating)
    
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/ollama/status')
@login_required
def ollama_status():
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            return jsonify({'status': 'online', 'models': response.json()})
        else:
            return jsonify({'status': 'offline'})
    except:
        return jsonify({'status': 'offline'})

@app.route('/api/export/chat-data')
@login_required
def export_chat_data():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    # Export all chat data as JSON
    sessions = ChatSession.query.all()
    data = []
    
    for session in sessions:
        session_data = {
            'id': session.id,
            'user': session.user.username,
            'model': session.model_name,
            'title': session.title,
            'created_at': session.created_at.isoformat(),
            'messages': []
        }
        
        for message in session.messages:
            session_data['messages'].append({
                'role': message.role,
                'content': message.content,
                'timestamp': message.timestamp.isoformat()
            })
        
        data.append(session_data)
    
    return jsonify(data)

@app.route('/api/export/user-stats')
@login_required
def export_user_stats():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    # Export user statistics
    users = User.query.all()
    stats = []
    
    for user in users:
        user_stats = {
            'username': user.username,
            'email': user.email,
            'created_at': user.created_at.isoformat(),
            'total_sessions': len(user.chat_sessions),
            'total_messages': sum(len(session.messages) for session in user.chat_sessions),
            'ratings_given': len(user.ratings),
            'avg_rating_given': sum(rating.rating for rating in user.ratings) / len(user.ratings) if user.ratings else 0
        }
        stats.append(user_stats)
    
    return jsonify(stats)

@socketio.on('connect')
@login_required
def handle_connect():
    print(f'User {current_user.username} connected')
    # Join user to their personal room for progress updates
    join_room(f'user_{current_user.id}')

@socketio.on('disconnect')
@login_required
def handle_disconnect():
    print(f'User {current_user.username} disconnected')
    # Leave user's personal room
    leave_room(f'user_{current_user.id}')
    # Clean up any streaming sessions for this user
    if current_user.id in streaming_sessions:
        del streaming_sessions[current_user.id]

@socketio.on('stop_generation')
@login_required
def handle_stop_generation(data):
    session_id = data.get('session_id')
    user_id = current_user.id
    
    print(f'User {current_user.username} requested to stop generation for session {session_id}')
    
    # Mark this session as stopped
    if user_id in streaming_sessions:
        streaming_sessions[user_id]['stopped'] = True
        print(f'Marked streaming session as stopped for user {user_id}')
        
        # Emit stop confirmation
        emit('generation_stopped', {
            'session_id': session_id,
            'message': 'Generation stopped by user'
        })
    else:
        print(f'No active streaming session found for user {user_id}')
        emit('error', {'message': 'No active generation to stop'})

@socketio.on('send_message')
@login_required
def handle_message(data):
    session_id = data['session_id']
    message = data['message']
    
    # Verify session belongs to current user
    session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        emit('error', {'message': 'Invalid session'})
        return
    
    # Save user message
    user_message = ChatMessage(
        session_id=session_id,
        role='user',
        content=message
    )
    db.session.add(user_message)
    db.session.commit()
    
    # Check if we should search the web
    search_results = None
    enhanced_prompt = message
    
    if should_search_web(message):
        print(f"Web search triggered for query: {message}")
        emit('web_search_start', {'message': 'Initiating web search for current information...'})
        
        # Add a small delay to show the initial message
        socketio.sleep(0.5)
        emit('web_search_progress', {'message': 'Connecting to search engine...'})
        
        search_results = search_web(message)
        
        if search_results:
            print(f"Found {len(search_results)} search results")
            emit('web_search_progress', {'message': f'Found {len(search_results)} relevant sources. Extracting content...'})
            
            # Show progress for each result being processed
            for i, result in enumerate(search_results, 1):
                emit('web_search_progress', {
                    'message': f'Processing source {i}/{len(search_results)}: {result["title"][:40]}...'
                })
                socketio.sleep(0.3)  # Small delay to show progress
            
            search_context = format_search_results(search_results)
            
            # Get system prompt
            system_prompt = get_system_config('system_prompt', '')
            base_prompt = system_prompt + '\n\n' if system_prompt else ''
            
            enhanced_prompt = f"""{base_prompt}You are a helpful AI assistant. A user has asked: "{message}"

{search_context}

Please provide a well-structured, comprehensive answer following these formatting guidelines:

1. Start with a clear, direct answer to the question
2. Use bullet points or numbered lists when appropriate
3. Add line breaks between different topics or sections
4. When referencing web sources, mention them clearly
5. Use clear headings or separators for different sections
6. Keep paragraphs concise and readable
7. End with a brief summary if the answer is long

User's question: {message}

Please format your response clearly with proper spacing and structure."""
            
            emit('web_search_complete', {
                'message': f'Successfully gathered information from {len(search_results)} sources. Analyzing and generating response...',
                'results_count': len(search_results)
            })
        else:
            print("No search results found")
            emit('web_search_progress', {'message': 'No current web results found for this query.'})
            socketio.sleep(0.5)
            emit('web_search_complete', {
                'message': 'Web search completed. Using available knowledge to answer your question...',
                'results_count': 0
            })
    else:
        print(f"No web search needed for: {message}")
        # Get system prompt
        system_prompt = get_system_config('system_prompt', '')
        base_prompt = system_prompt + '\n\n' if system_prompt else ''
        
        # Enhance regular prompts for better formatting
        enhanced_prompt = f"""{base_prompt}You are a helpful AI assistant. Please provide a well-structured response to the following question.

Use clear formatting with:
- Bullet points or numbered lists when appropriate
- Line breaks between different topics
- Clear, concise paragraphs
- Proper spacing for readability

User's question: {message}

Please provide a comprehensive, well-formatted answer:"""

    # Send message to Ollama and stream response
    try:
        user_id = current_user.id
        
        # Initialize streaming session tracking
        streaming_sessions[user_id] = {
            'session_id': session_id,
            'stopped': False,
            'start_time': time.time()
        }
        
        ollama_url = f"{OLLAMA_BASE_URL}/api/generate"
        payload = {
            'model': session.model_name,
            'prompt': enhanced_prompt,
            'stream': True,
            'options': {
                'temperature': session.temperature,
                'num_predict': session.max_tokens,
                'top_p': session.top_p,
                'top_k': session.top_k,
                'repeat_penalty': session.repeat_penalty
            }
        }
        
        # Start timing
        start_time = time.time()
        first_token_time = None
        token_count = 0
        
        response = requests.post(ollama_url, json=payload, stream=True, timeout=120)
        response.raw.decode_content = True  # Ensure proper streaming
        
        if response.status_code == 200:
            full_response = ""
            
            # Emit streaming start event
            emit('streaming_start', {
                'model': session.model_name,
                'timestamp': start_time,
                'session_id': session_id
            })
            
            for line in response.iter_lines():
                # Check if user requested to stop
                if user_id in streaming_sessions and streaming_sessions[user_id].get('stopped', False):
                    print(f"Stopping generation for user {user_id} as requested")
                    
                    # Save partial response if we have any
                    if full_response.strip():
                        assistant_message = ChatMessage(
                            session_id=session_id,
                            role='assistant',
                            content=full_response + "\n\n[Generation stopped by user]"
                        )
                        db.session.add(assistant_message)
                        db.session.commit()
                        
                        # Emit the final partial content
                        emit('message_chunk', {
                            'chunk': "\n\n[Generation stopped by user]",
                            'token_count': token_count,
                            'stopped': True
                        })
                    
                    # Clean up streaming session
                    if user_id in streaming_sessions:
                        del streaming_sessions[user_id]
                    
                    # Emit stop completion
                    emit('message_complete', {
                        'stopped': True,
                        'total_tokens': token_count,
                        'total_time': round(time.time() - start_time, 3),
                        'model': session.model_name,
                        'message': 'Generation stopped by user'
                    })
                    break
                
                if line:
                    try:
                        json_response = json.loads(line.decode('utf-8'))
                        
                        if 'response' in json_response:
                            chunk = json_response['response']
                            full_response += chunk
                            
                            # Better token counting - split by words and special characters
                            if chunk.strip():
                                # Count actual tokens more accurately
                                words = len(chunk.split())
                                chars = len(chunk.strip())
                                chunk_tokens = max(words, chars // 4)  # Estimate tokens as words or chars/4
                                token_count += chunk_tokens
                                
                                # Record first token time
                                if first_token_time is None:
                                    first_token_time = time.time()
                                    time_to_first_token = first_token_time - start_time
                                    emit('first_token', {
                                        'time_to_first_token': round(time_to_first_token, 3)
                                    })
                                
                                # Calculate current tokens per second with smoothing
                                current_time = time.time()
                                elapsed_time = current_time - (first_token_time or start_time)
                                tokens_per_second = token_count / elapsed_time if elapsed_time > 0 else 0
                                
                                # Emit chunk immediately for better responsiveness
                                socketio.emit('message_chunk', {
                                    'chunk': chunk,
                                    'token_count': token_count,
                                    'tokens_per_second': round(tokens_per_second, 2),
                                    'elapsed_time': round(elapsed_time, 3),
                                    'chunk_size': len(chunk),
                                    'words_in_chunk': len(chunk.split()) if chunk.split() else 0
                                })
                                
                                # Force immediate transmission
                                socketio.sleep(0)
                        
                        if json_response.get('done', False):
                            # Calculate final metrics
                            end_time = time.time()
                            total_time = end_time - start_time
                            final_tokens_per_second = token_count / total_time if total_time > 0 else 0
                            
                            # Get additional metrics from Ollama response
                            eval_count = json_response.get('eval_count', 0)
                            eval_duration = json_response.get('eval_duration', 0)
                            prompt_eval_count = json_response.get('prompt_eval_count', 0)
                            prompt_eval_duration = json_response.get('prompt_eval_duration', 0)
                            
                            # Save assistant message
                            assistant_message = ChatMessage(
                                session_id=session_id,
                                role='assistant',
                                content=full_response
                            )
                            db.session.add(assistant_message)
                            db.session.commit()
                            
                            # Clean up streaming session
                            if user_id in streaming_sessions:
                                del streaming_sessions[user_id]
                            
                            # Emit completion with full metrics
                            emit('message_complete', {
                                'total_tokens': token_count,
                                'total_time': round(total_time, 3),
                                'tokens_per_second': round(final_tokens_per_second, 2),
                                'time_to_first_token': round((first_token_time - start_time) if first_token_time else 0, 3),
                                'ollama_eval_count': eval_count,
                                'ollama_eval_duration_ms': round(eval_duration / 1_000_000, 2) if eval_duration else 0,
                                'ollama_prompt_eval_count': prompt_eval_count,
                                'ollama_prompt_eval_duration_ms': round(prompt_eval_duration / 1_000_000, 2) if prompt_eval_duration else 0,
                                'model': session.model_name
                            })
                            break
                    except json.JSONDecodeError:
                        continue
        else:
            # Clean up streaming session on error
            if user_id in streaming_sessions:
                del streaming_sessions[user_id]
            
            # Provide more specific error messages
            if response.status_code == 404:
                emit('error', {'message': f'Model "{session.model_name}" not found in Ollama. Please check available models.'})
            elif response.status_code == 400:
                emit('error', {'message': f'Invalid request to Ollama. Check model parameters.'})
            else:
                emit('error', {'message': f'Failed to get response from Ollama. Status: {response.status_code}'})
            
    except requests.exceptions.ConnectionError:
        # Clean up streaming session on error
        if current_user.id in streaming_sessions:
            del streaming_sessions[current_user.id]
        emit('error', {'message': 'Failed to connect to Ollama. Make sure Ollama is running.'})
    except requests.exceptions.Timeout:
        # Clean up streaming session on error
        if current_user.id in streaming_sessions:
            del streaming_sessions[current_user.id]
        emit('error', {'message': 'Request to Ollama timed out. Try again.'})
    except Exception as e:
        # Clean up streaming session on error
        if current_user.id in streaming_sessions:
            del streaming_sessions[current_user.id]
        emit('error', {'message': f'Error: {str(e)}'})

# Status page and API endpoints
@app.route('/status')
@login_required
def status():
    """Server status page - Admin only"""
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('chat'))
    return render_template('status.html')

@app.route('/api/status')
@login_required
def api_status():
    """API endpoint for server status information - Admin only"""
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
    
    import psutil
    import datetime
    import subprocess
    import requests
    
    def get_local_ip():
        """Get the local IP address"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def get_external_ip():
        """Get the external IP address"""
        try:
            response = requests.get('https://api.ipify.org', timeout=5)
            return response.text.strip()
        except Exception:
            return "Unable to fetch"
    
    def get_wifi_ssid():
        """Get the current WiFi SSID"""
        try:
            # Try nmcli first (NetworkManager)
            result = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('yes:'):
                        return line.split(':', 1)[1]
        except Exception:
            pass
        
        # Fallback to iwgetid
        try:
            result = subprocess.run(['iwgetid', '-r'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return "Unknown"
    
    def get_ollama_status():
        """Check Ollama server status and available models"""
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return {
                    'status': 'running',
                    'models': [model['name'] for model in models],
                    'model_count': len(models)
                }
            else:
                return {'status': 'error', 'models': [], 'model_count': 0}
        except Exception as e:
            return {'status': 'offline', 'models': [], 'model_count': 0, 'error': str(e)}
    
    def get_system_info():
        """Get system resource information"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_used_gb = memory.used / (1024**3)
            memory_total_gb = memory.total / (1024**3)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_used_gb = disk.used / (1024**3)
            disk_total_gb = disk.total / (1024**3)
            
            # System uptime
            boot_time = psutil.boot_time()
            uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(boot_time)
            
            return {
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'memory_used_gb': round(memory_used_gb, 2),
                'memory_total_gb': round(memory_total_gb, 2),
                'memory_percent': memory.percent,
                'disk_used_gb': round(disk_used_gb, 2),
                'disk_total_gb': round(disk_total_gb, 2),
                'disk_percent': disk.percent,
                'uptime_days': uptime.days,
                'uptime_hours': uptime.seconds // 3600,
                'uptime_minutes': (uptime.seconds % 3600) // 60
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_database_stats():
        """Get database statistics"""
        try:
            total_users = User.query.count()
            total_sessions = ChatSession.query.count()
            total_messages = ChatMessage.query.count()
            total_ratings = ModelRating.query.count()
            
            # Recent activity (last 24 hours)
            yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
            recent_sessions = ChatSession.query.filter(ChatSession.created_at >= yesterday).count()
            recent_messages = ChatMessage.query.filter(ChatMessage.timestamp >= yesterday).count()
            
            return {
                'total_users': total_users,
                'total_sessions': total_sessions,
                'total_messages': total_messages,
                'total_ratings': total_ratings,
                'recent_sessions_24h': recent_sessions,
                'recent_messages_24h': recent_messages
            }
        except Exception as e:
            return {'error': str(e)}
    
    # Gather all status information
    status_data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'server': {
            'local_ip': get_local_ip(),
            'external_ip': get_external_ip(),
            'wifi_ssid': get_wifi_ssid(),
            'port': 8080,
            'debug_mode': app.debug
        },
        'ollama': get_ollama_status(),
        'system': get_system_info(),
        'database': get_database_stats()
    }
    
    return jsonify(status_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create admin user if it doesn't exist
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created: username=admin, password=admin123")
        
        # Initialize default system prompt if it doesn't exist
        if not get_system_config('system_prompt'):
            set_system_config(
                'system_prompt',
                'Hello. I am PiBot, your friendly PiPowered LLM. I can use my local database and search the web! A human is going to communicate with you, behave like a chatbot and give informative and meaningful responses, like a buddha perhaps',
                'System prompt that defines how the AI should behave'
            )
            print("Default system prompt created")
        
        # Initialize default model to tinyllama if not set
        if not get_system_config('default_model'):
            set_system_config(
                'default_model',
                'tinyllama',
                'Default model for new chat sessions'
            )
            print("Default model set to tinyllama")
    
    # Display server access information
    def get_local_ip():
        """Get the local IP address of this machine"""
        try:
            import socket
            # Connect to a remote server to get local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "localhost"
    
    def get_external_ip():
        """Get the external/public IP address using curl"""
        try:
            import subprocess
            result = subprocess.run(['curl', '-s', 'ifconfig.me'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        # Fallback to another service
        try:
            result = subprocess.run(['curl', '-s', 'ipinfo.io/ip'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return "Unable to detect"
    
    def get_wifi_ssid():
        """Get the current WiFi SSID"""
        try:
            import subprocess
            # Try nmcli first (NetworkManager)
            result = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('yes:'):
                        return line.split(':', 1)[1]
        except Exception:
            pass
        
        # Fallback to iwgetid
        try:
            result = subprocess.run(['iwgetid', '-r'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return None
    
    local_ip = get_local_ip()
    external_ip = get_external_ip()
    current_ssid = get_wifi_ssid()
    port = 8080
    
    print("\n" + "="*60)
    print("🤖 PiBot - Your LLM for the end of the world")
    print("="*60)
    print(f"🏠 Local access:     http://localhost:{port}")
    print(f"🌐 Network access:   http://{local_ip}:{port}")
    print(f"📱 Mobile access:    http://{external_ip}:{port}")
    
    # WiFi SSID check for WAN access
    if current_ssid:
        print(f"📶 WiFi Network:     {current_ssid}")
        if current_ssid == "24GHZ":
            print("✅ WAN Access:       Available (Port 8080 open)")
        else:
            print("⚠️  WAN Access:       Limited (Port 8080 may be blocked)")
            print("   Note: External access requires '24GHZ' network")
    else:
        print("📶 Network:          Unable to detect WiFi")
        print("⚠️  WAN Access:       Unknown (Check network connection)")
    
    print("="*60)
    print("📋 Local network: Use the network IP from other devices on same network")
    print("🌍 External access: Use mobile IP (requires port forwarding)")
    print("🔧 Server running in debug mode - auto-restart on changes")
    print("="*60 + "\n")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=8080)

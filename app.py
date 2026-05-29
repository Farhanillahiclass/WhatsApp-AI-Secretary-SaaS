import os
import json
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///whatsapp_automation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# WhatsApp Cloud API Settings
app.config['WHATSAPP_API_TOKEN'] = os.environ.get('WHATSAPP_API_TOKEN')
app.config['WHATSAPP_PHONE_NUMBER_ID'] = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
app.config['WHATSAPP_BUSINESS_ACCOUNT_ID'] = os.environ.get('WHATSAPP_BUSINESS_ACCOUNT_ID')
app.config['WHATSAPP_API_VERSION'] = os.environ.get('WHATSAPP_API_VERSION', 'v18.0')
app.config['WHATSAPP_VERIFY_TOKEN'] = os.environ.get('WHATSAPP_VERIFY_TOKEN') or 'your-verify-token'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    rules = db.relationship('KeywordRule', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('MessageLog', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class KeywordRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    keyword = db.Column(db.String(200), nullable=False)
    response = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    match_type = db.Column(db.String(20), default='exact')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MessageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    from_number = db.Column(db.String(20), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    response_text = db.Column(db.Text)
    was_replied = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    total_rules = KeywordRule.query.filter_by(user_id=current_user.id).count()
    active_rules = KeywordRule.query.filter_by(user_id=current_user.id, is_active=True).count()
    total_messages = MessageLog.query.filter_by(user_id=current_user.id).count()
    replied_messages = MessageLog.query.filter_by(user_id=current_user.id, was_replied=True).count()
    
    recent_messages = MessageLog.query.filter_by(user_id=current_user.id)\
        .order_by(MessageLog.timestamp.desc())\
        .limit(10)\
        .all()
    
    return render_template('dashboard.html',
                         total_rules=total_rules,
                         active_rules=active_rules,
                         total_messages=total_messages,
                         replied_messages=replied_messages,
                         recent_messages=recent_messages)

@app.route('/rules')
@login_required
def rules():
    user_rules = KeywordRule.query.filter_by(user_id=current_user.id)\
        .order_by(KeywordRule.created_at.desc())\
        .all()
    return render_template('rules.html', rules=user_rules)

@app.route('/rules/add', methods=['POST'])
@login_required
def add_rule():
    keyword = request.form.get('keyword', '').strip().lower()
    response = request.form.get('response', '').strip()
    match_type = request.form.get('match_type', 'exact')
    
    if not keyword or not response:
        flash('Keyword and response are required', 'error')
        return redirect(url_for('rules'))
    
    rule = KeywordRule(
        user_id=current_user.id,
        keyword=keyword,
        response=response,
        match_type=match_type,
        is_active=True
    )
    db.session.add(rule)
    db.session.commit()
    
    flash('Rule added successfully!', 'success')
    return redirect(url_for('rules'))

@app.route('/rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_rule(rule_id):
    rule = KeywordRule.query.get_or_404(rule_id)
    if rule.user_id != current_user.id:
        abort(403)
    
    rule.is_active = not rule.is_active
    db.session.commit()
    
    status = 'activated' if rule.is_active else 'deactivated'
    flash(f'Rule {status}!', 'success')
    return redirect(url_for('rules'))

@app.route('/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_rule(rule_id):
    rule = KeywordRule.query.get_or_404(rule_id)
    if rule.user_id != current_user.id:
        abort(403)
    
    db.session.delete(rule)
    db.session.commit()
    
    flash('Rule deleted!', 'success')
    return redirect(url_for('rules'))

@app.route('/rules/<int:rule_id>/edit', methods=['POST'])
@login_required
def edit_rule(rule_id):
    rule = KeywordRule.query.get_or_404(rule_id)
    if rule.user_id != current_user.id:
        abort(403)
    
    rule.keyword = request.form.get('keyword', '').strip().lower()
    rule.response = request.form.get('response', '').strip()
    rule.match_type = request.form.get('match_type', 'exact')
    db.session.commit()
    
    flash('Rule updated!', 'success')
    return redirect(url_for('rules'))

def send_whatsapp_message(to_number, message_text, phone_number_id=None, api_token=None):
    if phone_number_id is None:
        phone_number_id = app.config['WHATSAPP_PHONE_NUMBER_ID']
    if api_token is None:
        api_token = app.config['WHATSAPP_API_TOKEN']
    
    url = f"https://graph.facebook.com/{app.config['WHATSAPP_API_VERSION']}/{phone_number_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {
            "body": message_text
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")
        return None

@app.route('/webhook', methods=['GET'])
def webhook_verify():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode == 'subscribe' and token == app.config['WHATSAPP_VERIFY_TOKEN']:
        print("Webhook verified successfully!")
        return challenge, 200
    else:
        abort(403)

@app.route('/webhook', methods=['POST'])
def webhook_receive():
    data = request.get_json()
    print(f"Received webhook: {json.dumps(data, indent=2)}")
    
    try:
        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        
        if 'messages' in value:
            message = value['messages'][0]
            from_number = message.get('from')
            message_type = message.get('type')
            
            if message_type == 'text':
                message_text = message.get('text', {}).get('body', '').strip()
                
                active_rules = KeywordRule.query.filter_by(is_active=True).all()
                
                for rule in active_rules:
                    should_respond = False
                    
                    if rule.match_type == 'exact':
                        should_respond = message_text.lower() == rule.keyword.lower()
                    elif rule.match_type == 'contains':
                        should_respond = rule.keyword.lower() in message_text.lower()
                    elif rule.match_type == 'starts_with':
                        should_respond = message_text.lower().startswith(rule.keyword.lower())
                    
                    if should_respond:
                        result = send_whatsapp_message(from_number, rule.response)
                        
                        log = MessageLog(
                            user_id=rule.user_id,
                            from_number=from_number,
                            message_text=message_text,
                            response_text=rule.response,
                            was_replied=True
                        )
                        db.session.add(log)
                        db.session.commit()
                        
                        break
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/stats')
@login_required
def api_stats():
    stats = {
        'total_rules': KeywordRule.query.filter_by(user_id=current_user.id).count(),
        'active_rules': KeywordRule.query.filter_by(user_id=current_user.id, is_active=True).count(),
        'total_messages': MessageLog.query.filter_by(user_id=current_user.id).count(),
        'replied_messages': MessageLog.query.filter_by(user_id=current_user.id, was_replied=True).count()
    }
    return jsonify(stats)

@app.route('/api/messages')
@login_required
def api_messages():
    messages = MessageLog.query.filter_by(user_id=current_user.id)\
        .order_by(MessageLog.timestamp.desc())\
        .limit(100)\
        .all()
    
    return jsonify([{
        'id': m.id,
        'from_number': m.from_number,
        'message_text': m.message_text,
        'response_text': m.response_text,
        'was_replied': m.was_replied,
        'timestamp': m.timestamp.isoformat()
    } for m in messages])

@app.route('/api/test-message', methods=['POST'])
@login_required
def test_message():
    data = request.get_json()
    to_number = data.get('to_number')
    message = data.get('message')
    
    if not to_number or not message:
        return jsonify({'error': 'Phone number and message required'}), 400
    
    result = send_whatsapp_message(to_number, message)
    
    if result:
        return jsonify({'success': True, 'result': result})
    else:
        return jsonify({'success': False, 'error': 'Failed to send message'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
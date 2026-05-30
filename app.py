import os
import json
import requests
import pytz
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///whatsapp_ai_secretary.db'
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

# ============== DATABASE MODELS ==============

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    timezone = db.Column(db.String(50), default='UTC')
    theme = db.Column(db.String(20), default='light')
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    # Relationships
    rules = db.relationship('KeywordRule', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('MessageLog', backref='user', lazy=True)
    contacts = db.relationship('Contact', backref='user', lazy=True, cascade='all, delete-orphan')
    templates = db.relationship('MessageTemplate', backref='user', lazy=True, cascade='all, delete-orphan')

class KeywordRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    keyword = db.Column(db.String(200), nullable=False)
    response = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    match_type = db.Column(db.String(20), default='exact')
    category = db.Column(db.String(50), default='general')
    usage_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MessageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    from_number = db.Column(db.String(20), nullable=False)
    contact_name = db.Column(db.String(100))
    message_text = db.Column(db.Text, nullable=False)
    response_text = db.Column(db.Text)
    was_replied = db.Column(db.Boolean, default=False)
    message_type = db.Column(db.String(20), default='text')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    tags = db.Column(db.String(200))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    last_contact = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MessageTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='general')
    variables = db.Column(db.String(200))
    usage_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BroadcastLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('message_template.id'))
    recipient_count = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    message_content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ============== WHATSAPP API FUNCTIONS ==============

def send_whatsapp_message(to_number, message_text, phone_number_id=None, api_token=None):
    if phone_number_id is None:
        phone_number_id = app.config['WHATSAPP_PHONE_NUMBER_ID']
    if api_token is None:
        api_token = app.config['WHATSAPP_API_TOKEN']
    
    if not phone_number_id or not api_token:
        print("WhatsApp API credentials not configured")
        return None
    
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
        "text": {"body": message_text}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")
        return None

def send_template_message(to_number, template_name, language_code="en", components=None):
    """Send a WhatsApp template message"""
    phone_number_id = app.config['WHATSAPP_PHONE_NUMBER_ID']
    api_token = app.config['WHATSAPP_API_TOKEN']
    
    if not phone_number_id or not api_token:
        return None
    
    url = f"https://graph.facebook.com/{app.config['WHATSAPP_API_VERSION']}/{phone_number_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code}
        }
    }
    
    if components:
        payload["template"]["components"] = components
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending template: {e}")
        return None

# ============== AUTHENTICATION ROUTES ==============

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
            session['theme'] = user.theme
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('theme', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# ============== MAIN DASHBOARD ==============

@app.route('/')
@login_required
def dashboard():
    # Calculate stats
    total_rules = KeywordRule.query.filter_by(user_id=current_user.id).count()
    active_rules = KeywordRule.query.filter_by(user_id=current_user.id, is_active=True).count()
    total_contacts = Contact.query.filter_by(user_id=current_user.id).count()
    total_messages = MessageLog.query.filter_by(user_id=current_user.id).count()
    
    # Today's stats
    today = datetime.utcnow().date()
    today_messages = MessageLog.query.filter(
        db.func.date(MessageLog.timestamp) == today,
        MessageLog.user_id == current_user.id
    ).count()
    
    # Recent activity
    recent_messages = MessageLog.query.filter_by(user_id=current_user.id)\
        .order_by(MessageLog.timestamp.desc())\
        .limit(5)\
        .all()
    
    # Top performing rules
    top_rules = KeywordRule.query.filter_by(user_id=current_user.id)\
        .order_by(KeywordRule.usage_count.desc())\
        .limit(5)\
        .all()
    
    # Weekly message chart data
    week_data = []
    for i in range(6, -1, -1):
        date = datetime.utcnow().date() - timedelta(days=i)
        count = MessageLog.query.filter(
            db.func.date(MessageLog.timestamp) == date,
            MessageLog.user_id == current_user.id
        ).count()
        week_data.append({
            'date': date.strftime('%a'),
            'count': count
        })
    
    return render_template('dashboard.html',
                         total_rules=total_rules,
                         active_rules=active_rules,
                         total_contacts=total_contacts,
                         total_messages=total_messages,
                         today_messages=today_messages,
                         recent_messages=recent_messages,
                         top_rules=top_rules,
                         week_data=week_data)

# ============== RULES MANAGEMENT ==============

@app.route('/rules')
@login_required
def rules():
    user_rules = KeywordRule.query.filter_by(user_id=current_user.id)\
        .order_by(KeywordRule.created_at.desc())\
        .all()
    categories = db.session.query(KeywordRule.category).filter_by(user_id=current_user.id).distinct().all()
    return render_template('rules.html', rules=user_rules, categories=[c[0] for c in categories])

@app.route('/rules/add', methods=['POST'])
@login_required
def add_rule():
    keyword = request.form.get('keyword', '').strip().lower()
    response = request.form.get('response', '').strip()
    match_type = request.form.get('match_type', 'exact')
    category = request.form.get('category', 'general')
    
    if not keyword or not response:
        flash('Keyword and response are required', 'error')
        return redirect(url_for('rules'))
    
    rule = KeywordRule(
        user_id=current_user.id,
        keyword=keyword,
        response=response,
        match_type=match_type,
        category=category,
        is_active=True
    )
    db.session.add(rule)
    db.session.commit()
    
    flash('Rule added successfully!', 'success')
    return redirect(url_for('rules'))

@app.route('/rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_rule(rule_id):
    rule = db.session.get(KeywordRule, rule_id)
    if not rule or rule.user_id != current_user.id:
        abort(403)
    
    rule.is_active = not rule.is_active
    db.session.commit()
    
    status = 'activated' if rule.is_active else 'deactivated'
    flash(f'Rule {status}!', 'success')
    return redirect(url_for('rules'))

@app.route('/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_rule(rule_id):
    rule = db.session.get(KeywordRule, rule_id)
    if not rule or rule.user_id != current_user.id:
        abort(403)
    
    db.session.delete(rule)
    db.session.commit()
    
    flash('Rule deleted!', 'success')
    return redirect(url_for('rules'))

@app.route('/rules/<int:rule_id>/edit', methods=['POST'])
@login_required
def edit_rule(rule_id):
    rule = db.session.get(KeywordRule, rule_id)
    if not rule or rule.user_id != current_user.id:
        abort(403)
    
    rule.keyword = request.form.get('keyword', '').strip().lower()
    rule.response = request.form.get('response', '').strip()
    rule.match_type = request.form.get('match_type', 'exact')
    rule.category = request.form.get('category', 'general')
    db.session.commit()
    
    flash('Rule updated!', 'success')
    return redirect(url_for('rules'))

# ============== CONTACTS MANAGEMENT ==============

@app.route('/contacts')
@login_required
def contacts():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = Contact.query.filter_by(user_id=current_user.id)
    
    if search:
        query = query.filter(
            db.or_(
                Contact.name.ilike(f'%{search}%'),
                Contact.phone_number.ilike(f'%{search}%'),
                Contact.tags.ilike(f'%{search}%')
            )
        )
    
    contacts = query.order_by(Contact.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('contacts.html', contacts=contacts, search=search)

@app.route('/contacts/add', methods=['POST'])
@login_required
def add_contact():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    tags = request.form.get('tags', '').strip()
    notes = request.form.get('notes', '').strip()
    
    if not phone:
        flash('Phone number is required', 'error')
        return redirect(url_for('contacts'))
    
    contact = Contact(
        user_id=current_user.id,
        name=name,
        phone_number=phone,
        email=email,
        tags=tags,
        notes=notes
    )
    db.session.add(contact)
    db.session.commit()
    
    flash('Contact added successfully!', 'success')
    return redirect(url_for('contacts'))

@app.route('/contacts/<int:contact_id>/delete', methods=['POST'])
@login_required
def delete_contact(contact_id):
    contact = db.session.get(Contact, contact_id)
    if not contact or contact.user_id != current_user.id:
        abort(403)
    
    db.session.delete(contact)
    db.session.commit()
    
    flash('Contact deleted!', 'success')
    return redirect(url_for('contacts'))

# ============== BROADCAST MESSAGING ==============

@app.route('/broadcast')
@login_required
def broadcast():
    templates = MessageTemplate.query.filter_by(user_id=current_user.id).all()
    contacts = Contact.query.filter_by(user_id=current_user.id, is_active=True).all()
    return render_template('broadcast.html', templates=templates, contacts=contacts)

@app.route('/broadcast/send', methods=['POST'])
@login_required
def send_broadcast():
    message = request.form.get('message', '').strip()
    template_id = request.form.get('template_id')
    contact_ids = request.form.getlist('contacts')
    
    if not message or not contact_ids:
        flash('Message and recipients are required', 'error')
        return redirect(url_for('broadcast'))
    
    success_count = 0
    failed_count = 0
    
    for contact_id in contact_ids:
        contact = db.session.get(Contact, contact_id)
        if contact and contact.user_id == current_user.id:
            result = send_whatsapp_message(contact.phone_number, message)
            if result:
                success_count += 1
            else:
                failed_count += 1
    
    # Log broadcast
    log = BroadcastLog(
        user_id=current_user.id,
        message_content=message,
        recipient_count=len(contact_ids),
        success_count=success_count,
        failed_count=failed_count
    )
    db.session.add(log)
    db.session.commit()
    
    flash(f'Broadcast sent! {success_count} successful, {failed_count} failed.', 'success')
    return redirect(url_for('broadcast'))

# ============== MESSAGE TEMPLATES ==============

@app.route('/templates')
@login_required
def templates():
    user_templates = MessageTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(MessageTemplate.created_at.desc())\
        .all()
    return render_template('templates.html', templates=user_templates)

@app.route('/templates/add', methods=['POST'])
@login_required
def add_template():
    name = request.form.get('name', '').strip()
    content = request.form.get('content', '').strip()
    category = request.form.get('category', 'general')
    variables = request.form.get('variables', '').strip()
    
    if not name or not content:
        flash('Name and content are required', 'error')
        return redirect(url_for('templates'))
    
    template = MessageTemplate(
        user_id=current_user.id,
        name=name,
        content=content,
        category=category,
        variables=variables
    )
    db.session.add(template)
    db.session.commit()
    
    flash('Template saved!', 'success')
    return redirect(url_for('templates'))

@app.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_template(template_id):
    template = db.session.get(MessageTemplate, template_id)
    if not template or template.user_id != current_user.id:
        abort(403)
    
    db.session.delete(template)
    db.session.commit()
    
    flash('Template deleted!', 'success')
    return redirect(url_for('templates'))

# ============== ANALYTICS ==============

@app.route('/analytics')
@login_required
def analytics():
    # Time range
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)
    
    # Message stats
    messages = MessageLog.query.filter(
        MessageLog.user_id == current_user.id,
        MessageLog.timestamp >= since
    ).all()
    
    total_sent = len(messages)
    auto_replied = sum(1 for m in messages if m.was_replied)
    reply_rate = (auto_replied / total_sent * 100) if total_sent > 0 else 0
    
    # Daily breakdown
    daily_stats = {}
    for msg in messages:
        day = msg.timestamp.strftime('%Y-%m-%d')
        if day not in daily_stats:
            daily_stats[day] = {'total': 0, 'replied': 0}
        daily_stats[day]['total'] += 1
        if msg.was_replied:
            daily_stats[day]['replied'] += 1
    
    # Top keywords triggered
    rules_usage = KeywordRule.query.filter_by(user_id=current_user.id)\
        .order_by(KeywordRule.usage_count.desc())\
        .limit(10)\
        .all()
    
    # Recent broadcasts
    broadcasts = BroadcastLog.query.filter_by(user_id=current_user.id)\
        .order_by(BroadcastLog.timestamp.desc())\
        .limit(10)\
        .all()
    
    return render_template('analytics.html',
                         days=days,
                         total_sent=total_sent,
                         auto_replied=auto_replied,
                         reply_rate=reply_rate,
                         daily_stats=daily_stats,
                         rules_usage=rules_usage,
                         broadcasts=broadcasts)

# ============== SETTINGS ==============

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.timezone = request.form.get('timezone', 'UTC')
        current_user.theme = request.form.get('theme', 'light')
        db.session.commit()
        session['theme'] = current_user.theme
        flash('Settings updated!', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html')

# ============== WEBHOOK HANDLER ==============

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
            
            # Get contact name if available
            contact_name = None
            if 'contacts' in value:
                contact_name = value['contacts'][0].get('profile', {}).get('name')
            
            if message_type == 'text':
                message_text = message.get('text', {}).get('body', '').strip()
                
                # Find matching rules
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
                        # Send reply
                        result = send_whatsapp_message(from_number, rule.response)
                        
                        # Update rule usage
                        rule.usage_count += 1
                        
                        # Log message
                        log = MessageLog(
                            user_id=rule.user_id,
                            from_number=from_number,
                            contact_name=contact_name,
                            message_text=message_text,
                            response_text=rule.response,
                            was_replied=True
                        )
                        db.session.add(log)
                        db.session.commit()
                        
                        # Update contact last_contact
                        contact = Contact.query.filter_by(
                            user_id=rule.user_id,
                            phone_number=from_number
                        ).first()
                        if contact:
                            contact.last_contact = datetime.utcnow()
                            db.session.commit()
                        
                        break
                else:
                    # No rule matched - log anyway
                    # Find user by phone number mapping (simplified)
                    pass
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200

# ============== API ENDPOINTS ==============

@app.route('/api/stats')
@login_required
def api_stats():
    stats = {
        'total_rules': KeywordRule.query.filter_by(user_id=current_user.id).count(),
        'active_rules': KeywordRule.query.filter_by(user_id=current_user.id, is_active=True).count(),
        'total_contacts': Contact.query.filter_by(user_id=current_user.id).count(),
        'total_messages': MessageLog.query.filter_by(user_id=current_user.id).count(),
        'today_messages': MessageLog.query.filter(
            db.func.date(MessageLog.timestamp) == datetime.utcnow().date(),
            MessageLog.user_id == current_user.id
        ).count()
    }
    return jsonify(stats)

@app.route('/api/contacts/search')
@login_required
def search_contacts():
    query = request.args.get('q', '')
    contacts = Contact.query.filter(
        Contact.user_id == current_user.id,
        db.or_(
            Contact.name.ilike(f'%{query}%'),
            Contact.phone_number.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone_number
    } for c in contacts])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
import os
import re
import json
import time
import secrets
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import timedelta
import sqlite3
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
from database import get_db, hash_password, verify_password, init_db
app = Flask(__name__)

# Persistent secure secret key for cryptographic session integrity
SECRET_KEY_FILE = os.path.join(os.path.dirname(__file__), '.secret_key')
if os.path.exists(SECRET_KEY_FILE):
    try:
        with open(SECRET_KEY_FILE, 'r', encoding='utf-8') as f:
            app.secret_key = f.read().strip()
    except Exception:
        app.secret_key = secrets.token_hex(32)
else:
    generated_key = secrets.token_hex(32)
    try:
        with open(SECRET_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(generated_key)
    except Exception:
        pass
    app.secret_key = generated_key

# Strict Session & Cookie Hardening
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True when HTTPS is enabled
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25 MB payload limit (supports up to 5 high-res vehicle photos)

# Configuration for uploads
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'heic', 'heif', 'jfif', 'avif'}
ADMIN_EMAILS = {'admin@biglautos.com', 'receptionist@biglautos.com', 'bonsum114@gmail.com', 'bonsum1141@gmail.com', 'michaelbonsu2000@icloud.com'}

def is_admin_email(email):
    if not email:
        return False
    e = str(email).lower().strip()
    if e in ADMIN_EMAILS:
        return True
    if e.startswith('bonsum114') or e.startswith('michaelbonsu'):
        return True
    return False

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_car_images(images_raw, default_cover=None):
    """
    Parses the images column into a clean list of up to 5 image URLs.
    Supports JSON lists, newline/comma-separated strings, or single URL fallbacks.
    """
    raw_list = []
    if images_raw:
        if isinstance(images_raw, list):
            raw_list = images_raw
        elif isinstance(images_raw, str):
            trimmed = images_raw.strip()
            if trimmed.startswith('[') and trimmed.endswith(']'):
                try:
                    parsed = json.loads(trimmed)
                    if isinstance(parsed, list):
                        raw_list = parsed
                    else:
                        raw_list = [trimmed]
                except Exception:
                    raw_list = [trimmed]
            else:
                raw_list = [trimmed]

    imgs = []
    for item in raw_list:
        if not item:
            continue
        item_str = str(item).strip()
        if not item_str:
            continue
        # Check if item itself is a JSON array string
        if item_str.startswith('[') and item_str.endswith(']'):
            try:
                sub_parsed = json.loads(item_str)
                if isinstance(sub_parsed, list):
                    for sub in sub_parsed:
                        if sub and str(sub).strip():
                            imgs.append(str(sub).strip())
                    continue
            except Exception:
                pass
        # Check for newline splitting
        if '\n' in item_str:
            for line in item_str.split('\n'):
                line = line.strip()
                if line:
                    imgs.append(line)
        # Check for comma splitting
        elif ',' in item_str and not ('http' in item_str and '?' in item_str and '&' in item_str):
            for part in item_str.split(','):
                part = part.strip()
                if part:
                    imgs.append(part)
        else:
            imgs.append(item_str)

    if not imgs and default_cover:
        imgs = [default_cover.strip()]

    # Deduplicate while preserving order, cap at 5
    seen = set()
    deduped = []
    for u in imgs:
        u_clean = u.strip().strip('"').strip("'")
        if u_clean and u_clean not in seen:
            seen.add(u_clean)
            deduped.append(u_clean)
        if len(deduped) >= 5:
            break

    if not deduped:
        deduped = ["https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80"]

    return deduped

# Cache static assets aggressively for faster mobile page loads, but never cache HTML.
# CSS/JS URLs are versioned (?v=3.8) so they are effectively immutable.
@app.after_request
def add_cache_control_headers(response):
    ctype = response.headers.get('Content-Type', '')
    is_dev = app.debug or app.config.get('TESTING')

    if 'text/html' in ctype:
        # HTML must never be cached (auth state changes frequently)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif any(t in ctype for t in ['text/css', 'javascript', 'image/']):
        if is_dev:
            response.headers['Cache-Control'] = 'no-cache, must-revalidate, max-age=0'
        else:
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

# In-memory Rate Limiting to prevent brute-force attacks and bot flooding
LOGIN_ATTEMPTS = {}
REGISTER_ATTEMPTS = {}

def is_rate_limited(tracker_dict, key, max_attempts=5, window_seconds=900):
    now = time.time()
    cutoff = now - window_seconds
    attempts = [t for t in tracker_dict.get(key, []) if t > cutoff]
    tracker_dict[key] = attempts
    if len(attempts) >= max_attempts:
        return True, int(attempts[0] + window_seconds - now)
    return False, 0

def record_attempt(tracker_dict, key):
    now = time.time()
    if key not in tracker_dict:
        tracker_dict[key] = []
    tracker_dict[key].append(now)

def clear_attempts(tracker_dict, key):
    if key in tracker_dict:
        del tracker_dict[key]

# HTTP Security Headers
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https://images.unsplash.com https://*.unsplash.com https://*.svg https://*.googleusercontent.com; "
        "connect-src 'self' https://accounts.google.com; "
        "frame-src 'self' https://accounts.google.com; "
        "frame-ancestors 'self';"
    )
    return response

# --- Automated Welcome Email Utility ---
def _send_welcome_email_worker(user_name, user_email):
    """Worker executed in background daemon thread to deliver welcome email without blocking user."""
    if not user_email or '@' not in user_email or user_email.endswith('@example.com'):
        return

    smtp_host = os.environ.get('SMTP_HOST', 'localhost')
    smtp_port = int(os.environ.get('SMTP_PORT', '25'))
    smtp_user = os.environ.get('SMTP_USER', 'support@big-lautos.com')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    smtp_use_tls = os.environ.get('SMTP_USE_TLS', 'false').lower() in ('true', '1', 'yes')
    sender_email = os.environ.get('SMTP_FROM', 'BIG-L Autos <support@big-lautos.com>')

    subject = "Welcome to BIG-L Autos – Premium Showroom & Direct Deals"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #030d07; color: #f1f5f9; margin: 0; padding: 24px; }}
    .email-card {{ max-width: 600px; margin: 0 auto; background: #081a10; border: 1px solid rgba(0, 242, 150, 0.25); border-radius: 12px; overflow: hidden; }}
    .email-header {{ background: linear-gradient(135deg, #022c16 0%, #064e2b 100%); padding: 32px 28px; text-align: center; border-bottom: 1px solid rgba(0, 242, 150, 0.2); }}
    .email-logo {{ font-size: 24px; font-weight: 900; letter-spacing: 2px; color: #00f296; text-decoration: none; }}
    .email-body {{ padding: 32px 28px; line-height: 1.6; font-size: 15px; color: #cbd5e1; }}
    .email-title {{ color: #ffffff; font-size: 20px; font-weight: 800; margin-top: 0; margin-bottom: 12px; }}
    .action-box {{ background: rgba(0, 242, 150, 0.08); border: 1px solid rgba(0, 242, 150, 0.2); border-radius: 8px; padding: 18px 20px; margin: 24px 0; }}
    .btn {{ display: inline-block; background: #00f296; color: #000000; font-weight: 800; font-size: 14px; padding: 12px 28px; border-radius: 6px; text-decoration: none; margin-top: 10px; }}
    .feature-list {{ margin: 18px 0; padding-left: 20px; }}
    .feature-list li {{ margin-bottom: 10px; }}
    .email-footer {{ padding: 20px 28px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid rgba(255,255,255,0.06); }}
  </style>
</head>
<body>
  <div class="email-card">
    <div class="email-header">
      <div class="email-logo">BIG-L AUTOS</div>
      <div style="font-size: 12px; color: #94a3b8; margin-top: 6px; letter-spacing: 1px;">PREMIUM AUTOMOTIVE SHOWROOM • SOMANYA-ROUNDABOUT</div>
    </div>
    <div class="email-body">
      <h2 class="email-title">Welcome to BIG-L Autos, {user_name}!</h2>
      <p>Your account has been created. You now have full access to our live inventory, direct dealer chat, vehicle swap evaluations, and customer portal.</p>
      
      <div class="action-box">
        <strong style="color: #00f296; font-size: 16px;">What you can do right now:</strong>
        <ul class="feature-list">
          <li><strong>Browse Showroom:</strong> Discover foreign-used luxury and daily drivers with up to 5 photos.</li>
          <li><strong>Direct Chat with Larry:</strong> Open a real-time negotiation chat or call Larry directly at <a href="tel:0549255121" style="color:#00f296; text-decoration:none;">0549255121</a>.</li>
          <li><strong>Car Trade-Ins &amp; Swaps:</strong> Submit your vehicle details for fair market valuation.</li>
          <li><strong>Sell Your Car (GH₵ 50/Month):</strong> List your own cars directly to verified buyers in Ghana.</li>
        </ul>
        <div style="text-align: center; margin-top: 20px;">
          <a href="https://big-lautos.com" class="btn">Explore Live Showroom</a>
        </div>
      </div>

      <p style="font-size: 13.5px; color: #94a3b8;">
        Need assistance or wish to arrange an on-site inspection? Call or visit Larry at the Somanya-Roundabout showroom or phone <strong>0549255121</strong>.
      </p>
    </div>
    <div class="email-footer">
      &copy; 2026 BIG-L Autos. Somanya-Roundabout, Eastern Region, Ghana.<br>
      This email was sent to {user_email} because you registered an account on big-lautos.com.
    </div>
  </div>
</body>
</html>"""

    plain_content = f"""Welcome to BIG-L Autos, {user_name}!

Your account has been created successfully.

What you can do on BIG-L Autos:
- Browse showroom cars: https://big-lautos.com
- Chat or negotiate directly with Larry (Head Dealer) on 0549255121
- Submit car trade-ins / swap evaluations
- Sell your cars in the showroom for GH₵ 50 / month

Showroom Location: Somanya-Roundabout, Eastern Region, Ghana
Direct Phone: 0549255121
"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = user_email
    msg.attach(MIMEText(plain_content, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        if smtp_host == 'localhost' and smtp_port == 25 and not smtp_pass:
            server = smtplib.SMTP('localhost', 25, timeout=5)
            server.sendmail(sender_email, [user_email], msg.as_string())
            server.quit()
        else:
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                if smtp_use_tls:
                    server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(sender_email, [user_email], msg.as_string())
            server.quit()
        print(f"[MAIL] Welcome email sent to {user_email}")
    except Exception as e:
        print(f"[MAIL NOTE] Background welcome email to {user_email} skipped: {e}")

def send_welcome_email(user_name, user_email):
    """Dispatches welcome email asynchronously in a background thread."""
    t = threading.Thread(target=_send_welcome_email_worker, args=(user_name, user_email), daemon=True)
    t.start()

# Ensure DB initialized
init_db()

# --- Helper Methods ---
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, email, phone, role, can_post, seller_status, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    db.close()
    if row:
        return dict(row)
    return None

def is_admin_or_receptionist(user):
    """Admin and Dealership desk (Larry / Head Dealer & Admin)."""
    if not user:
        return False
    email = str(user.get('email') or '').lower().strip()
    if is_admin_email(email):
        return True
    return user.get('role') in ('admin', 'receptionist')

@app.route('/sw.js')
def service_worker():
    response = send_from_directory('static', 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

@app.route('/manifest.json')
def web_manifest():
    response = send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')
    response.headers['Cache-Control'] = 'no-cache'
    return response

# --- Page Routes ---
@app.route('/')
def home():
    user = get_current_user()
    return render_template('index.html', user=user)

@app.route('/login')
def login_page():
    user = get_current_user()
    if user:
        return redirect(url_for('admin_dashboard') if is_admin_or_receptionist(user) else url_for('customer_dashboard'))
    car_id = request.args.get('car_id')
    inquiry_car = None
    if car_id:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM cars WHERE id = ?", (car_id,))
        row = cursor.fetchone()
        db.close()
        if row:
            inquiry_car = dict(row)
    return render_template('auth.html', mode='login', user=None, inquiry_car=inquiry_car)

@app.route('/register')
def register_page():
    user = get_current_user()
    if user:
        return redirect(url_for('admin_dashboard') if is_admin_or_receptionist(user) else url_for('customer_dashboard'))
    car_id = request.args.get('car_id')
    inquiry_car = None
    if car_id:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM cars WHERE id = ?", (car_id,))
        row = cursor.fetchone()
        db.close()
        if row:
            inquiry_car = dict(row)
    return render_template('auth.html', mode='register', user=None, inquiry_car=inquiry_car)

@app.route('/customer')
def customer_dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for('home', open_auth='login'))
    return render_template('customer.html', user=user)

@app.route('/receptionist')
@app.route('/admin')
def admin_dashboard():
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return redirect(url_for('home', open_auth='admin_login'))
    return render_template('admin.html', user=user)

@app.route('/privacy')
def privacy_page():
    user = get_current_user()
    return render_template('privacy.html', user=user)

@app.route('/terms')
def terms_page():
    user = get_current_user()
    return render_template('terms.html', user=user)

# --- Authentication APIs ---
@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = get_current_user()
    return jsonify({'authenticated': user is not None, 'user': user})

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    client_ip = request.remote_addr or 'unknown'
    limited, retry_in = is_rate_limited(REGISTER_ATTEMPTS, client_ip, max_attempts=10, window_seconds=900)
    if limited:
        return jsonify({'error': f'Too many registration attempts. Please try again in {retry_in // 60 + 1} minutes.'}), 429

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')

    if not name or not email or not password:
        return jsonify({'error': 'Name, email, and password are required'}), 400

    # Validate email syntax
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
        return jsonify({'error': 'Please provide a valid email address'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters long'}), 400

    record_attempt(REGISTER_ATTEMPTS, client_ip)

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        db.close()
        return jsonify({'error': 'An account with this email already exists'}), 400

    is_owner_admin = is_admin_email(email)
    role = 'admin' if is_owner_admin else 'customer'
    can_post = 1 if is_owner_admin else 0
    seller_status = 'approved' if is_owner_admin else 'none'

    pass_hash = hash_password(password)
    cursor.execute(
        "INSERT INTO users (name, email, phone, password_hash, role, can_post, seller_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, email, phone, pass_hash, role, can_post, seller_status)
    )
    db.commit()
    user_id = cursor.lastrowid
    db.close()

    session.permanent = True
    session['user_id'] = user_id
    session['role'] = role
    session['name'] = name

    # Dispatch welcome email asynchronously
    send_welcome_email(name, email)

    return jsonify({
        'success': True,
        'message': 'Account created successfully! Welcome to BIG L Autos.',
        'user': {'id': user_id, 'name': name, 'email': email, 'phone': phone, 'role': 'customer'}
    })

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    client_ip = request.remote_addr or 'unknown'
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    # Admin and Dealership desk are identical accounts for Larry
    if email in ('receptionist@biglautos.com', 'admin@biglautos.com'):
        email = 'admin@biglautos.com' 

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    # Brute force protection: maximum 5 failed attempts per IP + email per 15 minutes
    rate_key = f"{client_ip}:{email}"
    limited, retry_in = is_rate_limited(LOGIN_ATTEMPTS, rate_key, max_attempts=5, window_seconds=900)
    if limited:
        return jsonify({'error': f'Too many failed attempts. Account temporarily locked for {retry_in // 60 + 1} minutes.'}), 429

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, email, phone, password_hash, role FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()

    if not row:
        db.close()
        record_attempt(LOGIN_ATTEMPTS, rate_key)
        return jsonify({'error': 'Invalid email or password'}), 401

    is_valid, needs_rehash = verify_password(row['password_hash'], password)
    if not is_valid:
        db.close()
        record_attempt(LOGIN_ATTEMPTS, rate_key)
        return jsonify({'error': 'Invalid email or password'}), 401

    # Successful login: reset failed login attempts
    clear_attempts(LOGIN_ATTEMPTS, rate_key)

    # Automatic migration to salted PBKDF2 if user had legacy SHA-256
    if needs_rehash:
        new_hash = hash_password(password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row['id']))
        db.commit()

    if is_admin_email(email):
        cursor.execute("UPDATE users SET role = 'admin', can_post = 1, seller_status = 'approved' WHERE id = ?", (row['id'],))
        db.commit()
        user_role = 'admin'
    else:
        user_role = row['role']

    db.close()

    session.permanent = True
    session['user_id'] = row['id']
    session['role'] = user_role
    session['name'] = row['name']

    return jsonify({
        'success': True,
        'message': f'Welcome back, {row["name"]}!',
        'user': {
            'id': row['id'],
            'name': row['name'],
            'email': row['email'],
            'phone': row['phone'],
            'role': row['role']
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/auth/social-login', methods=['POST'])
def auth_social_login():
    """
    1-Click Social Sign-in (Google / Apple / etc.).
    Authenticates existing user immediately without filling in anything again,
    or auto-creates a new user account with default strong random password and sends welcome email!
    """
    data = request.get_json() or {}
    provider = data.get('provider', 'google').lower()
    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()

    if not email:
        return jsonify({'error': 'Email is required for social authentication'}), 400

    # Validate email syntax
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
        return jsonify({'error': 'Please provide a valid email address'}), 400

    if not name:
        name = email.split('@')[0].replace('.', ' ').capitalize()

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, email, phone, role, can_post, seller_status FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    is_owner_admin = is_admin_email(email)
    is_new_user = False
    if not user:
        # Create user account automatically
        is_new_user = True
        random_pass = secrets.token_urlsafe(16)
        pass_hash = hash_password(random_pass)
        phone = data.get('phone', '').strip()
        role = 'admin' if is_owner_admin else 'customer'
        can_post = 1 if is_owner_admin else 0
        seller_status = 'approved' if is_owner_admin else 'none'
        cursor.execute(
            "INSERT INTO users (name, email, phone, password_hash, role, can_post, seller_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, email, phone, pass_hash, role, can_post, seller_status)
        )
        db.commit()
        user_id = cursor.lastrowid
        cursor.execute("SELECT id, name, email, phone, role, can_post, seller_status FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()

        # Send welcome email asynchronously
        send_welcome_email(name, email)
    else:
        if is_owner_admin and (user['role'] != 'admin' or not user['can_post']):
            cursor.execute("UPDATE users SET role = 'admin', can_post = 1, seller_status = 'approved' WHERE id = ?", (user['id'],))
            db.commit()
            cursor.execute("SELECT id, name, email, phone, role, can_post, seller_status FROM users WHERE id = ?", (user['id'],))
            user = cursor.fetchone()

    user_dict = dict(user)
    db.close()

    session.permanent = True
    session['user_id'] = user_dict['id']
    session['role'] = user_dict['role']
    session['name'] = user_dict['name']

    return jsonify({
        'success': True,
        'is_new_user': is_new_user,
        'message': f"Welcome {'back ' if not is_new_user else ''}to BIG-L Autos, {user_dict['name']}!",
        'user': user_dict,
        'redirect': '/admin' if is_admin_or_receptionist(user_dict) else '/customer'
    })

# --- Real-Time Social OAuth Popup Windows ---
@app.route('/auth/google')
def google_oauth_popup():
    """Authentic Google Sign-In Window with instant account chooser."""
    google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
    if google_client_id:
        redirect_uri = url_for('auth_social_login', _external=True)
        return redirect(
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={google_client_id}&response_type=code&"
            f"scope=openid%20email%20profile&redirect_uri={urllib.parse.quote(redirect_uri)}&prompt=select_account"
        )
    return render_template('google_oauth.html')

@app.route('/auth/apple')
def apple_oauth_popup():
    """Authentic Apple ID Sign-In Window."""
    return render_template('apple_oauth.html')

# --- Profile & Password Management APIs ---
@app.route('/api/user/profile', methods=['GET', 'POST', 'PUT'])
def user_profile_endpoint():
    """Get or update current authenticated user's profile."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    if request.method == 'GET':
        return jsonify({'success': True, 'user': current_user})

    data = request.get_json() or {}
    new_name = data.get('name', '').strip()
    new_phone = data.get('phone', '').strip()
    new_email = data.get('email', '').strip().lower()

    if not new_name:
        return jsonify({'error': 'Name is required'}), 400

    db = get_db()
    cursor = db.cursor()

    # If email changed, verify email format and ensure no collision
    if new_email and new_email != current_user['email'].lower():
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', new_email):
            db.close()
            return jsonify({'error': 'Please provide a valid email address'}), 400
        cursor.execute("SELECT id FROM users WHERE email = ? AND id != ?", (new_email, current_user['id']))
        if cursor.fetchone():
            db.close()
            return jsonify({'error': 'That email address is already in use by another account'}), 400
        email_to_set = new_email
    else:
        email_to_set = current_user['email']

    phone_to_set = new_phone if new_phone else (current_user.get('phone') or '')

    cursor.execute(
        "UPDATE users SET name = ?, phone = ?, email = ? WHERE id = ?",
        (new_name, phone_to_set, email_to_set, current_user['id'])
    )
    db.commit()

    # Update session name if changed
    session['name'] = new_name

    cursor.execute("SELECT id, name, email, phone, role, can_post, seller_status FROM users WHERE id = ?", (current_user['id'],))
    updated_user = dict(cursor.fetchone())
    db.close()

    return jsonify({
        'success': True,
        'message': 'Profile updated successfully!',
        'user': updated_user
    })

@app.route('/api/user/change-password', methods=['POST'])
def user_change_password_endpoint():
    """Change current authenticated user's password."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json() or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not new_password or len(new_password) < 6:
        return jsonify({'error': 'New password must be at least 6 characters long'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (current_user['id'],))
    row = cursor.fetchone()
    if not row:
        db.close()
        return jsonify({'error': 'User not found'}), 404

    current_hash = row['password_hash']
    # If the user has a password set and is not empty, require verifying current password
    if current_hash and current_user.get('role') != 'admin_override':
        is_valid, _ = verify_password(current_hash, current_password)
        if not is_valid:
            db.close()
            return jsonify({'error': 'Current password is incorrect'}), 400

    new_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, current_user['id']))
    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'message': 'Password updated successfully!'
    })

# --- Cars Inventory APIs ---
@app.route('/api/cars', methods=['GET'])
def get_cars():
    search = request.args.get('search', '').strip()
    make = request.args.get('make', '').strip()
    body_type = request.args.get('body_type', '').strip()
    max_price = request.args.get('max_price', type=float)
    condition = request.args.get('condition', '').strip()
    status = request.args.get('status', '').strip()

    query = '''
    SELECT cars.*,
           users.name as seller_name,
           users.role as seller_role,
           users.phone as seller_phone
    FROM cars
    LEFT JOIN users ON cars.seller_id = users.id
    WHERE 1=1
    '''
    params = []

    if search:
        query += " AND (cars.title LIKE ? OR cars.make LIKE ? OR cars.model LIKE ? OR cars.description LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])

    if make:
        query += " AND cars.make = ?"
        params.append(make)

    if body_type:
        query += " AND cars.body_type = ?"
        params.append(body_type)

    if condition:
        query += " AND cars.condition = ?"
        params.append(condition)

    if status:
        query += " AND cars.status = ?"
        params.append(status)

    if max_price:
        query += " AND cars.price <= ?"
        params.append(max_price)

    query += " ORDER BY cars.id DESC"

    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    db.close()

    cars = []
    for r in rows:
        c = dict(r)
        is_user_seller = bool(c.get('seller_id') and c.get('seller_role') != 'admin')
        c['is_user_seller'] = is_user_seller
        c['seller_display_name'] = c.get('seller_name') if is_user_seller else "Larry (Head Dealer)"
        imgs = parse_car_images(c.get('images'), c.get('image_url'))
        c['images'] = imgs
        c['image_url'] = imgs[0] if imgs else (c.get('image_url') or '')
        c['image_count'] = len(imgs)
        cars.append(c)

    return jsonify({'cars': cars, 'total': len(cars)})

@app.route('/api/cars/<int:car_id>', methods=['GET'])
def get_car(car_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
    SELECT cars.*,
           users.name as seller_name,
           users.role as seller_role,
           users.phone as seller_phone
    FROM cars
    LEFT JOIN users ON cars.seller_id = users.id
    WHERE cars.id = ?
    ''', (car_id,))
    row = cursor.fetchone()
    db.close()

    if not row:
        return jsonify({'error': 'Car not found'}), 404

    car = dict(row)
    is_user_seller = bool(car.get('seller_id') and car.get('seller_role') != 'admin')
    car['is_user_seller'] = is_user_seller
    car['seller_display_name'] = car.get('seller_name') if is_user_seller else "Larry (Head Dealer)"
    imgs = parse_car_images(car.get('images'), car.get('image_url'))
    car['images'] = imgs
    car['image_url'] = imgs[0] if imgs else (car.get('image_url') or '')
    car['image_count'] = len(imgs)
    return jsonify({'car': car})

@app.route('/api/cars', methods=['POST'])
def add_car():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Please login to post cars'}), 401

    can_publish = is_admin_or_receptionist(user) or bool(user.get('can_post'))
    if not can_publish:
        return jsonify({'error': 'Your profile has not yet been approved for posting. Please request seller access from the receptionist.'}), 403

    collected_images = []

    # Support multipart/form-data and form-urlencoded for file/field uploads (supports up to 5 photos)
    if (request.content_type and ('multipart/form-data' in request.content_type or 'application/x-www-form-urlencoded' in request.content_type)) or request.form or request.files:
        title = (request.form.get('title') or '').strip()
        make = (request.form.get('make') or '').strip()
        model = (request.form.get('model') or '').strip()

        year_raw = request.form.get('year')
        try:
            year = int(str(year_raw).replace(',', '').strip()) if year_raw else 2024
        except (ValueError, TypeError):
            year = 2024

        price_raw = request.form.get('price')
        price = None
        if price_raw is not None:
            clean_price = str(price_raw).replace(',', '').replace('GH₵', '').replace('GHC', '').replace('ghc', '').strip()
            try:
                price = float(clean_price)
            except (ValueError, TypeError):
                price = None

        mileage_raw = request.form.get('mileage', 0)
        try:
            mileage = int(str(mileage_raw).replace(',', '').strip()) if mileage_raw else 0
        except (ValueError, TypeError):
            mileage = 0

        transmission = request.form.get('transmission', 'Automatic') or 'Automatic'
        fuel_type = request.form.get('fuel_type', 'Petrol') or 'Petrol'
        body_type = request.form.get('body_type', 'Sedan') or 'Sedan'
        color = request.form.get('color', 'Black') or 'Black'
        condition = request.form.get('condition', 'Foreign Used') or 'Foreign Used'
        status = request.form.get('status', 'Available') or 'Available'
        description = request.form.get('description', '') or ''
        features = request.form.get('features', '') or ''

        # 1. Process uploaded image files (accepts multiple files up to 5)
        files = request.files.getlist('image_files')
        if not files:
            files = request.files.getlist('image_file')
        for key in ['image_file_1', 'image_file_2', 'image_file_3', 'image_file_4', 'image_file_5']:
            if key in request.files:
                files.append(request.files[key])

        for f in files:
            if f and f.filename and allowed_file(f.filename):
                try:
                    safe_name = secure_filename(f.filename)
                    ext = safe_name.rsplit('.', 1)[1].lower() if '.' in safe_name else 'jpg'
                    filename = f"car_{int(time.time())}_{secrets.token_hex(4)}.{ext}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    f.save(filepath)
                    collected_images.append(f"/static/uploads/{filename}")
                    if len(collected_images) >= 5:
                        break
                except Exception as save_err:
                    print(f"Error saving car photo: {save_err}")

        # 2. Process image URLs if fewer than 5 files uploaded
        if len(collected_images) < 5:
            urls_raw = request.form.getlist('image_urls') or request.form.get('image_urls') or request.form.get('image_url')
            if urls_raw:
                parsed_urls = parse_car_images(urls_raw, None)
                for u in parsed_urls:
                    if u and u not in collected_images:
                        collected_images.append(u)
                        if len(collected_images) >= 5:
                            break
    else:
        data = request.get_json(silent=True) or {}
        title = str(data.get('title') or '').strip()
        make = str(data.get('make') or '').strip()
        model = str(data.get('model') or '').strip()
        try:
            year = int(str(data.get('year') or 2024).replace(',', '').strip())
        except (ValueError, TypeError):
            year = 2024
        price_raw = data.get('price')
        price = None
        if price_raw is not None:
            clean_price = str(price_raw).replace(',', '').replace('GH₵', '').replace('GHC', '').replace('ghc', '').strip()
            try:
                price = float(clean_price)
            except (ValueError, TypeError):
                price = None
        try:
            mileage = int(str(data.get('mileage', 0) or 0).replace(',', '').strip())
        except (ValueError, TypeError):
            mileage = 0
        transmission = data.get('transmission', 'Automatic') or 'Automatic'
        fuel_type = data.get('fuel_type', 'Petrol') or 'Petrol'
        body_type = data.get('body_type', 'Sedan') or 'Sedan'
        color = data.get('color', 'Black') or 'Black'
        condition = data.get('condition', 'Foreign Used') or 'Foreign Used'
        status = data.get('status', 'Available') or 'Available'
        description = data.get('description', '') or ''
        features = data.get('features', '') or ''
        raw_imgs = data.get('images') or data.get('image_urls') or data.get('image_url')
        if raw_imgs:
            collected_images = parse_car_images(raw_imgs, None)

    if not title or not make or price is None:
        return jsonify({'error': 'Title, Make, and Price are mandatory'}), 400

    if not collected_images:
        collected_images = ["https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80"]

    # Deduplicate and cap at 5
    collected_images = collected_images[:5]
    primary_image = collected_images[0]
    images_json = json.dumps(collected_images)

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO cars (seller_id, title, make, model, year, price, mileage, transmission, fuel_type, body_type, color, condition, status, description, features, image_url, images)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user['id'], title, make, model, year or 2024, price, mileage, transmission, fuel_type, body_type, color, condition, status, description, features, primary_image, images_json))
    db.commit()
    new_id = cursor.lastrowid
    db.close()

    return jsonify({
        'success': True,
        'message': f'Car published with {len(collected_images)} photo(s) successfully!',
        'car_id': new_id,
        'images': collected_images
    })

@app.route('/api/cars/<int:car_id>', methods=['PUT', 'POST'])
def update_car(car_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM cars WHERE id = ?", (car_id,))
    car = cursor.fetchone()
    if not car:
        db.close()
        return jsonify({'error': 'Vehicle not found'}), 404

    is_admin = is_admin_or_receptionist(user)
    if not is_admin and car['seller_id'] != user['id']:
        db.close()
        return jsonify({'error': 'Unauthorized to edit this vehicle'}), 403

    fields = []
    values = []

    if request.is_json:
        data = request.get_json() or {}
        for key in ['title', 'make', 'model', 'year', 'price', 'mileage', 'transmission', 'fuel_type', 'body_type', 'color', 'condition', 'status', 'description', 'features', 'image_url', 'images']:
            if key in data:
                if key == 'images' and isinstance(data['images'], list):
                    parsed = parse_car_images(data['images'])
                    fields.append("images = ?")
                    values.append(json.dumps(parsed))
                    if parsed:
                        fields.append("image_url = ?")
                        values.append(parsed[0])
                else:
                    fields.append(f"{key} = ?")
                    values.append(data[key])
    else:
        # Form submission or multipart
        for key in ['title', 'make', 'model', 'transmission', 'fuel_type', 'body_type', 'color', 'condition', 'status', 'description', 'features']:
            val = request.form.get(key)
            if val is not None:
                fields.append(f"{key} = ?")
                values.append(val.strip())

        if 'year' in request.form:
            try:
                values.append(int(str(request.form.get('year')).replace(',', '').strip()))
                fields.append("year = ?")
            except Exception:
                pass

        if 'price' in request.form:
            try:
                clean_p = str(request.form.get('price')).replace(',', '').replace('GH₵', '').replace('GHC', '').strip()
                values.append(float(clean_p))
                fields.append("price = ?")
            except Exception:
                pass

        if 'mileage' in request.form:
            try:
                values.append(int(str(request.form.get('mileage', 0)).replace(',', '').strip()))
                fields.append("mileage = ?")
            except Exception:
                pass

        # Handle photos in edit
        collected_images = []
        files = request.files.getlist('image_files')
        if not files:
            files = request.files.getlist('image_file')
        for f in files:
            if f and f.filename and allowed_file(f.filename):
                try:
                    safe_name = secure_filename(f.filename)
                    ext = safe_name.rsplit('.', 1)[1].lower() if '.' in safe_name else 'jpg'
                    filename = f"car_{int(time.time())}_{secrets.token_hex(4)}.{ext}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    f.save(filepath)
                    collected_images.append(f"/static/uploads/{filename}")
                    if len(collected_images) >= 5:
                        break
                except Exception as save_err:
                    print(f"Error saving updated car photo: {save_err}")

        urls_raw = request.form.get('image_urls') or request.form.get('image_url')
        if urls_raw:
            parsed_urls = parse_car_images(urls_raw, None)
            for u in parsed_urls:
                if u and u not in collected_images and len(collected_images) < 5:
                    collected_images.append(u)

        if collected_images:
            fields.append("images = ?")
            values.append(json.dumps(collected_images))
            fields.append("image_url = ?")
            values.append(collected_images[0])

    if not fields:
        db.close()
        return jsonify({'error': 'No fields to update'}), 400

    values.append(car_id)
    cursor.execute(f"UPDATE cars SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    db.close()

    return jsonify({'success': True, 'message': 'Vehicle updated successfully'})

@app.route('/api/cars/<int:car_id>', methods=['DELETE'])
def delete_car(car_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT seller_id FROM cars WHERE id = ?", (car_id,))
    car = cursor.fetchone()
    if not car:
        db.close()
        return jsonify({'error': 'Car not found'}), 404

    # Allow admin/receptionist OR the seller who posted the car
    if not is_admin_or_receptionist(user) and car['seller_id'] != user['id']:
        db.close()
        return jsonify({'error': 'Forbidden. You do not own this car listing.'}), 403

    cursor.execute("DELETE FROM cars WHERE id = ?", (car_id,))
    db.commit()
    db.close()

    return jsonify({'success': True, 'message': 'Car deleted successfully'})

# --- Admin Data Control & Backup APIs ---
@app.route('/api/admin/export-data', methods=['GET'])
def admin_export_data():
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM cars ORDER BY id DESC")
    cars = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT id, name, email, phone, role, can_post, seller_status, created_at FROM users ORDER BY id DESC")
    users = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM swap_requests ORDER BY id DESC")
    swaps = [dict(r) for r in cursor.fetchall()]
    db.close()

    return jsonify({
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'exported_by': user.get('name'),
        'total_cars': len(cars),
        'total_users': len(users),
        'cars': cars,
        'users': users,
        'swap_requests': swaps
    })

@app.route('/api/admin/seed-fleet', methods=['POST'])
def admin_seed_fleet():
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403

    import database
    database.init_db()
    return jsonify({'success': True, 'message': 'Database verified and optimized successfully!'})

# --- Chat & Inquiries APIs ---
@app.route('/api/inquiries/start', methods=['POST'])
def start_inquiry():
    """
    Called when a customer clicks "Text Receptionist" or "Text Seller" on a car card.
    If the car was posted by a customer, the chat is directly with that seller!
    If the car is a dealership car, the chat is with Larry.
    """
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Authentication required', 'need_auth': True}), 401

    data = request.get_json() or {}
    car_id = data.get('car_id')
    if not car_id:
        return jsonify({'error': 'Car ID required'}), 400

    db = get_db()
    cursor = db.cursor()

    # Get car details and seller info
    cursor.execute('''
    SELECT cars.*,
           users.name as seller_name,
           users.role as seller_role,
           users.phone as seller_phone
    FROM cars
    LEFT JOIN users ON cars.seller_id = users.id
    WHERE cars.id = ?
    ''', (car_id,))
    car = cursor.fetchone()
    if not car:
        db.close()
        return jsonify({'error': 'Car not found'}), 404

    # Determine seller ID (fallback to admin/Larry if no seller_id)
    seller_id = car['seller_id']
    if not seller_id:
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin_row = cursor.fetchone()
        seller_id = admin_row['id'] if admin_row else 1

    # Check if the user is attempting to text themselves on their own car
    if user['id'] == seller_id:
        db.close()
        return jsonify({
            'error': "This is your own car listing! You cannot text yourself.",
            'is_owner': True
        }), 400

    # Check if a chat already exists between this customer and this car
    cursor.execute("SELECT * FROM chats WHERE customer_id = ? AND car_id = ?", (user['id'], car_id))
    chat = cursor.fetchone()

    is_user_seller = bool(car['seller_role'] != 'admin' and car['seller_id'] is not None)
    seller_name = car['seller_name'] or "Car Owner"

    if not chat:
        # Create new chat with explicit buyer and seller
        cursor.execute("INSERT INTO chats (customer_id, seller_id, car_id) VALUES (?, ?, ?)",
                       (user['id'], seller_id, car_id))
        chat_id = cursor.lastrowid

        if is_user_seller:
            # Person posted car: inquiry opens directly with the seller!
            initial_message = (
                f"Hi {seller_name}! I saw your {car['title']} listed on BIG-L Autos "
                f"for GH₵ {car['price']:,.2f}. Is it still available? I'd like to make an inquiry."
            )
            cursor.execute(
                "INSERT INTO messages (chat_id, sender_id, sender_role, message) VALUES (?, ?, 'customer', ?)",
                (chat_id, user['id'], initial_message)
            )
        else:
            # Dealership vehicle: Larry greeting
            receptionist_greeting = (
                f"Hello {user['name']}. Welcome to BIG-L Autos. "
                f"I'm Larry, head dealer at BIG-L Autos. I see you're interested in our {car['title']} priced at GH₵ {car['price']:,.2f}. "
                f"How can I assist you with this vehicle? We're open to cash discussions, financing terms, inspections at Somanya-Roundabout, and vehicle swaps!"
            )
            cursor.execute(
                "INSERT INTO messages (chat_id, sender_id, sender_role, message) VALUES (?, ?, 'admin', ?)",
                (chat_id, seller_id, receptionist_greeting)
            )
        db.commit()
    else:
        chat_id = chat['id']

    car_dict = dict(car)
    car_dict['is_user_seller'] = is_user_seller
    car_dict['seller_display_name'] = seller_name if is_user_seller else "Larry (Head Dealer)"

    db.close()
    return jsonify({
        'success': True,
        'chat_id': chat_id,
        'car': car_dict,
        'redirect_url': f"/customer?chat_id={chat_id}"
    })

@app.route('/api/chats', methods=['GET'])
def list_chats():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()

    if is_admin_or_receptionist(user):
        # Admin / Receptionist sees all chats across showroom
        query = '''
        SELECT c.id, c.customer_id, c.seller_id, c.car_id, c.created_at, c.updated_at,
               buyer.name as customer_name, buyer.email as customer_email, buyer.phone as customer_phone,
               seller.name as seller_name, seller.email as seller_email, seller.phone as seller_phone, seller.role as seller_role,
               cars.title as car_title, cars.price as car_price, cars.year as car_year,
               cars.image_url as car_image, cars.status as car_status,
               (SELECT id FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_message_id,
               (SELECT sender_id FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_sender_id,
               (SELECT message FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_message,
               (SELECT created_at FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_message_time,
               (SELECT COUNT(*) FROM messages WHERE chat_id = c.id AND is_read = 0 AND sender_id != ?) as unread_count
        FROM chats c
        JOIN users buyer ON c.customer_id = buyer.id
        LEFT JOIN users seller ON c.seller_id = seller.id
        JOIN cars ON c.car_id = cars.id
        ORDER BY c.updated_at DESC
        '''
        cursor.execute(query, (user['id'],))
    else:
        # Customer sees chats where they are either:
        # 1. The Buyer (customer_id = user['id']) inquiring on a car
        # 2. The Seller (seller_id = user['id']) receiving buyer inquiries on their posted car!
        query = '''
        SELECT c.id, c.customer_id, c.seller_id, c.car_id, c.created_at, c.updated_at,
               buyer.name as customer_name, buyer.email as customer_email, buyer.phone as customer_phone,
               seller.name as seller_name, seller.email as seller_email, seller.phone as seller_phone, seller.role as seller_role,
               cars.title as car_title, cars.price as car_price, cars.year as car_year,
               cars.image_url as car_image, cars.status as car_status,
               (SELECT id FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_message_id,
               (SELECT sender_id FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_sender_id,
               (SELECT message FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_message,
               (SELECT created_at FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) as last_message_time,
               (SELECT COUNT(*) FROM messages WHERE chat_id = c.id AND is_read = 0 AND sender_id != ?) as unread_count
        FROM chats c
        JOIN users buyer ON c.customer_id = buyer.id
        LEFT JOIN users seller ON c.seller_id = seller.id
        JOIN cars ON c.car_id = cars.id
        WHERE c.customer_id = ? OR c.seller_id = ?
        ORDER BY c.updated_at DESC
        '''
        cursor.execute(query, (user['id'], user['id'], user['id']))

    rows = cursor.fetchall()
    chats = []
    for r in rows:
        d = dict(r)
        is_seller_of_car = (d['seller_id'] == user['id'])
        is_user_posted = bool(d.get('seller_role') != 'admin' and d.get('seller_id') is not None)
        d['is_user_seller'] = is_user_posted

        if is_seller_of_car:
            d['chat_type'] = 'selling'
            d['other_party_name'] = d['customer_name']
            d['other_party_role'] = 'Buyer'
        else:
            d['chat_type'] = 'buying'
            d['other_party_name'] = d['seller_name'] if is_user_posted else "Larry (Head Dealer)"
            d['other_party_role'] = 'Seller' if is_user_posted else 'Dealership'

        chats.append(d)

    db.close()
    return jsonify({'chats': chats})

@app.route('/api/chats/<int:chat_id>/messages', methods=['GET'])
def get_chat_messages(chat_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()

    # Delta support: only return messages newer than `since` (message id).
    # Omitting `since` returns the full history (keeps initial load & tests unchanged).
    since = request.args.get('since', type=int)

    # Verify access to this chat (joining both buyer and seller)
    cursor.execute('''
    SELECT c.*,
           cars.title as car_title, cars.price as car_price, cars.year as car_year,
           cars.mileage as car_mileage, cars.transmission as car_transmission,
           cars.image_url as car_image, cars.status as car_status,
           cars.seller_id as car_seller_id,
           buyer.name as customer_name, buyer.phone as customer_phone, buyer.email as customer_email,
           seller.name as seller_name, seller.phone as seller_phone, seller.email as seller_email,
           seller.role as seller_role
    FROM chats c
    JOIN cars ON c.car_id = cars.id
    JOIN users buyer ON c.customer_id = buyer.id
    LEFT JOIN users seller ON c.seller_id = seller.id
    WHERE c.id = ?
    ''', (chat_id,))
    chat_info = cursor.fetchone()

    if not chat_info:
        db.close()
        return jsonify({'error': 'Chat not found'}), 404

    # Authorization: user must be admin/receptionist OR the buyer OR the seller of the car
    is_participant = (
        is_admin_or_receptionist(user) or
        chat_info['customer_id'] == user['id'] or
        chat_info['seller_id'] == user['id']
    )
    if not is_participant:
        db.close()
        return jsonify({'error': 'Forbidden'}), 403

    # Mark unread messages sent by the other participant as read
    cursor.execute("UPDATE messages SET is_read = 1 WHERE chat_id = ? AND sender_id != ?", (chat_id, user['id']))
    db.commit()

    # Get messages
    if since:
        cursor.execute('''
        SELECT m.id, m.chat_id, m.sender_id, m.sender_role, m.message, m.is_read, m.created_at,
               u.name as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.chat_id = ? AND m.id > ?
        ORDER BY m.id ASC
        ''', (chat_id, since))
    else:
        cursor.execute('''
        SELECT m.id, m.chat_id, m.sender_id, m.sender_role, m.message, m.is_read, m.created_at,
               u.name as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.chat_id = ?
        ORDER BY m.id ASC
        ''', (chat_id,))
    messages = [dict(m) for m in cursor.fetchall()]

    chat_dict = dict(chat_info)
    is_user_posted = bool(chat_dict.get('seller_role') != 'admin' and chat_dict.get('seller_id') is not None)
    chat_dict['is_user_seller'] = is_user_posted

    if user['id'] == chat_dict['customer_id']:
        chat_dict['chat_type'] = 'buying'
        chat_dict['other_party_name'] = chat_dict['seller_name'] if is_user_posted else "Larry (Head Dealer)"
        chat_dict['other_party_role'] = 'Seller' if is_user_posted else 'Dealership'
    elif user['id'] == chat_dict['seller_id']:
        chat_dict['chat_type'] = 'selling'
        chat_dict['other_party_name'] = chat_dict['customer_name']
        chat_dict['other_party_role'] = 'Buyer'
    else:
        chat_dict['chat_type'] = 'admin_view'
        chat_dict['other_party_name'] = f"{chat_dict['customer_name']} (Buyer) & {chat_dict['seller_name'] or 'Larry'} (Seller)"
        chat_dict['other_party_role'] = 'Showroom Inquiry'

    db.close()
    return jsonify({
        'chat': chat_dict,
        'messages': messages
    })

@app.route('/api/chats/<int:chat_id>/messages', methods=['POST'])
def send_chat_message(chat_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    message_text = data.get('message', '').strip()
    if not message_text:
        return jsonify({'error': 'Message cannot be empty'}), 400

    db = get_db()
    cursor = db.cursor()

    # Verify chat access
    cursor.execute("SELECT customer_id, seller_id FROM chats WHERE id = ?", (chat_id,))
    chat = cursor.fetchone()
    if not chat:
        db.close()
        return jsonify({'error': 'Chat not found'}), 404

    is_participant = (
        is_admin_or_receptionist(user) or
        chat['customer_id'] == user['id'] or
        chat['seller_id'] == user['id']
    )
    if not is_participant:
        db.close()
        return jsonify({'error': 'Forbidden'}), 403

    if is_admin_or_receptionist(user):
        sender_role = 'admin'
    elif user['id'] == chat['seller_id']:
        sender_role = 'seller'
    else:
        sender_role = 'customer'

    cursor.execute('''
    INSERT INTO messages (chat_id, sender_id, sender_role, message)
    VALUES (?, ?, ?, ?)
    ''', (chat_id, user['id'], sender_role, message_text))

    cursor.execute("UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (chat_id,))
    db.commit()
    msg_id = cursor.lastrowid

    db.close()

    return jsonify({
        'success': True,
        'message_id': msg_id,
        'message': {
            'id': msg_id,
            'chat_id': chat_id,
            'sender_id': user['id'],
            'sender_name': user['name'],
            'sender_role': sender_role,
            'message': message_text,
            'created_at': 'Just now'
        }
    })

# --- Sell / Swap Evaluation Requests ---
@app.route('/api/swap-sell', methods=['POST'])
def submit_swap_sell():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Please login to submit a sell or swap request'}), 401

    data = request.get_json() or {}
    req_type = data.get('request_type', 'sell') # 'sell' or 'swap'
    target_car_id = data.get('target_car_id')
    car_make = data.get('car_make', '').strip()
    car_model = data.get('car_model', '').strip()
    car_year = data.get('car_year')
    car_mileage = data.get('car_mileage', 0)
    expected_price = data.get('expected_price')
    condition_notes = data.get('condition_notes', '')

    if not car_make or not car_model or not car_year:
        return jsonify({'error': 'Make, Model, and Year are required'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO swap_sell_requests (user_id, request_type, target_car_id, car_make, car_model, car_year, car_mileage, expected_price, condition_notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user['id'], req_type, target_car_id, car_make, car_model, car_year, car_mileage, expected_price, condition_notes))
    db.commit()
    req_id = cursor.lastrowid

    # If this was linked to a target car for swap, create or send a chat message to receptionist
    if target_car_id:
        cursor.execute("SELECT id FROM chats WHERE customer_id = ? AND car_id = ?", (user['id'], target_car_id))
        existing_chat = cursor.fetchone()
        if not existing_chat:
            cursor.execute("INSERT INTO chats (customer_id, car_id) VALUES (?, ?)", (user['id'], target_car_id))
            chat_id = cursor.lastrowid
        else:
            chat_id = existing_chat['id']

        swap_msg = (
            f"[SWAP INQUIRY] Hi Larry, I would like to swap my {car_year} {car_make} {car_model} "
            f"({car_mileage:,} km, valued at approx GH₵ {float(expected_price or 0):,.2f}) for this vehicle. "
            f"Notes: {condition_notes or 'Ready for inspection at Somanya-Roundabout.'}"
        )
        cursor.execute("INSERT INTO messages (chat_id, sender_id, sender_role, message) VALUES (?, ?, 'customer', ?)",
                       (chat_id, user['id'], swap_msg))
        cursor.execute("UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (chat_id,))
        db.commit()

    db.close()
    return jsonify({
        'success': True,
        'message': 'Your request has been received! Our receptionist will review and contact you shortly.',
        'request_id': req_id
    })

@app.route('/api/swap-sell', methods=['GET'])
def list_swap_sell():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()

    if is_admin_or_receptionist(user):
        cursor.execute('''
        SELECT s.*, u.name as user_name, u.email as user_email, u.phone as user_phone,
               c.title as target_car_title, c.price as target_car_price, c.image_url as target_car_image
        FROM swap_sell_requests s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN cars c ON s.target_car_id = c.id
        ORDER BY s.id DESC
        ''')
    else:
        cursor.execute('''
        SELECT s.*, c.title as target_car_title, c.price as target_car_price, c.image_url as target_car_image
        FROM swap_sell_requests s
        LEFT JOIN cars c ON s.target_car_id = c.id
        WHERE s.user_id = ?
        ORDER BY s.id DESC
        ''', (user['id'],))

    rows = [dict(r) for r in cursor.fetchall()]
    db.close()
    return jsonify({'requests': rows})

@app.route('/api/swap-sell/<int:req_id>/status', methods=['PUT'])
def update_swap_sell_status(req_id):
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin required'}), 403

    status = request.json.get('status')
    if not status:
        return jsonify({'error': 'Status required'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE swap_sell_requests SET status = ? WHERE id = ?", (status, req_id))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': 'Status updated'})


# ─── User Car Listings (Post My Car) ──────────────────────────────────────────

@app.route('/api/user-listings', methods=['POST'])
def submit_user_listing():
    """Any logged-in customer can submit their own car for sale on the platform."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Please login to list your car'}), 401

    collected_images = []
    if request.content_type and 'multipart/form-data' in request.content_type:
        title        = request.form.get('title', '').strip()
        make         = request.form.get('make', '').strip()
        model        = request.form.get('model', '').strip()
        year         = request.form.get('year', type=int)
        price        = request.form.get('price', type=float)
        mileage      = request.form.get('mileage', 0, type=int)
        transmission = request.form.get('transmission', 'Automatic')
        fuel_type    = request.form.get('fuel_type', 'Petrol')
        body_type    = request.form.get('body_type', 'Sedan')
        color        = request.form.get('color', 'Black')
        condition    = request.form.get('condition', 'Local Used')
        description  = request.form.get('description', '')
        features     = request.form.get('features', '')

        # Process multiple files (up to 5)
        files = request.files.getlist('image_files')
        if not files:
            files = request.files.getlist('image_file')
        for key in ['image_file_1', 'image_file_2', 'image_file_3', 'image_file_4', 'image_file_5']:
            if key in request.files:
                files.append(request.files[key])

        for f in files:
            if f and f.filename and allowed_file(f.filename):
                safe_name = secure_filename(f.filename)
                ext = safe_name.rsplit('.', 1)[1].lower() if '.' in safe_name else 'jpg'
                filename = f"listing_{int(time.time())}_{secrets.token_hex(4)}.{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                f.save(filepath)
                collected_images.append(f"/static/uploads/{filename}")
                if len(collected_images) >= 5:
                    break

        if len(collected_images) < 5:
            urls_raw = request.form.getlist('image_urls') or request.form.get('image_urls') or request.form.get('image_url')
            if urls_raw:
                for u in parse_car_images(urls_raw, None):
                    if u and u not in collected_images:
                        collected_images.append(u)
                        if len(collected_images) >= 5:
                            break
    else:
        data         = request.get_json() or {}
        title        = data.get('title', '').strip()
        make         = data.get('make', '').strip()
        model        = data.get('model', '').strip()
        year         = data.get('year')
        price        = data.get('price')
        mileage      = data.get('mileage', 0)
        transmission = data.get('transmission', 'Automatic')
        fuel_type    = data.get('fuel_type', 'Petrol')
        body_type    = data.get('body_type', 'Sedan')
        color        = data.get('color', 'Black')
        condition    = data.get('condition', 'Local Used')
        description  = data.get('description', '')
        features     = data.get('features', '')
        raw_imgs     = data.get('images') or data.get('image_urls') or data.get('image_url')
        if raw_imgs:
            collected_images = parse_car_images(raw_imgs, None)

    if not title or not make or not model or not price:
        return jsonify({'error': 'Title, Make, Model, and Price are required'}), 400

    if not collected_images:
        collected_images = ["https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80"]

    collected_images = collected_images[:5]
    primary_image = collected_images[0]
    images_json = json.dumps(collected_images)

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
    INSERT INTO user_listings (user_id, title, make, model, year, price, mileage,
        transmission, fuel_type, body_type, color, condition, description, features, image_url, images)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user['id'], title, make, model, year or 2024, price, mileage,
          transmission, fuel_type, body_type, color, condition, description, features, primary_image, images_json))
    db.commit()
    new_id = cursor.lastrowid
    db.close()

    return jsonify({
        'success': True,
        'message': f'Your car listing with {len(collected_images)} photo(s) has been submitted! The admin will review it shortly.',
        'listing_id': new_id,
        'images': collected_images
    })


@app.route('/api/user-listings', methods=['GET'])
def get_user_listings():
    """Customers see their own listings; admin sees all listings."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()

    if is_admin_or_receptionist(user):
        cursor.execute('''
        SELECT ul.*, u.name as user_name, u.email as user_email, u.phone as user_phone
        FROM user_listings ul
        JOIN users u ON ul.user_id = u.id
        ORDER BY ul.id DESC
        ''')
    else:
        cursor.execute('''
        SELECT * FROM user_listings WHERE user_id = ? ORDER BY id DESC
        ''', (user['id'],))

    rows = []
    for r in cursor.fetchall():
        item = dict(r)
        item['images'] = parse_car_images(item.get('images'), item.get('image_url'))
        item['image_url'] = item['images'][0] if item['images'] else (item.get('image_url') or '')
        rows.append(item)

    db.close()
    return jsonify({'listings': rows})


@app.route('/api/user-listings/<int:listing_id>/review', methods=['PUT'])
def review_user_listing(listing_id):
    """Admin-only: Approve or reject a user listing.
    action = 'approve' → publishes the car to the main inventory.
    action = 'reject'  → marks it rejected with an optional note.
    action = 'pending' → resets back to pending.
    """
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin access required'}), 403

    data   = request.get_json() or {}
    action = data.get('action', '').lower()   # 'approve' | 'reject' | 'pending'
    note   = data.get('admin_note', '').strip()

    if action not in ('approve', 'reject', 'pending'):
        return jsonify({'error': "action must be 'approve', 'reject', or 'pending'"}), 400

    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM user_listings WHERE id = ?', (listing_id,))
    listing = cursor.fetchone()
    if not listing:
        db.close()
        return jsonify({'error': 'Listing not found'}), 404

    listing = dict(listing)
    approved_car_id = listing.get('approved_car_id')

    if action == 'approve':
        # If not yet published to main inventory, do it now
        if not approved_car_id:
            imgs = parse_car_images(listing.get('images'), listing.get('image_url'))
            cursor.execute('''
            INSERT INTO cars (seller_id, title, make, model, year, price, mileage,
                transmission, fuel_type, body_type, color, condition, status,
                description, features, image_url, images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Available', ?, ?, ?, ?)
            ''', (
                listing['user_id'], listing['title'], listing['make'], listing['model'], listing['year'],
                listing['price'], listing['mileage'], listing['transmission'],
                listing['fuel_type'], listing['body_type'], listing['color'],
                listing['condition'], listing['description'], listing['features'],
                imgs[0], json.dumps(imgs)
            ))
            approved_car_id = cursor.lastrowid

        cursor.execute('''
        UPDATE user_listings
        SET status = 'Approved', admin_note = ?, approved_car_id = ?, reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (note, approved_car_id, listing_id))
        db.commit()
        db.close()
        return jsonify({
            'success': True,
            'message': 'Listing approved and published to the showroom!',
            'car_id': approved_car_id
        })

    elif action == 'reject':
        # If car was previously approved/published, remove it from inventory
        if approved_car_id:
            cursor.execute('DELETE FROM cars WHERE id = ?', (approved_car_id,))

        cursor.execute('''
        UPDATE user_listings
        SET status = 'Rejected', admin_note = ?, approved_car_id = NULL, reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (note, listing_id))
        db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Listing rejected.'})

    else:  # pending
        cursor.execute('''
        UPDATE user_listings
        SET status = 'Pending', admin_note = ?, reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (note, listing_id))
        db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Listing reset to Pending.'})


@app.route('/api/user-listings/<int:listing_id>', methods=['DELETE'])
def delete_user_listing(listing_id):
    """Owner or admin can delete a listing (and its published car if approved)."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM user_listings WHERE id = ?', (listing_id,))
    listing = cursor.fetchone()
    if not listing:
        db.close()
        return jsonify({'error': 'Listing not found'}), 404

    listing = dict(listing)
    if not is_admin_or_receptionist(user) and listing['user_id'] != user['id']:
        db.close()
        return jsonify({'error': 'Forbidden'}), 403

    # Remove the published car entry if it exists
    if listing.get('approved_car_id'):
        cursor.execute('DELETE FROM cars WHERE id = ?', (listing['approved_car_id'],))

    cursor.execute('DELETE FROM user_listings WHERE id = ?', (listing_id,))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': 'Listing deleted.'})


# Update admin stats to include pending user listings count
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin required'}), 403

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as total_cars FROM cars")
    total_cars = cursor.fetchone()['total_cars']

    cursor.execute("SELECT COUNT(*) as available_cars FROM cars WHERE status = 'Available'")
    available_cars = cursor.fetchone()['available_cars']

    cursor.execute("SELECT COUNT(*) as total_chats FROM chats")
    total_chats = cursor.fetchone()['total_chats']

    cursor.execute("SELECT COUNT(*) as pending_requests FROM swap_sell_requests WHERE status = 'Pending Review'")
    pending_requests = cursor.fetchone()['pending_requests']

    cursor.execute("SELECT COUNT(*) as total_customers FROM users WHERE role = 'customer'")
    total_customers = cursor.fetchone()['total_customers']

    cursor.execute("SELECT COUNT(*) as pending_sellers FROM users WHERE seller_status = 'pending'")
    pending_sellers = cursor.fetchone()['pending_sellers']

    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = cursor.fetchone()['total_users']

    db.close()
    return jsonify({
        'total_cars': total_cars,
        'available_cars': available_cars,
        'total_chats': total_chats,
        'pending_requests': pending_requests,
        'total_customers': total_customers,
        'pending_sellers': pending_sellers,
        'total_users': total_users
    })



# ─── Profile-Based Seller Access Endpoints ────────────────────────────────────

@app.route('/api/seller/request-access', methods=['POST'])
def request_seller_access():
    """Customer submits their request to Larry for monthly posting access approval."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Please sign in to request seller access'}), 401

    if user.get('can_post'):
        return jsonify({'success': True, 'message': 'Your account already has approved posting access!'})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE users
        SET seller_status = 'pending', seller_requested_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (user['id'],))
    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'message': 'Your posting access request has been sent to Larry! Please make sure you have sent your GH₵ 50 monthly subscription to Larry via Mobile Money on 0549255121. Once confirmed, your direct posting access will be activated immediately.'
    })


@app.route('/api/seller/status', methods=['GET'])
def get_seller_status():
    """Returns current user's profile posting permission and their published cars."""
    user = get_current_user()
    if not user:
        return jsonify({'authenticated': False}), 401

    can_post = bool(user.get('can_post') or is_admin_or_receptionist(user))
    status = 'approved' if can_post else (user.get('seller_status') or 'none')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM cars WHERE seller_id = ? ORDER BY id DESC", (user['id'],))
    my_cars = [dict(r) for r in cursor.fetchall()]
    db.close()

    return jsonify({
        'authenticated': True,
        'can_post': can_post,
        'seller_status': status,
        'cars': my_cars,
        'user': user
    })


@app.route('/api/my-cars', methods=['GET'])
def get_my_cars():
    """Returns vehicles posted directly by this logged-in seller."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM cars WHERE seller_id = ? ORDER BY id DESC", (user['id'],))
    cars = [dict(r) for r in cursor.fetchall()]
    db.close()
    return jsonify({'cars': cars})


@app.route('/api/admin/sellers', methods=['GET'])
def admin_list_sellers():
    """Receptionist/Admin views all customer accounts and their posting permission."""
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin / Receptionist access required'}), 403

    status_filter = request.args.get('status', 'all').strip().lower()

    query = """
    SELECT u.id, u.name, u.email, u.phone, u.role, u.can_post, u.seller_status, u.seller_requested_at, u.created_at,
           (SELECT COUNT(*) FROM cars WHERE seller_id = u.id) as posted_cars_count
    FROM users u
    WHERE u.role = 'customer'
    """
    params = []
    if status_filter == 'pending':
        query += " AND u.seller_status = 'pending'"
    elif status_filter == 'approved':
        query += " AND u.can_post = 1"
    elif status_filter == 'not_approved':
        query += " AND (u.can_post = 0 OR u.can_post IS NULL)"

    query += " ORDER BY CASE WHEN u.seller_status = 'pending' THEN 0 ELSE 1 END, u.id DESC"

    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, params)
    sellers = [dict(r) for r in cursor.fetchall()]
    db.close()
    return jsonify({'sellers': sellers})


@app.route('/api/admin/sellers/<int:target_user_id>/access', methods=['POST'])
def admin_manage_seller_access(target_user_id):
    """Receptionist/Admin approves or revokes a customer's posting privilege."""
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin / Receptionist access required'}), 403

    data = request.get_json() or {}
    action = data.get('action', '').lower()

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (target_user_id,))
    target = cursor.fetchone()
    if not target:
        db.close()
        return jsonify({'error': 'User not found'}), 404

    if action == 'approve':
        cursor.execute("UPDATE users SET can_post = 1, seller_status = 'approved' WHERE id = ?", (target_user_id,))
        msg = f"Profile approved! {target['name']} can now post cars directly to the showroom without waiting."
    elif action == 'revoke':
        cursor.execute("UPDATE users SET can_post = 0, seller_status = 'rejected' WHERE id = ?", (target_user_id,))
        msg = f"Posting access revoked for {target['name']}."
    else:
        db.close()
        return jsonify({'error': "Action must be 'approve' or 'revoke'"}), 400

    db.commit()
    db.close()
    return jsonify({'success': True, 'message': msg})


@app.route('/api/admin/users', methods=['GET'])
def admin_list_users():
    """Receptionist/Admin views all registered user accounts with activity stats and search/filtering."""
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin / Receptionist access required'}), 403

    status_filter = request.args.get('status', 'all').strip().lower()
    search_q = request.args.get('q', '').strip()

    query = """
    SELECT u.id, u.name, u.email, u.phone, u.role, u.can_post, u.seller_status, u.seller_requested_at, u.created_at,
           (SELECT COUNT(*) FROM cars WHERE seller_id = u.id) as posted_cars_count,
           (SELECT COUNT(*) FROM chats WHERE customer_id = u.id OR seller_id = u.id) as chats_count,
           (SELECT COUNT(*) FROM swap_sell_requests WHERE user_id = u.id) as swap_requests_count
    FROM users u
    WHERE 1=1
    """
    params = []
    if status_filter == 'pending':
        query += " AND u.seller_status = 'pending' AND (u.can_post = 0 OR u.can_post IS NULL)"
    elif status_filter == 'approved':
        query += " AND u.can_post = 1"
    elif status_filter == 'not_approved' or status_filter == 'buyer':
        query += " AND (u.can_post = 0 OR u.can_post IS NULL) AND u.role = 'customer'"
    elif status_filter == 'customer':
        query += " AND u.role = 'customer'"
    elif status_filter == 'admin':
        query += " AND u.role IN ('admin', 'receptionist')"

    if search_q:
        query += " AND (u.name LIKE ? OR u.email LIKE ? OR u.phone LIKE ?)"
        wildcard = f"%{search_q}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY CASE WHEN u.id = 1 THEN 0 WHEN u.role IN ('admin', 'receptionist') THEN 1 WHEN u.seller_status = 'pending' THEN 2 ELSE 3 END, u.id DESC"

    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, params)
    raw_users = cursor.fetchall()
    users_list = []
    for r in raw_users:
        u_dict = dict(r)
        u_dict['is_primary_admin'] = (u_dict['id'] == 1 or u_dict['role'] == 'admin')
        users_list.append(u_dict)

    # Summary metrics
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE seller_status = 'pending' AND (can_post = 0 OR can_post IS NULL)")
    pending_sellers = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE can_post = 1")
    approved_sellers = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
    customer_count = cursor.fetchone()[0]

    db.close()
    return jsonify({
        'users': users_list,
        'total': total_users,
        'customer_count': customer_count,
        'pending_sellers': pending_sellers,
        'approved_sellers': approved_sellers
    })


@app.route('/api/admin/users/<int:target_user_id>', methods=['DELETE', 'POST'])
@app.route('/api/admin/users/<int:target_user_id>/delete', methods=['POST', 'DELETE'])
def admin_delete_user(target_user_id):
    """
    Permanently deletes a single user account and cascades deletion of all their messages,
    chats, listings, and trade-in evaluation requests. Strictly protects primary admin account.
    """
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin / Receptionist access required'}), 403

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, email, role FROM users WHERE id = ?", (target_user_id,))
    target = cursor.fetchone()
    if not target:
        db.close()
        return jsonify({'error': 'User account not found'}), 404

    target = dict(target)
    # Strictly protect root admin account and administrative roles
    if target['id'] == 1 or target['role'] in ('admin', 'receptionist') or target['id'] == user['id']:
        db.close()
        return jsonify({'error': 'The primary administrative account is protected and cannot be deleted.'}), 403

    try:
        # 1. Delete messages in chats where target user is customer or seller, or where target is sender
        cursor.execute("""
            DELETE FROM messages 
            WHERE sender_id = ? 
               OR chat_id IN (SELECT id FROM chats WHERE customer_id = ? OR seller_id = ?)
        """, (target_user_id, target_user_id, target_user_id))

        # 2. Delete chats
        cursor.execute("DELETE FROM chats WHERE customer_id = ? OR seller_id = ?", (target_user_id, target_user_id))

        # 3. Delete user listings and seller showroom cars
        cursor.execute("DELETE FROM user_listings WHERE user_id = ?", (target_user_id,))
        cursor.execute("DELETE FROM cars WHERE seller_id = ?", (target_user_id,))

        # 4. Delete swap and sell valuation requests
        cursor.execute("DELETE FROM swap_sell_requests WHERE user_id = ?", (target_user_id,))

        # 5. Delete the user record
        cursor.execute("DELETE FROM users WHERE id = ?", (target_user_id,))

        db.commit()
    except Exception as e:
        db.rollback()
        db.close()
        return jsonify({'error': f'Failed to delete user account: {str(e)}'}), 500

    db.close()
    return jsonify({
        'success': True,
        'message': f"Account for {target['name']} ({target['email']}) has been permanently deleted.",
        'deleted_user_id': target_user_id
    })


@app.route('/api/admin/clean-users', methods=['POST'])
def admin_clean_users():
    """Wipes all non-admin users and their chats/requests from the system, keeping only Admin."""
    user = get_current_user()
    if not is_admin_or_receptionist(user):
        return jsonify({'error': 'Admin / Receptionist access required'}), 403

    db = get_db()
    cursor = db.cursor()
    cursor.execute('PRAGMA foreign_keys = ON;')
    cursor.execute('DELETE FROM messages WHERE chat_id IN (SELECT id FROM chats WHERE customer_id != 1) OR sender_id != 1')
    cursor.execute('DELETE FROM chats WHERE customer_id != 1')
    cursor.execute('DELETE FROM user_listings WHERE user_id != 1')
    cursor.execute('DELETE FROM swap_sell_requests WHERE user_id != 1')
    cursor.execute("DELETE FROM users WHERE id != 1 AND role NOT IN ('admin', 'receptionist')")
    db.commit()
    cursor.execute('SELECT COUNT(*) as count FROM users')
    remaining = cursor.fetchone()['count']
    db.close()

    return jsonify({
        'success': True,
        'message': f'All non-admin accounts removed successfully. System has {remaining} admin account.',
        'remaining_users': remaining
    })


if __name__ == '__main__':
    print("Starting BIG L Autos server on http://0.0.0.0:5000 ...")
    print("Access locally:  http://127.0.0.1:5000")
    print("Access on phone: http://172.20.10.3:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)

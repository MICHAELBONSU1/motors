import sqlite3
import os
import json
import hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.environ.get('DATABASE_PATH') or os.path.join(os.path.dirname(__file__), 'big_l_autos.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def hash_password(password):
    """Cryptographically salted PBKDF2-SHA256 password hash."""
    return generate_password_hash(password, method='pbkdf2:sha256')

def verify_password(stored_hash, password):
    """
    Verifies a password against the stored hash.
    Supports both modern Werkzeug salted hashes and legacy SHA-256 with auto-rehash flag.
    Returns (is_valid: bool, needs_rehash: bool).
    """
    if not stored_hash or not password:
        return False, False

    # Check for modern Werkzeug hash format (e.g., 'pbkdf2:sha256:...' or 'scrypt:...')
    if stored_hash.startswith('pbkdf2:') or stored_hash.startswith('scrypt:'):
        is_valid = check_password_hash(stored_hash, password)
        return is_valid, False

    # Legacy unsalted SHA-256 fallback (64 hex characters)
    legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    if legacy_hash == stored_hash:
        return True, True  # Valid, but caller should rehash to PBKDF2!

    return False, False

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Users Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'customer',
        can_post INTEGER DEFAULT 0,
        seller_status TEXT DEFAULT 'none',
        seller_requested_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Migration checks for existing users table
    cursor.execute("PRAGMA table_info(users)")
    u_cols = [c[1] for c in cursor.fetchall()]
    if 'can_post' not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN can_post INTEGER DEFAULT 0")
    if 'seller_status' not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN seller_status TEXT DEFAULT 'none'")
    if 'seller_requested_at' not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN seller_requested_at TIMESTAMP")

    # Cars Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        title TEXT NOT NULL,
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        year INTEGER NOT NULL,
        price REAL NOT NULL,
        mileage INTEGER DEFAULT 0,
        transmission TEXT DEFAULT 'Automatic',
        fuel_type TEXT DEFAULT 'Petrol',
        body_type TEXT DEFAULT 'Sedan',
        color TEXT DEFAULT 'Emerald Green',
        condition TEXT DEFAULT 'Foreign Used',
        status TEXT DEFAULT 'Available',
        description TEXT,
        features TEXT,
        image_url TEXT,
        images TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Migration checks for existing cars table
    cursor.execute("PRAGMA table_info(cars)")
    c_cols = [c[1] for c in cursor.fetchall()]
    if 'seller_id' not in c_cols:
        cursor.execute("ALTER TABLE cars ADD COLUMN seller_id INTEGER")
    if 'images' not in c_cols:
        cursor.execute("ALTER TABLE cars ADD COLUMN images TEXT")

    # Chats / Inquiries Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        seller_id INTEGER DEFAULT 1,
        car_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES users (id),
        FOREIGN KEY (seller_id) REFERENCES users (id),
        FOREIGN KEY (car_id) REFERENCES cars (id)
    )
    ''')

    # Migration checks for existing chats table
    cursor.execute("PRAGMA table_info(chats)")
    ch_cols = [c[1] for c in cursor.fetchall()]
    if 'seller_id' not in ch_cols:
        cursor.execute("ALTER TABLE chats ADD COLUMN seller_id INTEGER DEFAULT 1")
    cursor.execute('''
    UPDATE chats SET seller_id = (
        SELECT COALESCE(cars.seller_id, 1) FROM cars WHERE cars.id = chats.car_id
    ) WHERE seller_id IS NULL OR seller_id = 1
    ''')

    # Messages Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        sender_role TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats (id),
        FOREIGN KEY (sender_id) REFERENCES users (id)
    )
    ''')

    # Performance indexes for responsive chat queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_created ON messages(chat_id, id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_customer ON chats(customer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_seller ON chats(seller_id)")

    # User Car Listings Table (customers post their own cars for sale)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        year INTEGER NOT NULL,
        price REAL NOT NULL,
        mileage INTEGER DEFAULT 0,
        transmission TEXT DEFAULT 'Automatic',
        fuel_type TEXT DEFAULT 'Petrol',
        body_type TEXT DEFAULT 'Sedan',
        color TEXT DEFAULT 'Black',
        condition TEXT DEFAULT 'Local Used',
        description TEXT,
        features TEXT,
        image_url TEXT,
        images TEXT,
        status TEXT DEFAULT 'Pending',
        admin_note TEXT,
        approved_car_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (approved_car_id) REFERENCES cars (id)
    )
    ''')

    cursor.execute("PRAGMA table_info(user_listings)")
    ul_cols = [c[1] for c in cursor.fetchall()]
    if 'images' not in ul_cols:
        cursor.execute("ALTER TABLE user_listings ADD COLUMN images TEXT")

    # Swap & Sell Requests Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS swap_sell_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        request_type TEXT NOT NULL,
        target_car_id INTEGER,
        car_make TEXT NOT NULL,
        car_model TEXT NOT NULL,
        car_year INTEGER NOT NULL,
        car_mileage INTEGER,
        expected_price REAL,
        condition_notes TEXT,
        status TEXT DEFAULT 'Pending Review',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (target_car_id) REFERENCES cars (id)
    )
    ''')

    conn.commit()

    # Seed Admin / Receptionist if not exists
    cursor.execute("SELECT * FROM users WHERE email = 'admin@biglautos.com'")
    admin = cursor.fetchone()
    if not admin:
        admin_pass = hash_password("admin123")
        cursor.execute('''
        INSERT INTO users (name, email, phone, password_hash, role, can_post, seller_status)
        VALUES (?, ?, ?, ?, 'admin', 1, 'approved')
        ''', ("Larry (Head Dealer & Admin)", "admin@biglautos.com", "0549255121", admin_pass))
    else:
        # Ensure admin password is upgraded to salted PBKDF2 if legacy
        if not admin['password_hash'].startswith('pbkdf2:') and not admin['password_hash'].startswith('scrypt:'):
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password("admin123"), admin['id']))
        # Update name and phone to ensure Admin Larry is set with posting access
        cursor.execute("UPDATE users SET name = 'Larry (Head Dealer & Admin)', phone = '0549255121', role = 'admin', can_post = 1, seller_status = 'approved' WHERE id = ?", (admin['id'],))

    # Ensure all site owner emails always have admin role and posting privileges
    cursor.execute("""
    UPDATE users 
    SET role = 'admin', can_post = 1, seller_status = 'approved'
    WHERE email IN ('admin@biglautos.com', 'receptionist@biglautos.com', 'bonsum114@gmail.com', 'bonsum1141@gmail.com', 'michaelbonsu2000@icloud.com')
       OR email LIKE 'bonsum114%'
       OR email LIKE 'michaelbonsu%'
    """)

    # Purge any legacy demo/seed cars - strictly maintain ONLY vehicles posted by real users/dealers
    cursor.execute("""
    DELETE FROM cars 
    WHERE title IN (
        '2023 Mercedes-AMG GT R Coupe',
        '2023 Mercedes-Benz C-Class C300 AMG Line',
        '2022 Toyota Land Cruiser Prado TX-L',
        '2021 BMW 5 Series 530i M Sport',
        '2024 Lexus RX 350 F Sport',
        '2023 Range Rover Velar R-Dynamic'
    )
    """)

    # Ensure all real cars in database have their images column backfilled with up to 5 photos
    cursor.execute("SELECT id, title, image_url, images FROM cars")
    for row in cursor.fetchall():
        car_id = row['id']
        car_title = row['title'] or ''
        primary = row['image_url'] or ''
        existing_imgs = []
        if row['images']:
            try:
                parsed = json.loads(row['images'])
                if isinstance(parsed, list):
                    existing_imgs = parsed
            except Exception:
                pass
        if not existing_imgs:
            matched_photos = [primary] if primary else ["https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80"]
            cursor.execute("UPDATE cars SET images = ? WHERE id = ?", (json.dumps(matched_photos[:5]), car_id))

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database updated successfully!")

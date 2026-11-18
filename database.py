import sqlite3
import os
import json
import hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'big_l_autos.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    cursor.execute("SELECT * FROM users WHERE role IN ('admin', 'receptionist')")
    admin = cursor.fetchone()
    if not admin:
        admin_pass = hash_password("admin123")
        cursor.execute('''
        INSERT INTO users (name, email, phone, password_hash, role)
        VALUES (?, ?, ?, ?, ?)
        ''', ("Sarah (Head Receptionist & Admin)", "admin@biglautos.com", "0549255121", admin_pass, "admin"))
    else:
        # Ensure admin password is upgraded to salted PBKDF2 if legacy
        if not admin['password_hash'].startswith('pbkdf2:') and not admin['password_hash'].startswith('scrypt:'):
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password("admin123"), admin['id']))
        # Update name and phone to ensure Receptionist & Admin are unified, and set posting access
        cursor.execute("UPDATE users SET name = 'Sarah (Head Receptionist & Admin)', phone = '0549255121', can_post = 1, seller_status = 'approved' WHERE id = ?", (admin['id'],))

    # Default 5-photo packs for curated showroom inventory
    default_car_photos = {
        'Mercedes-AMG GT R Coupe': [
            "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=80"
        ],
        'C300': [
            "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1553440569-bcc63803a83d?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1502877338535-766e1452684a?auto=format&fit=crop&w=1200&q=80"
        ],
        'Land Cruiser Prado': [
            "https://images.unsplash.com/photo-1594502184342-2e12f877aa73?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=80"
        ],
        '5 Series': [
            "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1580273916550-e323be2ae537?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1556189250-72ba954cfc2b?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=80"
        ],
        'RX 350': [
            "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=80"
        ],
        'Velar': [
            "https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1594502184342-2e12f877aa73?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=80"
        ]
    }

    # Check cars count
    cursor.execute("SELECT COUNT(*) as count FROM cars")
    count = cursor.fetchone()['count']
    if count == 0:
        seed_cars = [
            (
                "2023 Mercedes-AMG GT R Coupe",
                "Mercedes-Benz", "AMG GT", 2023, 1650000, 8400,
                "Automatic", "Petrol", "Coupe", "Green Hell Magno", "Brand New", "Available",
                "Flagship Mercedes-AMG GT Coupe in signature metallic emerald green. Handcrafted 4.0L Bi-Turbo V8 engine, active aerodynamics, race interior, ceramic brakes.",
                "Handcrafted Bi-Turbo V8, AMG Track Pace, Burmester High-End Surround, Ceramic Brakes",
                "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=1200&q=80",
                json.dumps(default_car_photos['Mercedes-AMG GT R Coupe'])
            ),
            (
                "2023 Mercedes-Benz C-Class C300 AMG Line",
                "Mercedes-Benz", "C300", 2023, 580000, 14200,
                "Automatic", "Petrol", "Sedan", "Emerald Green", "Foreign Used", "Available",
                "Flawlessly maintained executive sedan with AMG styling package, panoramic sunroof, ambient lighting, and Burmester sound system. Ready for delivery or swap.",
                "Sunroof, Leather Seats, 360 Camera, Navigation, Apple CarPlay, Heated Seats",
                "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=1200&q=80",
                json.dumps(default_car_photos['C300'])
            ),
            (
                "2022 Toyota Land Cruiser Prado TX-L",
                "Toyota", "Land Cruiser Prado", 2022, 920000, 26000,
                "Automatic", "Diesel", "SUV", "Pearl White", "Foreign Used", "Available",
                "Rugged luxury 7-seater SUV with full terrain select, cool box, keyless entry, leather interior, and exceptional fuel economy.",
                "4x4, 7 Seats, Cool Box, Push Start, Alloy Wheels, Reverse Camera",
                "https://images.unsplash.com/photo-1594502184342-2e12f877aa73?auto=format&fit=crop&w=1200&q=80",
                json.dumps(default_car_photos['Land Cruiser Prado'])
            ),
            (
                "2021 BMW 5 Series 530i M Sport",
                "BMW", "5 Series", 2021, 540000, 31000,
                "Automatic", "Petrol", "Sedan", "Alpine White", "Foreign Used", "Available",
                "Dynamic executive sedan with aggressive M Sport package, adaptive LED headlights, digital cockpit, and immaculate maintenance history.",
                "M-Sport Package, Digital Cockpit, Wireless Charging, Harman Kardon Audio",
                "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1200&q=80",
                json.dumps(default_car_photos['5 Series'])
            ),
            (
                "2024 Lexus RX 350 F Sport",
                "Lexus", "RX 350", 2024, 980000, 5300,
                "Automatic", "Hybrid", "SUV", "Deep Forest Green", "Brand New", "Available",
                "The pinnacle of modern crossover elegance. Features Lexus Safety System+ 3.0, Mark Levinson audio, head-up display, and hybrid fuel efficiency.",
                "Hybrid, Panoramic Roof, Heads-Up Display, Lane Assist, Ventilated Seats",
                "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80",
                json.dumps(default_car_photos['RX 350'])
            ),
            (
                "2023 Range Rover Velar R-Dynamic",
                "Land Rover", "Range Rover Velar", 2023, 860000, 18500,
                "Automatic", "Petrol", "SUV", "Santorini Black", "Foreign Used", "Available",
                "Sleek and revolutionary British SUV with flush deployable door handles, Touch Pro Duo touchscreen, Meridian 3D sound, and air suspension.",
                "Air Suspension, Meridian Sound, Matrix LED, Panoramic Sunroof, AWD",
                "https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=1200&q=80",
                json.dumps(default_car_photos['Velar'])
            )
        ]

        for car in seed_cars:
            cursor.execute('''
            INSERT INTO cars (title, make, model, year, price, mileage, transmission, fuel_type, body_type, color, condition, status, description, features, image_url, images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', car)

    # Ensure all cars in database have their images column backfilled with up to 5 photos
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
        if not existing_imgs or len(existing_imgs) < 2:
            matched_photos = None
            for key, photo_list in default_car_photos.items():
                if key.lower() in car_title.lower():
                    matched_photos = photo_list
                    break
            if not matched_photos:
                matched_photos = [primary] if primary else ["https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=80"]
            cursor.execute("UPDATE cars SET images = ? WHERE id = ?", (json.dumps(matched_photos[:5]), car_id))

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database updated successfully!")

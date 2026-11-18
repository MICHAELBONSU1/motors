# BIG-L AUTOS

> **"YOUR NEXT CAR AWAITS YOU"**  
> **• WE SELL • WE BUY • WE SWAP**  
> **LOCATION: SOMANYA-ROUNDABOUT | CONTACT: 0549255121**

A luxury, clean, humanized, and professional web platform built for **BIG-L AUTOS** using **HTML5, CSS3, JavaScript, and Python (Flask + SQLite)**.

Designed with the **Dark Emerald Green, Mint, Crisp White & Black** aesthetic inspired by the official showroom visual flyer.

---

## 🌟 Key Features

### 1. Cinematic Hero Presentation & Branding
- **Official Brand Emblem**: Circular outline with the sports car silhouette and capital 'L' badge.
- **Bold Headline**: `YOUR NEXT CAR AWAITS YOU` with `• WE SELL • WE BUY • WE SWAP`.
- **Location & Contact Floating Badges**:
  - `LOCATION: SOMANYA-ROUNDABOUT`
  - `CONTACT: 0549255121`
- **Zero Distracting Icons**: Clean, professional typography across the entire interface.
- **No Green Status Pills**: Clean vehicle cards with no distracting status overlays.

### 2. "Text Receptionist" Inquiry Flow
- Under each car card: A prominent **"Text Receptionist"** button.
- **New Visitors**: Automatically prompts account creation/login with that exact vehicle pinned as the reason for the conversation.
- **Immediate Context Initialization**: Links the buyer directly to **Sarah Mitchell** (Head Receptionist). The vehicle specifications and price remain pinned at the top of the chat.
- Negotiation quick-chips:
  - *Ask for cash discount*
  - *Request test drive*
  - *Inquire about swap*
  - *Ask for best price*

### 3. Customer Dashboard
- Real-time chat with the receptionist to negotiate pricing and arrange inspections.
- **Sell & Swap Portal**: Submit your current car details (Make, Model, Year, Mileage, Valuation, Notes) for a direct cash buyout or showroom vehicle swap.

### 4. Receptionist & Admin Portal
- **Car Upload & Specifications**: Upload vehicle photos and set complete specs (Make, Model, Year, Price, Mileage, Transmission, Fuel, Body, Color, Features, Description).
- **Fleet Management**: Mark vehicles as Available, Reserved, or Sold.
- **Live Inquiries Desk**: Real-time customer chat management with canned response templates and contact options.
- **Sell & Swap Desk**: Review and manage trade-in offers.

---

## 🚀 How to Run

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start the server:
```bash
python app.py
```

3. Open in browser:
```
http://127.0.0.1:5000
```

### 🔐 Production Credentials & Security
- **Head Receptionist (Admin)**: `admin@biglautos.com` / Password: `admin123` (Phone: `0549255121`)
- **Customer Access**: Sign up directly via the showroom or login portal using your own email and secure password.

### 🛡️ Enterprise Security Hardening
- **Salted PBKDF2 Password Hashing**: Cryptographic password protection with backward-compatible auto-migration.
- **Brute-Force Rate Limiting**: Built-in sliding-window limiter on `/api/auth/login` (blocks IP/account after 5 failed attempts for 15 minutes).
- **Hardened Session Management**: Cryptographically generated persistent secret keys, `HttpOnly`, `SameSite=Lax`, and 12-hour session expiration.
- **Defensive HTTP Security Headers**: `X-Frame-Options: SAMEORIGIN` (anti-clickjacking), `X-Content-Type-Options: nosniff`, `X-XSS-Protection`, strict `Content-Security-Policy`, and `Referrer-Policy`.
- **Upload Protection**: File size cap (8MB), strict extension whitelist, and randomized nonces preventing path traversal.

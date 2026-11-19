# StormerHost Deployment Guide — BIG-L Autos

This guide covers deploying **BIG-L Autos** to **StormerHost** (cPanel / CloudLinux Python Selector) and explains why your data will be **100% persistent** (no data loss on restarts).

---

## Why Data Was Lost on Render vs. Why StormerHost Fixes It

| Feature | Render (Free Tier) | StormerHost (cPanel) |
| :--- | :--- | :--- |
| **Storage Type** | Ephemeral Docker Container | **Persistent SSD Storage** (`/home/username/...`) |
| **On Server Restart** | Container is destroyed & recreated from Git; all new database records and uploads are wiped. | **All files remain safe on disk**. Database (`big_l_autos.db`) and uploaded images (`static/uploads/`) are never lost. |
| **Database Performance** | Default SQLite locking conflicts | **SQLite WAL mode enabled** (`PRAGMA journal_mode=WAL`), allowing simultaneous reads and writes without lockups. |

---

## Pre-Requisites
1. A **StormerHost** cPanel account with Python support ("Setup Python App").
2. Your domain name pointed to StormerHost (e.g. `biglautos.com` or a subdomain).
3. The latest code pushed to your GitHub repository: `https://github.com/MICHAELBONSU1/motors.git`.

---

## Step-by-Step Deployment Instructions

### Step 1: Create the Python Application in cPanel
1. Log in to your **StormerHost cPanel**.
2. In the search box, type **Setup Python App** (under the *Software* section) and click it.
3. Click the blue **Create Application** button.
4. Fill in the fields:
   - **Python version**: Select `3.10` or `3.11`.
   - **Application root**: Enter the folder name for your project, e.g. `motors` (or `public_html` if deploying to the root domain).
   - **Application URL**: Select your domain and path (leave path blank for the root domain, e.g. `https://yourdomain.com`).
   - **Application startup file**: Leave empty or enter `passenger_wsgi.py`.
   - **Application Entry point**: Leave empty or enter `application`.
5. Click **Create** in the top right.

---

### Step 2: Deploy Your Project Code
You can get your code onto StormerHost in either of two ways:

#### Option A: Using cPanel Git Version Control (Recommended)
1. In cPanel, open **Git™ Version Control**.
2. Click **Create**.
3. Set **Clone URL** to: `https://github.com/MICHAELBONSU1/motors.git`.
4. Set **Repository Path** to the application root you specified in Step 1 (e.g. `/home/username/motors`).
5. Click **Create**.

#### Option B: Uploading via File Manager
1. On your computer, compress the project folder into a `.zip` file (exclude `.git` and `__pycache__` if you wish).
2. In cPanel, open **File Manager**.
3. Navigate to your application root directory (e.g. `motors`).
4. Click **Upload**, select your zip file, and extract it inside that folder.

---

### Step 3: Install Required Python Packages
1. Go back to **Setup Python App** in cPanel and click on your application.
2. At the top of the page, you will see a command box labeled:
   ```bash
   source /home/username/virtualenv/motors/3.10/bin/activate && cd /home/username/motors
   ```
   Click on the command to copy it to your clipboard.
3. In cPanel, open the **Terminal** tool (under *Advanced*).
4. Paste that copied command and press **Enter**. Your terminal prompt will now show the virtual environment prefix `(motors:3.10)`.
5. Run the following command to install all dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

### Step 4: Initialize the Database (If Setting Up Fresh)
While still inside the cPanel Terminal in your virtual environment:
```bash
python database.py
```
This ensures the SQLite database (`big_l_autos.db`) is initialized with:
- WAL mode enabled for high concurrency.
- Head Receptionist admin account (`Sarah Mitchell`, `0549255121`).
- Default luxury showroom fleet listings.

---

### Step 5: Verify the WSGI File
Ensure `passenger_wsgi.py` exists in your application root folder. The file already included in the repository contains:
```python
import sys
import os

project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from app import app as application
```
*Note: Phusion Passenger automatically loads `application` from this file.*

---

### Step 6: Enable Free SSL (HTTPS)
Service workers, live audio notifications, and push alerts require HTTPS to function properly.
1. In cPanel, search for **SSL/TLS Status** or **Let's Encrypt SSL**.
2. Select your domain and click **Run AutoSSL** or **Issue SSL**.
3. Once SSL is installed, your site will be accessible via `https://`.

---

### Step 7: Restart the Application
1. Go back to **Setup Python App** in cPanel.
2. Find your application and click the **Restart** button.
3. Open your website domain in your browser!

---

## Verification Checklist
- [x] **Home page loads with luxury dark emerald branding**: Check showroom cars and swap/sell forms.
- [x] **Admin Login**: Go to `/admin`, log in with Sarah Mitchell's credentials.
- [x] **Live Inquiries**: Submit an enquiry from the website; verify that the receptionist desk receives it instantly.
- [x] **Data Persistence Check**: Add a car or message in the admin portal, click **Restart** in cPanel Python App, and refresh the page. All data will remain intact!

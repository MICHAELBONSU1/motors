import sys
import os

# Insert project root directory into sys.path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# cPanel Phusion Passenger expects a WSGI callable named 'application'
from app import app as application

"""Titik masuk untuk hosting cPanel (Setup Python App / Phusion Passenger).

Di cPanel isi: Application startup file = passenger_wsgi.py,
Application Entry point = application.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run import app as application  # noqa: F401

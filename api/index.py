from flask import Flask, redirect
import os
import sys

# Add parent directory to path to import app
sys.path.insert(1, os.path.join(sys.path[0], '..'))
from app import app as application

# For Vercel serverless function
def handler(request, response):
    return application(request, response)

# Export the app variable
app = application
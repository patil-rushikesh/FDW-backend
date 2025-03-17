from flask import Blueprint, request, jsonify
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import jwt
from mail import send_reset_password_mail
import bcrypt

# Load environment variables
load_dotenv()

# Create blueprint
forgot_password = Blueprint('forgot_password', __name__)

# MongoDB Configuration
client = MongoClient(os.getenv("MONGO_URI"))
db = client.get_default_database()
db_users = db.users
db_signin = db.signin

# JWT secret key for reset tokens
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")  # Use environment variable or default

@forgot_password.route('/forgot-password', methods=['POST'])
def request_password_reset():
    """Handle forgot password requests"""
    try:
        data = request.json
        if not data or 'email' not in data:
            return jsonify({'error': 'Email is required'}), 400

        user_email = data['email']
        
        # Find user by email
        user = db_users.find_one({"mail": user_email})
        if not user:
            return jsonify({'error': 'No account found with this email'}), 404

        # Generate reset token
        token = jwt.encode({
            'user_id': user['_id'],
            'exp': datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
        }, JWT_SECRET, algorithm='HS256')

        # Create reset link
        reset_link = f"http://localhost:5173/reset-password?token={token}"

        # Send email with reset link
        send_reset_password_mail(user_email, reset_link, user['name'])

        return jsonify({
            'message': 'Password reset link has been sent to your email',
            'success': True
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@forgot_password.route('/reset-password', methods=['POST'])
def reset_password():
    """Handle password reset"""
    try:
        data = request.json
        if not data or 'token' not in data or 'new_password' not in data:
            return jsonify({'error': 'Token and new password are required'}), 400

        # Verify token
        try:
            token_data = jwt.decode(data['token'], JWT_SECRET, algorithms=['HS256'])
            user_id = token_data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Reset link has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid reset link'}), 401

        # Hash new password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(data['new_password'].encode('utf-8'), salt)

        # Update password in signin collection
        result = db_signin.update_one(
            {"_id": user_id},
            {"$set": {"password": hashed_password}}
        )

        if result.modified_count:
            return jsonify({
                'message': 'Password has been reset successfully',
                'success': True
            }), 200
        else:
            return jsonify({'error': 'Failed to reset password'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
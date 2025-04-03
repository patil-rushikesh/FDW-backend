import random
import string
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



db_otp = db.otp_verification

def generate_otp(length=6):
    """Generate a random OTP of specified length"""
    return ''.join(random.choices(string.digits, k=length))


@forgot_password.route('/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to user's email for password reset"""
    try:
        data = request.json
        if not data or 'user_id' not in data:
            return jsonify({'error': 'User ID is required'}), 400

        user_id = data['user_id']
        
        # Find user by ID
        user = db_users.find_one({"_id": user_id})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Generate OTP
        otp = generate_otp()
        
        # Store OTP in database with expiration time (15 minutes)
        expiry_time = datetime.utcnow() + timedelta(minutes=15)
        
        # Remove any existing OTP for this user
        db_otp.delete_many({"user_id": user_id})
        
        # Insert new OTP
        db_otp.insert_one({
            "user_id": user_id,
            "otp": otp,
            "expires_at": expiry_time,
            "verified": False
        })
        
        # Send OTP to user's email
        # You need to create a function similar to send_reset_password_mail for OTP
        # Assuming function is called send_otp_mail
        from mail import send_otp_mail
        send_otp_mail(user['mail'], otp, user['name'])
        
        return jsonify({
            'message': 'OTP has been sent to your email',
            'success': True
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    


@forgot_password.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP submitted by user"""
    try:
        data = request.json
        if not data or 'user_id' not in data or 'otp' not in data:
            return jsonify({'error': 'User ID and OTP are required'}), 400

        user_id = data['user_id']
        submitted_otp = data['otp']
        
        # Find the OTP record
        otp_record = db_otp.find_one({
            "user_id": user_id,
            "expires_at": {"$gt": datetime.utcnow()}  # Check if OTP is still valid
        })
        
        if not otp_record:
            return jsonify({'error': 'OTP expired or not found'}), 401
        
        if otp_record['otp'] != submitted_otp:
            return jsonify({'error': 'Invalid OTP'}), 401
        
        # Mark OTP as verified
        db_otp.update_one(
            {"_id": otp_record["_id"]},
            {"$set": {"verified": True}}
        )
        
        # Generate a short-lived token for password reset
        token = jwt.encode({
            'user_id': user_id,
            'otp_verified': True,
            'exp': datetime.utcnow() + timedelta(minutes=5)  # Token expires in 5 minutes
        }, JWT_SECRET, algorithm='HS256')
        
        return jsonify({
            'message': 'OTP verified successfully',
            'token': token,
            'success': True
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@forgot_password.route('/reset-user-password', methods=['POST'])
def reset_user_password():
    """Reset user password after OTP verification"""
    try:
        data = request.json
        if not data or 'token' not in data or 'new_password' not in data:
            return jsonify({'error': 'Token and new password are required'}), 400

        # Verify token
        try:
            token_data = jwt.decode(data['token'], JWT_SECRET, algorithms=['HS256'])
            user_id = token_data['user_id']
            if not token_data.get('otp_verified', False):
                return jsonify({'error': 'OTP verification required'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expired, please verify OTP again'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        # Hash new password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(data['new_password'].encode('utf-8'), salt)

        # Update password in signin collection
        result = db_signin.update_one(
            {"_id": user_id},
            {"$set": {"password": hashed_password}}
        )

        if result.modified_count:
            # Clean up OTP records for this user
            db_otp.delete_many({"user_id": user_id})
            
            return jsonify({
                'message': 'Password has been reset successfully',
                'success': True
            }), 200
        else:
            return jsonify({'error': 'Failed to reset password'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
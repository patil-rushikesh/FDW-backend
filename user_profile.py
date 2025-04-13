from flask import Blueprint, request, jsonify, current_app
from bson.json_util import dumps
import traceback

# Create a Blueprint for user profile operations
user_profile = Blueprint('user_profile', __name__)

@user_profile.route('/update-profile', methods=['PUT'])
def update_user_profile():
    """
    API endpoint to update user profile (name and phone number only)
    Requires: userId, name, phone in request body
    """
    try:
        # Get database references from current_app instead of blueprint
        db_users = current_app.config.get('db_users')
        if db_users is None:  # Changed from 'if not db_users:'
            return jsonify({"error": "Database configuration error"}), 500
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
            
        # Check if required fields are present
        required_fields = ["userId", "name", "phone"]
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400
            
        user_id = data["userId"]
        
        # Only allow updating name and phone
        update_fields = {
            "name": data["name"],
            "mob": data["phone"]
        }
        
        # Update in users collection
        result = db_users.update_one(
            {"_id": user_id},
            {"$set": update_fields}
        )
        
        if result.matched_count == 0:
            return jsonify({"error": "User not found"}), 404
            
        if result.modified_count == 0:
            return jsonify({"message": "No changes made"}), 200
            
        return jsonify({
            "message": "Profile updated successfully",
            "updated": {
                "name": data["name"],
                "phone": data["phone"]
            }
        }), 200
            
    except Exception as e:
        print(f"Error updating user profile: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Get user profile information
@user_profile.route('/<string:user_id>', methods=['GET'])
def get_user_profile(user_id):
    """
    API endpoint to fetch user profile information
    """
    try:
        # Get database reference from current_app
        db_users = current_app.config.get('db_users')
        if db_users is None:  # Changed from 'if not db_users:'
            return jsonify({"error": "Database configuration error"}), 500
            
        user = db_users.find_one({"_id": user_id})
        if user is None:  # Changed from 'if not user:'
            return jsonify({"error": "User not found"}), 404
            
        # Return only necessary profile fields
        profile_data = {
            "userId": user["_id"],
            "name": user.get("name", ""),
            "department": user.get("dept", ""),
            "position": user.get("role", ""),
            "email": user.get("mail", ""),
            "phone": user.get("mob", ""),
            "designation": user.get("desg", "Faculty")
        }
            
        return dumps(profile_data), 200
            
    except Exception as e:
        print(f"Error fetching user profile: {str(e)}")
        return jsonify({"error": str(e)}), 500
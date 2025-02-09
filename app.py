from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from bson.json_util import dumps
import os
import bcrypt
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

db_users = mongo.db.users  # Users Collection
db_signin = mongo.db.signin  # Signin Collection

# Health check endpoint
@app.route('/', methods=['GET'])
def test():
    return jsonify({"message": "Welcome to FDW project"}), 200

# Create a new user and add them to both users and signin collections
@app.route('/users', methods=['POST'])
def add_user():
    data = request.json
    if not data or not all(k in data for k in ["_id", "name", "role", "dept", "mail", "mob"]):
        return jsonify({"error": "Missing required fields"}), 400
    
    try:
        # Insert into users collection
        db_users.insert_one(data)
        
        # Hash the password (use _id as the password initially)
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(data["_id"].encode('utf-8'), salt)
        
        # Insert into signin collection
        signin_data = {"_id": data["_id"], "password": hashed_password}
        db_signin.insert_one(signin_data)
        
        return jsonify({"message": "User added successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get all users
@app.route('/users', methods=['GET'])
def get_users():
    users = db_users.find()
    return dumps(users), 200

# Get a single user by ID
@app.route('/users/<string:user_id>', methods=['GET'])
def get_user(user_id):
    user = db_users.find_one({"_id": user_id})
    if user:
        return dumps(user), 200
    return jsonify({"error": "User not found"}), 404

# Update a user by ID
@app.route('/users/<string:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.json
    updated_data = {k: v for k, v in data.items() if k in ["name", "role", "dept", "mail", "mob"]}
    
    if not updated_data:
        return jsonify({"error": "No valid fields to update"}), 400
    
    result = db_users.update_one({"_id": user_id}, {"$set": updated_data})
    
    if result.modified_count:
        return jsonify({"message": "User updated successfully"}), 200
    return jsonify({"error": "User not found or no changes made"}), 404

# Delete a user by ID
@app.route('/users/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    result = db_users.delete_one({"_id": user_id})
    db_signin.delete_one({"_id": user_id})  # Also remove from signin collection
    if result.deleted_count:
        return jsonify({"message": "User deleted successfully"}), 200
    return jsonify({"error": "User not found"}), 404

# Migrate all users from users collection to signin collection
@app.route('/migrate_users', methods=['POST'])
def migrate_users():
    users = db_users.find()
    migrated_count = 0
    
    for user in users:
        user_id = user["_id"]
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user_id.encode('utf-8'), salt)
        
        if not db_signin.find_one({"_id": user_id}):
            db_signin.insert_one({"_id": user_id, "password": hashed_password})
            migrated_count += 1
    
    return jsonify({"message": f"Migrated {migrated_count} users to signin collection"}), 200

if __name__ == '__main__':
    app.run(debug=True)

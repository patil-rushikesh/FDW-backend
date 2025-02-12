from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from bson.json_util import dumps
import os
import bcrypt
from dotenv import load_dotenv
from mail import send_username_password_mail
from flask_cors import CORS  # Add this import

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:5173"],  # Your React app's URL
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.config["MONGO_URI_FDW"] = os.getenv("MONGO_URI_FDW")

mongo = PyMongo(app, uri=app.config["MONGO_URI"])
mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])

# Collections
db_users = mongo.db.users
db_signin = mongo.db.signin

# Department-based collections in the FDW database
department_collections = {
    "AIML": mongo_fdw.db.AIML,
    "ASH": mongo_fdw.db.ASH,
    "Civil": mongo_fdw.db.Civil,
    "Computer": mongo_fdw.db.Computer,
    "Computer(Regional)": mongo_fdw.db.Computer_Regional,
    "ENTC": mongo_fdw.db.ENTC,
    "IT": mongo_fdw.db.IT,
    "Mechanical": mongo_fdw.db.Mechanical
}

# Health check
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"message": "Welcome to FDW project"}), 200

# Create a new user
@app.route('/users', methods=['POST'])
def add_user():
    data = request.json
    required_fields = ["_id", "name", "role", "dept", "mail", "mob"]

    if not data or not all(k in data for k in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        # Insert into users collection
        db_users.insert_one(data)

        # Hash the password (use _id as the password initially)
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(data["_id"].encode('utf-8'), salt)

        # Insert into signin collection
        db_signin.insert_one({"_id": data["_id"], "password": hashed_password})

        # Get the correct department collection
        department = data["dept"]
        collection = department_collections.get(department)

        if collection is not None:
            collection.update_one(
                {"_id": "lookup"},
                {"$set": {f"data.{data['_id']}": data["role"]}},
                upsert=True
            )

            return jsonify({"message": f"User added successfully to {department}"}), 201
        else:
            return jsonify({"error": "Invalid department"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get all users
@app.route('/users', methods=['GET'])
def get_users():
    users = db_users.find()
    return dumps(users), 200

# Get a user by ID
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
    allowed_fields = ["name", "role", "dept", "mail", "mob"]
    updated_data = {k: v for k, v in data.items() if k in allowed_fields}

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
    db_signin.delete_one({"_id": user_id})  # Remove from signin collection
    
    if result.deleted_count:
        return jsonify({"message": "User deleted successfully"}), 200
    return jsonify({"error": "User not found"}), 404

# Migrate all users to signin collection
@app.route('/migrate_users', methods=['POST'])
def migrate_users():
    users = db_users.find()
    migrated_count = 0

    for user in users:
        user_id = user["_id"]
        if not db_signin.find_one({"_id": user_id}):
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(user_id.encode('utf-8'), salt)
            db_signin.insert_one({"_id": user_id, "password": hashed_password})
            migrated_count += 1
        department = user["dept"]
        collection = department_collections.get(department)
        if collection is not None:
            collection.update_one(
                {"_id": "lookup"},
                {"$set": {f"data.{user_id}": user["role"]}},
                upsert=True
            )
            

    return jsonify({"message": f"Migrated {migrated_count} users to signin collection"}), 200

# User login
@app.route('/login', methods=['POST', 'OPTIONS'])  # Added OPTIONS method
def login():
    # Handle preflight request
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response

    data = request.json
    if not data or not all(k in data for k in ["_id", "password"]):
        return jsonify({"error": "Missing required fields"}), 400

    user = db_signin.find_one({"_id": data["_id"]})
    if user and bcrypt.checkpw(data["password"].encode('utf-8'), user["password"]):
        user_data = db_users.find_one({"_id": data["_id"]})
        response = app.response_class(
            response=dumps(user_data),
            status=200,
            mimetype='application/json'
        )
        return response

    return jsonify({"error": "Invalid credentials"}), 401



#Section Data Adding Start here
@app.route('/<department>/<user_id>/A', methods=['POST'])
def handle_post_A(department, user_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
        
        # Access the collection named after the department
        collection = department_collections.get(department)
        
        #first we have to verify from lookup that the user exist in that department or not then only add data
        
        
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        
        lookup = collection.find_one({"_id": "lookup"}).get("data")
        print(lookup)
        if lookup is None:
            return jsonify({"error": "Invalid department"}), 400
        user = lookup.get(user_id)
        if user is None:
            return jsonify({"error": "Invalid user"}), 400
        
        # Update the document for the given user_id
        result = collection.update_one(
            {"_id": user_id},
            {"$set": {"A": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/<user_id>/A', methods=['GET'])
def get_section_A(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("A"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
        

#Section B Data Adding Start here
@app.route('/<department>/<user_id>/B', methods=['POST'])
def handle_post_B(department, user_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
        
        # Access the collection named after the department
        collection = department_collections.get(department)
        
        #first we have to verify from lookup that the user exist in that department or not then only add data
        
        
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        
        lookup = collection.find_one({"_id": "lookup"}).get("data")
        print(lookup)
        if lookup is None:
            return jsonify({"error": "Invalid department"}), 400
        user = lookup.get(user_id)
        if user is None:
            return jsonify({"error": "Invalid user"}), 400
        
        # Update the document for the given user_id
        result = collection.update_one(
            {"_id": user_id},
            {"$set": {"B": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/<user_id>/B', methods=['GET'])
def get_section_B(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("B"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#Section C Data Adding Start here
@app.route('/<department>/<user_id>/C', methods=['POST'])
def handle_post_C(department, user_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
        
        # Access the collection named after the department
        collection = department_collections.get(department)
        
        #first we have to verify from lookup that the user exist in that department or not then only add data
        
        
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        
        lookup = collection.find_one({"_id": "lookup"}).get("data")
        print(lookup)
        if lookup is None:
            return jsonify({"error": "Invalid department"}), 400
        user = lookup.get(user_id)
        if user is None:
            return jsonify({"error": "Invalid user"}), 400
        
        # Update the document for the given user_id
        result = collection.update_one(
            {"_id": user_id},
            {"$set": {"C": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/<user_id>/C', methods=['GET'])
def get_section_C(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("C"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
                
#Section B Data Adding Start here
@app.route('/<department>/<user_id>/D', methods=['POST'])
def handle_post_D(department, user_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
        
        # Access the collection named after the department
        collection = department_collections.get(department)
        
        #first we have to verify from lookup that the user exist in that department or not then only add data
        
        
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        
        lookup = collection.find_one({"_id": "lookup"}).get("data")
        print(lookup)
        if lookup is None:
            return jsonify({"error": "Invalid department"}), 400
        user = lookup.get(user_id)
        if user is None:
            return jsonify({"error": "Invalid user"}), 400
        
        # Update the document for the given user_id
        result = collection.update_one(
            {"_id": user_id},
            {"$set": {"D": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/<user_id>/D', methods=['GET'])
def get_section_B(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("D"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        

if __name__ == '__main__':
    app.run(debug=True)
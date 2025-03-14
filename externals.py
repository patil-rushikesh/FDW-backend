from flask import Blueprint, request, jsonify, Flask
from flask_pymongo import PyMongo
from bson.json_util import dumps
import re
import os
import datetime
import bcrypt
from mail import send_username_password_mail

app = Flask(__name__)
externals = Blueprint('externals', __name__)


# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.config["MONGO_URI_FDW"] = os.getenv("MONGO_URI_FDW")

mongo = PyMongo(app, uri=app.config["MONGO_URI"])
mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])

# Collections
db_users = mongo.db.users
db_signin = mongo.db.signin

app.config["MONGO_URI_FDW"] = os.getenv("MONGO_URI_FDW")
mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])

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



def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def validate_mobile(mobile):
    pattern = r'^[0-9]{10}$'
    return re.match(pattern, mobile) is not None

def generate_external_id(collection):
    """Generate unique external ID in format EXT2425001"""
    try:
        # Get current academic year
        current_year = datetime.datetime.now().year
        year_code = f"{str(current_year)[2:]}{str(current_year + 1)[2:]}"  # "2425"
        
        # Find the latest external reviewer document to get the last used number
        externals_doc = collection.find_one({"_id": "externals"})
        if not externals_doc or 'reviewers' not in externals_doc:
            next_number = 1
        else:
            # Find max number from existing IDs
            existing_ids = [r.get('_id', 'EXT0000000') for r in externals_doc.get('reviewers', [])]
            max_number = max([int(id[-3:]) for id in existing_ids if id.startswith(f'EXT{year_code}')] or [0])
            next_number = max_number + 1

        # Format the ID
        return f"EXT{year_code}{str(next_number).zfill(3)}"
    except Exception as e:
        print(f"Error generating external ID: {str(e)}")
        raise

@externals.route('/<department>/create-external', methods=['POST'])
def create_external(department):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate required fields
        required_fields = ["full_name", "email", "mobile_no", "designation", "specialization", "organization"]
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Validate email format
        if not validate_email(data['email']):
            return jsonify({"error": "Invalid email format"}), 400

        # Validate mobile number
        if not validate_mobile(data['mobile_no']):
            return jsonify({"error": "Invalid mobile number format. Must be 10 digits"}), 400

        # Get department collection
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Generate unique external ID
        external_id = generate_external_id(collection)

        # Create external reviewer document
        external_doc = {
            "_id": external_id,
            "full_name": data['full_name'],
            "mail": data['mail'],
            "mob": data['mob'],
            "desg": data['desg'],
            "specialization": data['specialization'],
            "organization": data['organization'],
            "address": data.get('address', ''),  # Optional field
            "isExternal": True,  # Add isExternal flag
            "dept": department  # Add department info
        }

        # Add to signin collection with password same as ID
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(external_id.encode('utf-8'), salt)
        db_signin.insert_one({"_id": external_id, "password": hashed_password})

        # Add to db_users collection
        user_doc = {
            **external_doc,  # Include all fields from external_doc
            "role": "external",  # Add role
            "isExternal": True,  # Add isExternal flag
            "facultyToReview": []  # Initialize empty list for faculty assignments
        }
        db_users.insert_one(user_doc)

        # Update or create externals document in department collection
        result = collection.update_one(
            {"_id": "externals"},
            {"$push": {"reviewers": external_doc}},
            upsert=True
        )

        # Send credentials via email
        # email_sent = send_username_password_mail(
        #     data['email'],
        #     external_id,
        #     external_id  # Password is same as ID
        # )

        if result.modified_count > 0 or result.upserted_id:
            return jsonify({
                "message": "External reviewer added successfully",
                "data": external_doc,
                # "credentials_sent": email_sent
            }), 201
        else:
            return jsonify({"error": "Failed to add external reviewer"}), 400

    except Exception as e:
        print(f"Error creating external reviewer: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Add this new route after your existing code
@externals.route('/<department>/get-externals', methods=['GET'])
def get_externals(department):
    try:
        # Get department collection
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Find the externals document
        externals_doc = collection.find_one({"_id": "externals"})
        if not externals_doc:
            return jsonify({"message": "No external reviewers found", "data": []}), 200

        # Return the list of reviewers
        return jsonify({
            "message": "External reviewers retrieved successfully",
            "data": externals_doc.get('reviewers', [])
        }), 200

    except Exception as e:
        print(f"Error retrieving external reviewers: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/assign-externals', methods=['POST'])
def assign_externals(department):
    """
    Updated JSON format:
    {
        "external_assignments": {
            "EXT2425001": ["faculty_id1", "faculty_id2"],
            "EXT2425002": ["faculty_id3", "faculty_id4"]
        }
    }
    """
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        data = request.get_json()
        if not data or 'external_assignments' not in data:
            return jsonify({"error": "Missing external assignments"}), 400

        # Get existing externals document
        externals_doc = collection.find_one({"_id": "externals"})
        if not externals_doc or 'reviewers' not in externals_doc:
            return jsonify({"error": "No external reviewers found"}), 404

        # Create assignments structure using external IDs
        assignments = {}
        for reviewer in externals_doc['reviewers']:
            external_id = reviewer['_id']
            if external_id in data['external_assignments']:
                faculty_list = []
                for faculty_id in data['external_assignments'][external_id]:
                    faculty = db_users.find_one({"_id": faculty_id})
                    if faculty:
                        faculty_list.append({
                            "_id": faculty_id,
                            "name": faculty.get("name", "Unknown"),
                            "isReviewed": False
                        })
                assignments[external_id] = {
                    "reviewer_info": reviewer,
                    "assigned_faculty": faculty_list
                }
                
        print(assignments)

        # Update assignments
        result = collection.update_one(
            {"_id": "externals_assignments"},
            {"$set": assignments},
            upsert=True
        )

    
        return jsonify({
            "message": "External reviewers assigned successfully",
            "assignments": assignments
        }), 200
        
    except Exception as e:
        print(f"Error assigning external reviewers: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/external-assignments', methods=['GET'])
def get_external_assignments(department):
    """Get all external reviewer assignments for a department"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        assignments = collection.find_one({"_id": "externals_assignments"})
        if not assignments:
            return jsonify({
                "message": "No external assignments found",
                "data": {}
            }), 200

        assignments.pop('_id', None)
        return jsonify({
            "message": "External assignments retrieved successfully",
            "data": assignments
        }), 200

    except Exception as e:
        print(f"Error retrieving external assignments: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/external-assignments/<id>', methods=['GET'])
def get_external_specific_assignments(department, id):
    """Get assignments for a specific external reviewer"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        assignments = collection.find_one({"_id": "externals_assignments"})
        if not assignments or id not in assignments:
            return jsonify({
                "message": "No assignments found for this external reviewer",
                "data": {}
            }), 200

        return jsonify({
            "message": "External reviewer assignments retrieved successfully",
            "data": assignments[id]
        }), 200

    except Exception as e:
        print(f"Error retrieving external reviewer assignments: {str(e)}")
        return jsonify({"error": str(e)}), 500
    

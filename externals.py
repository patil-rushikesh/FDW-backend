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
        required_fields = ["full_name", "mail", "mob", "desg", "specialization", "organization"]
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Validate email format
        if not validate_email(data['mail']):
            return jsonify({"error": "Invalid email format"}), 400

        # Validate mobile number
        if not validate_mobile(data['mob']):
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

        return jsonify({
            "message": "External reviewer added successfully",
            "data": external_doc,
            # "credentials_sent": email_sent
        }), 201
        

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
    

@externals.route('/<department>/dean-external-assignment/<external_id>/<dean_id>', methods=['POST'])
def dean_external_assignment(department, external_id, dean_id):
    """Creating the map creating relation between dean and external reviewer
    also assigning the same verifying faculty to dean as external reviewer
    """
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get external reviewer assignments
        assignments = collection.find_one({"_id": "externals_assignments"})
        if not assignments or external_id not in assignments:
            return jsonify({
                "error": "No assignments found for this external reviewer"
            }), 404

        # Get dean from users collection
        dean = db_users.find_one({"_id": dean_id})
        if not dean:
            return jsonify({"error": "Dean not found"}), 404

        # Create dean assignments using external reviewer's faculty list
        external_assignments = assignments[external_id]
        dean_assignments = {
            dean_id: {
                "reviewer_info": {
                    "_id": dean_id,
                    "full_name": dean.get("name", "Unknown"),
                    "mail": dean.get("mail", ""),
                    "isExternal": False,
                    "isDean": True
                },
                "assigned_faculty": external_assignments["assigned_faculty"]
            }
        }

        # Update or create dean assignments document
        result = collection.update_one(
            {"_id": "dean_assignments"},
            {"$set": {dean_id: dean_assignments[dean_id]}},
            upsert=True
        )

        # Create mapping between dean and external reviewer
        dean_external_mapping = {
            
            external_id : dean_id,
        }

        collection.update_one(
            {"_id": "dean_external_mappings"},
            {"$push": {"mappings": dean_external_mapping}},
            upsert=True
        )

        return jsonify({
            "message": "Dean-External mapping created successfully",
            "dean_assignments": dean_assignments,
            "mapping": dean_external_mapping
        }), 200

    except Exception as e:
        print(f"Error creating dean-external assignment: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/dean-external-mappings', methods=['GET'])
def get_dean_external_mappings(department):
    """Get all dean to external reviewer mappings for a department"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get the mappings document
        mappings_doc = collection.find_one({"_id": "dean_external_mappings"})
        if not mappings_doc or 'mappings' not in mappings_doc:
            return jsonify({
                "message": "No dean-external mappings found",
                "data": []
            }), 200

        # Get reviewer and dean details for each mapping
        detailed_mappings = []
        for mapping in mappings_doc['mappings']:
            external_id = mapping['external_id']
            dean_id = mapping['dean_id']
            
            # Get dean details
            dean = db_users.find_one({"_id": dean_id})
            # Get external details
            external = db_users.find_one({"_id": external_id})
            
            detailed_mappings.append({
                "dean": {
                    "id": dean_id,
                    "name": dean.get("name", "Unknown") if dean else "Unknown",
                    "mail": dean.get("mail", "")
                },
                "external": {
                    "id": external_id,
                    "name": external.get("full_name", "Unknown") if external else "Unknown",
                    "mail": external.get("mail", "")
                }
            })

        return jsonify({
            "message": "Dean-External mappings retrieved successfully",
            "data": detailed_mappings
        }), 200

    except Exception as e:
        print(f"Error retrieving dean-external mappings: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/dean-assignments/<dean_id>', methods=['GET'])
def get_dean_assignments(department, dean_id):
    """Get faculty assignments for a specific dean"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get dean assignments document
        assignments = collection.find_one({"_id": "dean_assignments"})
        if not assignments or dean_id not in assignments:
            return jsonify({
                "message": "No assignments found for this dean",
                "data": {}
            }), 200

        # Get dean details from users collection
        dean = db_users.find_one({"_id": dean_id})
        if not dean:
            return jsonify({"error": "Dean not found"}), 404

        return jsonify({
            "message": "Dean assignments retrieved successfully",
            "data": assignments[dean_id]
        }), 200

    except Exception as e:
        print(f"Error retrieving dean assignments: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/assign-interaction-deans', methods=['POST'])
def assign_interaction_deans(department):
    """Assign deans to a department for interaction"""
    try:
        data = request.get_json()
        if not data or 'dean_ids' not in data:
            return jsonify({
                "error": "Missing required field: dean_ids list"
            }), 400

        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        dean_assignments = []
        for dean_id in data['dean_ids']:
            # Verify dean exists and is actually a dean
            dean = db_users.find_one({"_id": dean_id, "role": "Dean"})
            if not dean:
                continue  # Skip invalid deans

            # Add department to dean's interaction list
            db_users.update_one(
                {"_id": dean_id},
                {
                    "$set": {"isAddedForInteraction": True},
                    "$addToSet": {"interactionDepartments": department}
                }
            )

            dean_assignments.append({
                "_id": dean_id,
                "name": dean.get("name", "Unknown"),
                "mail": dean.get("mail", ""),
                "dept": dean.get("dept", "Unknown")
            })

        # Update department's interaction deans list
        collection.update_one(
            {"_id": "interaction_deans"},
            {"$set": {"deans": dean_assignments}},
            upsert=True
        )

        return jsonify({
            "message": f"Deans assigned successfully to {department} department",
            "assigned_deans": dean_assignments
        }), 200

    except Exception as e:
        print(f"Error assigning deans for interaction: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/interaction-deans', methods=['GET'])
def get_department_interaction_deans(department):
    """Get all deans assigned for interaction in a department"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        interaction_doc = collection.find_one({"_id": "interaction_deans"})
        if not interaction_doc:
            return jsonify({
                "message": "No deans assigned for interaction",
                "department": department,
                "deans": []
            }), 200

        return jsonify({
            "message": "Interaction deans retrieved successfully",
            "department": department,
            "deans": interaction_doc.get("deans", [])
        }), 200

    except Exception as e:
        print(f"Error retrieving interaction deans: {str(e)}")
        return jsonify({"error": str(e)}), 500

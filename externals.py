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

def check_and_update_review_completion(collection, faculty_id):
    """Check if all three reviews are present and update status"""
    try:
        # Get marks document
        marks_doc = collection.find_one(
            {"_id": "interaction_marks"},
        )

        if not marks_doc or faculty_id not in marks_doc:
            return False

        faculty_marks = marks_doc[faculty_id]
        
        # Check if all three reviews exist
        has_external = bool(faculty_marks.get("external_marks", {}).get("marks"))
        has_dean = bool(faculty_marks.get("dean_marks", {}).get("marks"))
        has_hod = bool(faculty_marks.get("hod_marks"))

        if has_external and has_dean and has_hod:
            # Update faculty document status
            collection.update_one(
                {"_id": faculty_id},
                {
                    "$set": {
                        "interaction_review_status": "completed",
                        "status": "done"  # Update the main status field
                    }
                }
            )

            # Update interaction_marks document status
            collection.update_one(
                {"_id": "interaction_marks"},
                {"$set": {f"{faculty_id}.review_status": "completed"}}
            )

            # Update externals_assignments status
            collection.update_many(
                {"_id": "externals_assignments"},
                {"$set": {"assigned_faculty.$[elem].review_status": "completed"}},
                array_filters=[{"elem._id": faculty_id}]
            )

            return True
        return False

    except Exception as e:
        print(f"Error checking review completion: {str(e)}")
        return False


def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def validate_mobile(mobile):
    pattern = r'^[0-9]{10}$'
    return re.match(pattern, mobile) is not None

def generate_external_id(collection, department):
    """Generate unique external ID in format EXT2425001"""
    try:
        # Get current academic year
        current_year = datetime.datetime.now().year
        year_code = f"{str(current_year)[2:]}{str(current_year + 1)[2:]}"  # "2425"
        
        # Convert department to uppercase and take first 4 letters
        dept_code = department.upper()[:4]
        
        # Find the latest external reviewer document to get the last used number
        externals_doc = collection.find_one({"_id": "externals"})
        if not externals_doc or 'reviewers' not in externals_doc:
            next_number = 1
        else:
            # Find max number from existing IDs
            existing_ids = [r.get('_id', 'EXT0000000') for r in externals_doc.get('reviewers', [])]
            max_number = max([int(id[-3:]) for id in existing_ids if id.startswith(f'EXT{dept_code}{year_code}')] or [0])
            next_number = max_number + 1

        # Format the ID
        return f"EXT{dept_code}{year_code}{str(next_number).zfill(3)}"
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
        external_id = generate_external_id(collection, department)

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
        email_sent = send_username_password_mail(
            data['mail'],
            external_id,
            external_id,
            data['full_name']  # Password is same as ID
        )

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
                            "isReviewed": False,
                            "isHodMarksGiven": False,
                            "total_marks": 0
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
    """Creating the map between dean and external reviewer with assignments"""
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

        # Get existing dean assignments
        existing_assignments = collection.find_one({"_id": "dean_assignments"})
        
        # Create or update dean info
        dean_info = {
            "_id": dean_id,
            "full_name": dean.get("name", "Unknown"),
            "mail": dean.get("mail", ""),
            "isExternal": False,
            "isDean": True
        }

        # Get external assignments
        external_assignments = assignments[external_id]["assigned_faculty"]

        if existing_assignments and dean_id in existing_assignments:
            # Update existing dean's assignments
            collection.update_one(
                {"_id": "dean_assignments"},
                {
                    "$set": {
                        f"{dean_id}.reviewer_info": dean_info
                    },
                    "$set": {
                        f"{dean_id}.{external_id}": external_assignments
                    }
                }
            )
        else:
            # Create new dean assignments
            collection.update_one(
                {"_id": "dean_assignments"},
                {
                    "$set": {
                        f"{dean_id}": {
                            "reviewer_info": dean_info,
                            external_id: external_assignments
                        }
                    }
                },
                upsert=True
            )

        # Create or update mapping
        mapping_doc = {
            external_id: dean_id,
            "timestamp": datetime.datetime.now()
        }

        collection.update_one(
            {"_id": "dean_external_mappings"},
            {"$push": {"mappings": mapping_doc}},
            upsert=True
        )

        # Get updated assignments for response
        updated_assignments = collection.find_one(
            {"_id": "dean_assignments"},
            {dean_id: 1}
        )

        return jsonify({
            "message": "Dean-External mapping created successfully",
            "dean_assignments": updated_assignments[dean_id],
            "mapping": mapping_doc
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

        # Get dean assignments for verification
        dean_assignments = collection.find_one({"_id": "dean_assignments"})
        
        # Get detailed mappings with verification status
        detailed_mappings = []
        for mapping in mappings_doc['mappings']:
            external_id = list(mapping.keys())[0]  # Get external ID
            dean_id = mapping[external_id]         # Get dean ID
            
            # Get dean details
            dean = db_users.find_one({"_id": dean_id})
            # Get external details
            external = db_users.find_one({"_id": external_id})
            

            detailed_mappings.append({
                "dean": {
                    "id": dean_id,
                    "name": dean.get("name", "Unknown") if dean else "Unknown",
                    "mail": dean.get("mail", ""),
                    "department": dean.get("dept", "Unknown") if dean else "Unknown"
                },
                "external": {
                    "id": external_id,
                    "name": external.get("full_name", "Unknown") if external else "Unknown",
                    "mail": external.get("mail", ""),
                    "organization": external.get("organization", "Unknown")
                }
            })

        return jsonify({
            "message": "Dean-External mappings retrieved successfully",
            "department": department,
            "total_mappings": len(detailed_mappings),
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
            dean = db_users.find_one({"_id": dean_id, "desg": "Dean"})
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


@externals.route('/<department>/external_interaction_marks/<external_id>/<faculty_id>', methods=['POST'])
def externalFacultyMarks(department,external_id,faculty_id) : 
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        faculty_collection = collection.find_one({"_id": faculty_id})
        if not faculty_collection:
            return jsonify({"error": "Faculty not found"}), 404
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        if 'total_marks' not in data:
            return jsonify({"error": "Missing required field: marks"}), 400
        total_marks = data['total_marks']
        comments = data.get('comments', '')  # Get comments from request data, default empty string
        
        collection.update_one(
            {"_id": faculty_id},
            {"$set": {
                "total_marks_by_external_for_interaction": total_marks,
                "comments_by_external_for_interaction": comments
            }}
        )
        
        collection.update_one(
            {"_id": "interaction_marks"},
            {
                "$set": {
                    f"{faculty_id}.external_marks": {
                        "external_id": external_id,
                        "marks": total_marks,
                        "comments": comments
                    }
                }
            },
            upsert=True
        )

        # Update external assignments document
        collection.update_one(
            {"_id": "externals_assignments"},
            {
                "$set": {
                    f"{external_id}.assigned_faculty.$[elem].isReviewed": True,
                    f"{external_id}.assigned_faculty.$[elem].total_marks": total_marks,
                    f"{external_id}.assigned_faculty.$[elem].comments": comments
                }
            },
            array_filters=[{"elem._id": faculty_id}]
        )
        isCompleted = check_and_update_review_completion(collection, faculty_id)
        if isCompleted : 
            collection.update_one(
            {"_id": faculty_id},
            {"$set": {
                "status": "done"
            }}
        )
        return jsonify({"message": "Marks and comments updated successfully"}), 200
    except Exception as e:
        print(f"Error updating marks and comments: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@externals.route('/<department>/dean_interaction_marks/<dean_id>/<faculty_id>/<external_id>', methods=['POST'])
def deanFacultyMarks(department,dean_id,faculty_id,external_id) :
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        faculty_collection = collection.find_one({"_id": faculty_id})
        if not faculty_collection:
            return jsonify({"error": "Faculty not found"}), 404
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        if 'total_marks' not in data:
            return jsonify({"error": "Missing required field: marks"}), 400
        total_marks = data['total_marks']
        comments = data.get('comments', '')  # Get comments from request data, default empty string
        
        collection.update_one(
            {"_id": faculty_id},
            {"$set": {
                "total_marks_by_dean_for_interaction": total_marks,
                "comments_by_dean_for_interaction": comments
            }}
        )
        collection.update_one(
            {"_id": "interaction_marks"},
            {
                "$set": {
                    f"{faculty_id}.dean_marks": {
                        "dean_id": dean_id,
                        "marks": total_marks,
                        "comments": comments
                    }
                }
            },
            upsert=True
        )
        collection.update_one(
            {"_id": "dean_assignments"},
            {
                "$set": {
                    f"{dean_id}.{external_id}.$[elem].isReviewed": True,
                    f"{dean_id}.{external_id}.$[elem].total_marks": total_marks,
                    f"{dean_id}.{external_id}.$[elem].comments": comments
                }
            },
            array_filters=[{"elem._id": faculty_id}],
            upsert=True
        )
        isCompleted = check_and_update_review_completion(collection, faculty_id)
        if isCompleted : 
            collection.update_one(
            {"_id": faculty_id},
            {"$set": {
                "status": "done"
            }}
        )
        return jsonify({"message": "Marks and comments updated successfully"}), 200
    except Exception as e:
        print(f"Error updating marks and comments: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@externals.route('/<department>/hod_interaction_marks/<external_id>/<faculty_id>', methods=['POST'])
def facultyHodMarks(department,external_id, faculty_id):
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        faculty_collection = collection.find_one({"_id": faculty_id})
        if not faculty_collection:
            return jsonify({"error": "Faculty not found"}), 404
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        if 'total_marks' not in data:
            return jsonify({"error": "Missing required field: marks"}), 400
        
        total_marks = data['total_marks']
        comments = data.get('comments', '')  # Get comments from request data, default empty string
        
        # Update faculty document with marks and comments
        collection.update_one(
            {"_id": faculty_id},
            {"$set": {
                "total_marks_by_hod_for_interaction": total_marks,
                "comments_by_hod_for_interaction": comments
            }}
        )
        collection.update_one(
            {"_id": "externals_assignments"},
            {
                "$set": {
                    f"{external_id}.assigned_faculty.$[elem].hod_total_marks": total_marks,
                    f"{external_id}.assigned_faculty.$[elem].isHodMarksGiven": True,
                    }
            },
            array_filters=[{"elem._id": faculty_id}]
        )

        
        # Update interaction_marks document with marks and comments
        collection.update_one(
            {"_id": "interaction_marks"},
            {
                "$set": {
                    f"{faculty_id}.hod_marks": total_marks,
                    f"{faculty_id}.hod_comments": comments
                }
            },
            upsert=True
        )
        
        # Update HOD-specific marks document with marks and comments
        collection.update_one(
            {"_id": "interaction-mark-by-hod"},
            {"$set": {
                f"{faculty_id}.marks": total_marks,
                f"{faculty_id}.comments": comments
            }},
            upsert=True
        )
        isCompleted = check_and_update_review_completion(collection, faculty_id)
        if isCompleted : 
            collection.update_one(
            {"_id": faculty_id},
            {"$set": {
                "status": "done"
            }}
        )
        
        return jsonify({"message": "Marks and comments updated successfully"}), 200
    except Exception as e:
        print(f"Error updating marks and comments: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/hod_interaction_marks/<faculty_id>', methods=['GET'])
def get_hod_interaction_marks(department, faculty_id):
    """Get HOD interaction marks for a specific faculty"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get marks from HOD marks document
        hod_marks = collection.find_one({"_id": "interaction-mark-by-hod"})
        if not hod_marks or faculty_id not in hod_marks:
            return jsonify({
                "message": "No HOD marks found for this faculty",
                "data": None
            }), 200

        return jsonify({
            "message": "HOD marks retrieved successfully",
            "faculty_id": faculty_id,
            "marks": hod_marks[faculty_id]
        }), 200

    except Exception as e:
        print(f"Error retrieving HOD marks: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/all_interaction_marks/<faculty_id>', methods=['GET'])
def get_all_interaction_marks(department, faculty_id):
    """Get all interaction marks (HOD, Dean, External) for a specific faculty"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get consolidated marks document
        marks_doc = collection.find_one(
            {"_id": "interaction_marks"},
            {faculty_id: 1}
        )

        if not marks_doc or faculty_id not in marks_doc:
            return jsonify({
                "message": "No marks found for this faculty",
                "data": {}
            }), 200

        faculty_marks = marks_doc[faculty_id]

        # Get faculty details
        faculty = db_users.find_one({"_id": faculty_id})
        faculty_name = faculty.get("name", "Unknown") if faculty else "Unknown"

        response_data = {
            "faculty_info": {
                "id": faculty_id,
                "name": faculty_name
            },
            "marks": {
                "external": faculty_marks.get("external_marks", {}),
                "dean": faculty_marks.get("dean_marks", {}),
                "hod": faculty_marks.get("hod_marks")
            }
        }

        return jsonify({
            "message": "Interaction marks retrieved successfully",
            "data": response_data
        }), 200

    except Exception as e:
        print(f"Error retrieving interaction marks: {str(e)}")
        return jsonify({"error": str(e)}), 500

@externals.route('/<department>/all_faculties_final_marks', methods=['GET'])
def get_all_faculties_marks(department):
    """Get interaction marks and final calculated marks for all faculties"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get consolidated marks document
        marks_doc = collection.find_one({"_id": "interaction_marks"})
        if not marks_doc:
            return jsonify({
                "message": "No marks found for any faculty",
                "department": department,
                "data": []
            }), 200

        # Get all faculties with status "done" or "SentToDirector"
        completed_faculties = list(collection.find({
            "status": {"$in": ["done", "SentToDirector"]}
        }))
        
        faculty_marks_list = []
        
        for faculty in completed_faculties:
            faculty_id = faculty.get("_id")
            # Skip if faculty_id is not in marks document
            if faculty_id not in marks_doc:
                continue
                
            marks = marks_doc[faculty_id]
            user = db_users.find_one({"_id": faculty_id})
            
            if not user:
                continue
                
            # Basic faculty info
            faculty_data = {
                "faculty_info": {
                    "id": faculty_id,
                    "name": user.get("name", "Unknown"),
                    "designation": faculty.get("desg", "Faculty"),
                    "role": user.get("role", "faculty"),  # Added faculty role
                    "department": department,
                    "status": faculty.get("status", "pending")
                },
                "interaction_marks": {
                    "external": marks.get("external_marks", {
                        "external_id": None,
                        "marks": None,
                        "comments": None
                    }),
                    "dean": marks.get("dean_marks", {
                        "dean_id": None,
                        "marks": None,
                        "comments": None
                    }),
                    "hod": {
                        "marks": marks.get("hod_marks"),
                        "comments": marks.get("hod_comments")
                    }
                }
            }

            # Calculate interaction average
            interaction_marks = []
            if marks.get("external_marks", {}).get("marks"):
                interaction_marks.append(marks["external_marks"]["marks"])
            if marks.get("dean_marks", {}).get("marks"):
                interaction_marks.append(marks["dean_marks"]["marks"])
            if marks.get("hod_marks"):
                interaction_marks.append(marks["hod_marks"])
            
            interaction_avg = sum(interaction_marks) / len(interaction_marks) if interaction_marks else 0
            faculty_data["interaction_marks"]["average"] = round(interaction_avg, 2)
            faculty_data["interaction_marks"]["total_reviews"] = len(interaction_marks)

            # Add final marks calculation if grand_verified_marks exists
            if faculty.get("grand_verified_marks"):
                verified_marks = faculty.get("grand_verified_marks", 0)
                scaled_verified = (verified_marks / 1000) * 850  # Scale verified marks to 85
                scaled_interaction = (interaction_avg / 100) * 150  # Scale interaction to 15
                
                faculty_data["final_marks"] = {
                    "verified_marks": verified_marks,
                    "scaled_verified_marks": round(scaled_verified, 2),
                    "interaction_average": interaction_avg,
                    "scaled_interaction_marks": round(scaled_interaction, 2),
                    "total_marks": round(scaled_verified + scaled_interaction, 2)
                }
            else:
                # Add placeholder for faculty without verified marks
                faculty_data["final_marks"] = {
                    "verified_marks": 0,
                    "scaled_verified_marks": 0,
                    "interaction_average": interaction_avg,
                    "scaled_interaction_marks": round((interaction_avg / 100) * 150, 2),
                    "total_marks": round((interaction_avg / 100) * 150, 2),
                    "missing_verified_marks": True
                }
                
            faculty_marks_list.append(faculty_data)

        # Calculate summary statistics
        completed_reviews = sum(1 for f in faculty_marks_list if f["interaction_marks"]["total_reviews"] == 3)
        partial_reviews = sum(1 for f in faculty_marks_list if 0 < f["interaction_marks"]["total_reviews"] < 3)
        no_reviews = sum(1 for f in faculty_marks_list if f["interaction_marks"]["total_reviews"] == 0)
        final_marks_count = sum(1 for f in faculty_marks_list if "final_marks" in f)
        missing_verified_marks = sum(1 for f in faculty_marks_list if f.get("final_marks", {}).get("missing_verified_marks", False))

        return jsonify({
            "message": "All faculty marks retrieved successfully",
            "department": department,
            "total_faculty": len(faculty_marks_list),
            "data": faculty_marks_list,
            "summary": {
                "total_reviewed": completed_reviews,
                "partially_reviewed": partial_reviews,
                "not_reviewed": no_reviews,
                "final_marks_calculated": final_marks_count,
                "missing_verified_marks": missing_verified_marks
            }
        }), 200

    except Exception as e:
        print(f"Error retrieving all faculty marks: {str(e)}")
        return jsonify({"error": str(e)}), 500


@externals.route('/<department>/all_hod_faculty_marks', methods=['GET'])
def get_all_hod_faculty_marks(department):
    """Get HOD interaction marks for all faculties in a department"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get HOD marks document
        hod_marks_doc = collection.find_one({"_id": "interaction-mark-by-hod"})
        if not hod_marks_doc:
            return jsonify({
                "message": "No HOD marks found for any faculty",
                "department": department,
                "data": []
            }), 200

        # Get all faculty marks with details
        faculty_marks_list = []
        
        for faculty_id, marks in hod_marks_doc.items():
            if faculty_id == "_id":
                continue

            # Get faculty details
            faculty = db_users.find_one({"_id": faculty_id})
            if not faculty:
                continue

            faculty_data = {
                "faculty_info": {
                    "id": faculty_id,
                    "name": faculty.get("name", "Unknown"),
                    "designation": faculty.get("desg", "Faculty"),
                    "department": department,
                    "email": faculty.get("mail", ""),
                },
                "marks": marks,
                "status": "Reviewed"
            }
            
            faculty_marks_list.append(faculty_data)

        # Get all department faculty for checking unreviewed faculty
        all_faculty = db_users.find({"dept": department, "role": "faculty"})
        reviewed_ids = set(f["faculty_info"]["id"] for f in faculty_marks_list)
        
        # Add unreviewed faculty
        for faculty in all_faculty:
            if faculty["_id"] not in reviewed_ids:
                faculty_marks_list.append({
                    "faculty_info": {
                        "id": faculty["_id"],
                        "name": faculty.get("name", "Unknown"),
                        "designation": faculty.get("desg", "Faculty"),
                        "department": department,
                        "email": faculty.get("mail", ""),
                    },
                    "marks": None,
                    "status": "Pending"
                })

        # Sort by faculty name
        faculty_marks_list.sort(key=lambda x: x["faculty_info"]["name"])

        # Calculate statistics
        total_faculty = len(faculty_marks_list)
        reviewed_count = sum(1 for f in faculty_marks_list if f["status"] == "Reviewed")
        pending_count = total_faculty - reviewed_count

        return jsonify({
            "message": "HOD marks for all faculty retrieved successfully",
            "department": department,
            "total_faculty": total_faculty,
            "data": faculty_marks_list,
            "summary": {
                "total_reviewed": reviewed_count,
                "pending_review": pending_count,
                "review_completion": f"{(reviewed_count/total_faculty*100):.2f}%" if total_faculty > 0 else "0%"
            }
        }), 200

    except Exception as e:
        print(f"Error retrieving HOD faculty marks: {str(e)}")
        return jsonify({"error": str(e)}), 500
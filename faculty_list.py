import os
from datetime import datetime, UTC  # Updated import
from flask import Blueprint, Flask, jsonify
from flask_pymongo import PyMongo
from bson import ObjectId

faculty_list = Blueprint('faculty_list', __name__)

app = Flask(__name__)
# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.config["MONGO_URI_FDW"] = os.getenv("MONGO_URI_FDW")

# Initialize MongoDB connections
mongo = PyMongo(app, uri=app.config["MONGO_URI"])
mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])


def calculate_grand_total(data):
    """Calculate grand total and verified marks from all sections"""
    try:
        grand_total = 0
        form_status = "pending"  # Default status

        # Add all sections total marks if they exist
        sections = ['A', 'B', 'C', 'D', 'E']
        for section in sections:
            if section in data and 'total_marks' in data[section]:
                grand_total += float(data[section]['total_marks'])

        return {
            'grand_total_marks': round(grand_total, 2),
            'grand_verified_marks': 0,  # Initialize verified marks as 0
            'status': form_status
        }

    except Exception as e:
        print(f"Error calculating grand total: {str(e)}")
        return {
            'grand_total_marks': 0,
            'grand_verified_marks': 0,
            'status': "error"
        }


@faculty_list.route('/faculty/<department>', methods=['GET'])
def get_faculty_list(department):
    try:
        # Get the department collection
        department_collection = {
            "AIML": mongo_fdw.db.AIML,
            "ASH": mongo_fdw.db.ASH,
            "Civil": mongo_fdw.db.Civil,
            "Computer": mongo_fdw.db.Computer,
            "Computer(Regional)": mongo_fdw.db.Computer_Regional,
            "ENTC": mongo_fdw.db.ENTC,
            "IT": mongo_fdw.db.IT,
            "Mechanical": mongo_fdw.db.Mechanical
        }.get(department)

        if department_collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get the lookup document for the department
        lookup_doc = department_collection.find_one({"_id": "lookup"})
        if not lookup_doc or "data" not in lookup_doc:
            return jsonify({"error": "No faculty found in department"}), 404

        faculty_list = []
        
        # Iterate through faculty in lookup data
        for user_id, role in lookup_doc["data"].items():
            # Get faculty data from department collection
            faculty_data = department_collection.find_one({"_id": user_id})
            
            # Get user profile data from users collection
            user_profile = mongo.db.users.find_one({"_id": user_id})

            if faculty_data and user_profile:
                faculty_info = {
                    "_id": user_id,
                    "name": user_profile.get("name", ""),
                    "role": role,
                    "designation": user_profile.get("desg", "Faculty"),  # Added designation field
                    "grand_marks": faculty_data.get("grand_total", 0),
                    "status": faculty_data.get("status", "pending")
                }
                faculty_list.append(faculty_info)

        return jsonify({
            "status": "success",
            "department": department,
            "faculty_count": len(faculty_list),
            "data": faculty_list
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
    
@faculty_list.route('/total_marks/<department>/<faculty_id>', methods=['GET'])
def get_total_marks(department, faculty_id):
    try:
        # Access Flask app context for MongoDB connections
        from flask import current_app as app
        mongo = PyMongo(app, uri=app.config["MONGO_URI"])
        mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])
        
        # Get the department collection
        department_collection = {
            "AIML": mongo_fdw.db.AIML,
            "ASH": mongo_fdw.db.ASH,
            "Civil": mongo_fdw.db.Civil,
            "Computer": mongo_fdw.db.Computer,
            "Computer(Regional)": mongo_fdw.db.Computer_Regional,
            "ENTC": mongo_fdw.db.ENTC,
            "IT": mongo_fdw.db.IT,
            "Mechanical": mongo_fdw.db.Mechanical
        }.get(department)

        if department_collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get faculty data from department collection
        faculty_data = department_collection.find_one({"_id": faculty_id})
        if not faculty_data:
            # Initialize new faculty document if not found
            initial_faculty_data = {
                "_id": faculty_id,
                "A": {"total_marks": 0, "verified_marks": 0},
                "B": {"total_marks": 0, "verified_marks": 0},
                "C": {"total_marks": 0, "verified_marks": 0},
                "D": {"total_marks": 0, "verified_marks": 0},
                "E": {"total_marks": 0, "verified_marks": 0},
                "grand_total_marks": 0,
                "grand_verified_marks": 0,
                "status": "pending"
            }
            department_collection.insert_one(initial_faculty_data)
            faculty_data = initial_faculty_data

        # Get user profile data
        user_profile = mongo.db.users.find_one({"_id": faculty_id})
        if not user_profile:
            return jsonify({"error": f"User profile for ID {faculty_id} not found"}), 404

        # Calculate grand total using the provided function
        grand_total_data = calculate_grand_total(faculty_data)
        
        # Update the faculty data with new grand total
        department_collection.update_one(
            {"_id": faculty_id},
            {"$set": {
                "grand_total_marks": grand_total_data["grand_total_marks"],
                "grand_verified_marks": grand_total_data["grand_verified_marks"]
            }}
        )
        
        # Extract section totals and verified marks
        section_totals = {
            "A_total": faculty_data.get("A", {}).get("total_marks", 0),
            "A_verified_total": faculty_data.get("A", {}).get("verified_marks", 0),
            "B_total": faculty_data.get("B", {}).get("total_marks", 0),
            "B_verified_total": faculty_data.get("B", {}).get("final_verified_marks", 0),
            "C_total": faculty_data.get("C", {}).get("total_marks", 0),
            "C_verified_total": faculty_data.get("C", {}).get("verified_marks", 0),
            "D_total": faculty_data.get("D", {}).get("total_marks", 0),
            "D_verified_total": faculty_data.get("D", {}).get("verified_marks", 0),
            "E_total": faculty_data.get("E", {}).get("total_marks", 0),
            "E_verified_total": faculty_data.get("E", {}).get("verified_marks", 0)
        }

        # Prepare response data
        faculty_list = {
            "_id": faculty_id,
            "name": user_profile.get("name", ""),
            "department": department,
            "section_totals": section_totals,
            "grand_total_marks": grand_total_data["grand_total_marks"],
            "grand_verified_marks": grand_total_data["grand_verified_marks"],
            "status": faculty_data.get("status", "pending")
        }

        return jsonify({
            "status": "success",
            "data": faculty_list
        }), 200

    except Exception as e:
        print('error', str(e))
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@faculty_list.route('/total_marks/<department>/<faculty_id>', methods=['POST'])
def update_verified_marks(department, faculty_id):
    try:
        from flask import current_app as app, request
        from datetime import datetime, UTC
        mongo = PyMongo(app, uri=app.config["MONGO_URI"])
        mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])
        
        verified_data = request.get_json()
        
        department_collection = {
            "AIML": mongo_fdw.db.AIML,
            "ASH": mongo_fdw.db.ASH,
            "Civil": mongo_fdw.db.Civil,
            "Computer": mongo_fdw.db.Computer,
            "Computer(Regional)": mongo_fdw.db.Computer_Regional,
            "ENTC": mongo_fdw.db.ENTC,
            "IT": mongo_fdw.db.IT,
            "Mechanical": mongo_fdw.db.Mechanical
        }.get(department)

        if department_collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get existing faculty data
        faculty_data = department_collection.find_one({"_id": faculty_id})
        if not faculty_data:
            return jsonify({"error": "Faculty not found"}), 404

        # Calculate totals and prepare update document
        grand_verified_total = 0
        sections = ['A', 'B', 'C', 'D', 'E']
        section_totals = {}

        for section in sections:
            section_data = verified_data.get(section, {})
            verified_marks = float(section_data.get('verified_marks', 0))
            total_marks = float(faculty_data.get(section, {}).get('total_marks', 0))
            
            grand_verified_total += verified_marks
            
            section_totals[section] = {
                "total_marks": total_marks,
                "verified_marks": verified_marks,
                "section_items": section_data.get('section_items', {})
            }

        # Create grand total document
        grand_total_doc = {
            "_id": "grand_total",
            "faculty_data": {
                faculty_id: {
                    "sections": section_totals,
                    "section_wise_totals": {
                        "A_total": section_totals['A']['total_marks'],
                        "A_verified": section_totals['A']['verified_marks'],
                        "B_total": section_totals['B']['total_marks'],
                        "B_verified": section_totals['B']['verified_marks'],
                        "C_total": section_totals['C']['total_marks'],
                        "C_verified": section_totals['C']['verified_marks'],
                        "D_total": section_totals['D']['total_marks'],
                        "D_verified": section_totals['D']['verified_marks'],
                        "E_total": section_totals['E']['total_marks'],
                        "E_verified": section_totals['E']['verified_marks']
                    },
                    "grand_total_marks": sum(section['total_marks'] for section in section_totals.values()),
                    "grand_verified_marks": round(grand_verified_total, 2),
                    "status": "verified",
                    "last_updated": datetime.now(UTC),
                    "department": department
                }
            }
        }

        

        # Update original faculty document
        department_collection.update_one(
            {"_id": faculty_id},
            {
                "$set": {
                    **{f"grand_marks_{section}": section_totals[section] for section in sections},
                    "grand_verified_marks": round(grand_verified_total, 2),
                    "status": "verified"
                }
            }
        )

        return jsonify({
            "status": "success",
            "message": "Marks updated successfully"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@faculty_list.route('/all-faculties', methods=['GET'])
def get_all_faculties():
    """Get faculty information from all departments"""
    try:
        all_faculties = []
        
        # Iterate through all departments
        for dept, collection in department_collections.items():
            # Get the lookup document for the department
            lookup_doc = collection.find_one({"_id": "lookup"})
            if not lookup_doc or "data" not in lookup_doc:
                continue

            # Iterate through faculty in lookup data
            for user_id, role in lookup_doc["data"].items():
                # Get faculty data from department collection
                faculty_data = collection.find_one({"_id": user_id})
                
                # Get user profile data from users collection
                user_profile = db_users.find_one({"_id": user_id})

                if faculty_data and user_profile:
                    faculty_info = {
                        "_id": user_id,
                        "name": user_profile.get("name", ""),
                        "department": dept,
                        "designation": user_profile.get("desg", "Faculty"),
                        "role": role,
                        "status": faculty_data.get("status", "pending")
                    }
                    all_faculties.append(faculty_info)

        return jsonify({
            "status": "success",
            "faculty_count": len(all_faculties),
            "data": all_faculties
        }), 200

    except Exception as e:
        print(f"Error retrieving all faculties: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
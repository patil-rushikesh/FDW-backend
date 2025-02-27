import os
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
    """Calculate grand total from all sections and determine status"""
    try:
        grand_total = 0
        form_status = "pending"  # Default status

        # Add Section A total if exists
        if 'A' in data and 'total_marks' in data['A']:
            grand_total += float(data['A']['total_marks'])

        # Add Section B total if exists
        if 'B' in data and 'total_marks' in data['B']:
            grand_total += float(data['B']['total_marks'])

        # Add Section C total if exists
        if 'C' in data and 'total_marks' in data['C']:
            grand_total += float(data['C']['total_marks'])

        # Add Section D total if exists
        if 'D' in data and 'total_marks' in data['D']:
            grand_total += float(data['D']['total_marks'])

        return {
            'grand_total': round(grand_total, 2),
            'status': form_status
        }

    except Exception as e:
        print(f"Error calculating grand total: {str(e)}")
        return {
            'grand_total': 0,
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
            return jsonify({"error": f"Faculty with ID {faculty_id} not found in {department} department"}), 404

        # Get user profile data
        user_profile = mongo.db.users.find_one({"_id": faculty_id})
        if not user_profile:
            return jsonify({"error": f"User profile for ID {faculty_id} not found"}), 404

        # Calculate grand total using the provided function
        grand_total_data = calculate_grand_total(faculty_data)
        
        # Extract section totals and B section verified marks
        section_totals = {
            "A_total": faculty_data.get("A", {}).get("total_marks", 0),
            "B_total": faculty_data.get("B", {}).get("total_marks", 0),
            "B_verified_total": faculty_data.get("B", {}).get("final_verified_marks", 0),
            "C_total": faculty_data.get("C", {}).get("total_marks", 0),
            "D_total": faculty_data.get("D", {}).get("total_marks", 0)
        }

        # Prepare response data
        faculty_list = {
            "_id": faculty_id,
            "name": user_profile.get("name", ""),
            "department": department,
            "section_totals": section_totals,
            "grand_total": grand_total_data["grand_total"],
            "status": faculty_data.get("status", "pending")
        }

        return jsonify({
            "status": "success",
            "data": faculty_list
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

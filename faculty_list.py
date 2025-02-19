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

        if  department_collection is None:
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
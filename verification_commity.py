from flask import Flask, jsonify, request
from flask_pymongo import PyMongo
import os
from dotenv import load_dotenv
from flask import Blueprint

# Load environment variables
load_dotenv()

app = Flask(__name__)

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.config["MONGO_URI_FDW"] = os.getenv("MONGO_URI_FDW")

# Initialize MongoDB connections
mongo = PyMongo(app, uri=app.config["MONGO_URI"])
mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])

# Collections
db_users = mongo.db.users

# Department collections
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

from flask import Blueprint, jsonify, request

def create_verification_blueprint(mongo_fdw, db_users, department_collections):
    verification_bp = Blueprint('verification', __name__)

    @verification_bp.route('/<department>/verification-committee', methods=['POST'])
    def create_verification_committee(department):
        """Create or update verification committee structure with empty faculty lists"""
        try:
            collection = department_collections.get(department)
            if collection is None:
                return jsonify({"error": "Invalid department"}), 400

            data = request.get_json()
            if not data or 'committee_ids' not in data:
                return jsonify({"error": "Missing committee head IDs"}), 400

            committee_ids = data['committee_ids']
            committee_data = {}

            for committee_id in committee_ids:
                head = db_users.find_one({"_id": committee_id})
                if not head:
                    return jsonify({"error": f"Committee head {committee_id} not found"}), 404
                
                committee_key = f"{head['_id']} ({head['name']})"
                committee_data[committee_key] = []

            result = collection.update_one(
                {"_id": "verification_team"},
                {"$set": committee_data},
                upsert=True
            )

            if result.modified_count > 0 or result.upserted_id:
                return jsonify({
                    "message": "Verification committee created successfully",
                    "department": department,
                    "committee_structure": committee_data
                }), 200
            else:
                return jsonify({"error": "No changes made"}), 400

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @verification_bp.route('/<department>/verification-committee/addfaculties', methods=['POST'])
    def add_faculty_to_committee(department):
        """Add faculty members to committees"""
        try:
            collection = department_collections.get(department)
            if collection is None:
                return jsonify({"error": "Invalid department"}), 400

            data = request.get_json()
            if not data:
                return jsonify({"error": "Missing faculty assignments"}), 400

            existing_doc = collection.find_one({"_id": "verification_team"})
            if not existing_doc:
                return jsonify({"error": "Verification team not found"}), 404

            result = collection.update_one(
                {"_id": "verification_team"},
                {"$set": data}
            )

            if result.modified_count > 0:
                return jsonify({
                    "message": "Faculty members assigned successfully",
                    "assignments": data
                }), 200
            else:
                return jsonify({"error": "No changes made"}), 400

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @verification_bp.route('/<department>/verification-committee', methods=['GET'])
    def get_verification_committee(department):
        """Get verification committee details"""
        try:
            collection = department_collections.get(department)
            if collection is None:
                return jsonify({"error": "Invalid department"}), 400

            committee = collection.find_one({"_id": "verification_team"})
            if not committee:
                return jsonify({"error": "No verification committee found"}), 404

            committee.pop('_id', None)
            return jsonify({
                "department": department,
                "committees": committee
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return verification_bp

app.register_blueprint(create_verification_blueprint(mongo_fdw, db_users, department_collections))

@app.route('/<department>/verification-committee/faculty', methods=['DELETE'])
def remove_faculty_from_committee(department):
    """
    Remove faculty members from the verification committee
    Expected JSON body:
    {
        "committee_id": "string",  # ID of the committee head
        "faculty_ids": ["id1", "id2", ...]  # List of faculty IDs to remove
    }
    """
    try:
        collection = department_collections.get(department)
        if collection is  None:
            return jsonify({"error": "Invalid department"}), 400

        data = request.get_json()
        if not data or 'committee_id' not in data or 'faculty_ids' not in data:
            return jsonify({"error": "Missing required fields"}), 400

        # Get committee head details
        head = db_users.find_one({"_id": data['committee_id']})
        if not head:
            return jsonify({"error": "Committee head not found"}), 404

        committee_key = f"{head['_id']} ({head['name']})"

        # Remove faculty members
        result = collection.update_one(
            {"_id": "verification_team"},
            {"$pullAll": {committee_key: data['faculty_ids']}}
        )

        if result.modified_count > 0:
            return jsonify({
                "message": "Faculty members removed successfully",
                "removed_faculty": data['faculty_ids']
            }), 200
        else:
            return jsonify({"error": "No changes made or committee not found"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/verification-committee', methods=['GET'])
def get_verification_committee(department):
    """Get verification committee details for a department"""
    try:
        collection = department_collections.get(department)
        if  collection is  None:
            return jsonify({"error": "Invalid department"}), 400

        committee = collection.find_one({"_id": "verification_team"})
        if not committee:
            return jsonify({"error": "No verification committee found"}), 404

        committee.pop('_id', None)
        return jsonify(committee), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/verification-committee', methods=['PUT'])
def update_verification_committee(department):
    """
    Update entire verification committee structure
    Expected JSON body:
    {
        "23TCOMP0123 (Aviraj Kale)": ["23TCOMP2202"],
        "23TCOMP0129 (Harshad Karale)": [],
        "23TCOMP0133 (Ashirwad Katkamwar)": [],
        "23TCOMP0255 (Sujit Shaha)": ["23TCOMP0137"]
    }
    """
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing committee data"}), 400

        # Update entire verification team document
        result = collection.update_one(
            {"_id": "verification_team"},
            {"$set": data},
            upsert=True
        )

        if result.modified_count > 0 or result.upserted_id:
            return jsonify({
                "message": "Verification committee updated successfully",
                "committee_structure": data
            }), 200
        else:
            return jsonify({"error": "No changes made"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/verification-committee', methods=['DELETE'])
def delete_verification_committee(department):
    """Delete entire verification committee for a department"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        result = collection.delete_one({"_id": "verification_team"})

        if result.deleted_count > 0:
            return jsonify({
                "message": "Verification committee deleted successfully"
            }), 200
        else:
            return jsonify({"error": "Verification committee not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/verification-committee/<committee_head>', methods=['GET'])
def get_specific_committee(department, committee_head):
    """Get details for a specific committee head"""
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        committee = collection.find_one({"_id": "verification_team"})
        if not committee:
            return jsonify({"error": "No verification committee found"}), 404

        # Find the committee head entry
        for key in committee:
            if committee_head in key:  # Check if committee_head is part of the key
                return jsonify({key: committee[key]}), 200

        return jsonify({"error": "Committee head not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
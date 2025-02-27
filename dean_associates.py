import logging
from flask import Blueprint, jsonify
from flask_pymongo import PyMongo
from flask import current_app as app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dean_associates = Blueprint('dean_associates', __name__)

DEPARTMENTS = {
    "AIML": "AIML",
    "ASH": "ASH",
    "Civil": "Civil",
    "Computer": "Computer",
    "Computer(Regional)": "Computer_Regional",
    "ENTC": "ENTC",
    "IT": "IT",
    "Mechanical": "Mechanical"
}

DEFAULT_STATUS = "pending"

@dean_associates.route('/dean/<dean_id>/associates', methods=['GET'])
def get_associate_deans(dean_id):
    """
    Retrieve all associate deans for a given dean ID.
    
    Args:
        dean_id (str): The ID of the dean
        
    Returns:
        tuple: JSON response with associate dean information and HTTP status code
    """
    try:
        mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])
        mongo = PyMongo(app, uri=app.config["MONGO_URI"])
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Database connection failed",
            "details": str(e)
        }), 500

    try:
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
        # Initialize MongoDB connection
        
        # Get the lookup document for deans
        lookup_doc = mongo.db.lookup.find_one({"_id": "deans"})
        if not lookup_doc:
            logger.error("No lookup document found")
            return jsonify({
                "status": "error",
                "message": "Lookup document not found"
            }), 404

        # Check if higherDeanId exists
        if "higherDeanId" not in lookup_doc:
            logger.error(f"No higherDeanId field in lookup document: {lookup_doc}")
            return jsonify({
                "status": "error",
                "message": "Invalid lookup document structure"
            }), 404

        # Get list of associate dean IDs under this dean
        dean_associates = lookup_doc["higherDeanId"].get(dean_id)
        if not dean_associates:
            logger.info(f"No associates found for dean {dean_id}")
            return jsonify({
                "status": "error",
                "message": f"No associate deans found for dean {dean_id}"
            }), 404
        
        associates_list = []
        
        # Get details for each associate dean
        for associate in dean_associates:
            associate_id = associate["id"] if isinstance(associate, dict) else associate
            associate_data = mongo.db.users.find_one({"_id": associate_id})
            if associate_data:
                department = associate_data.get("dept", "")
                department_collection = department_collections.get(department)
                if department_collection is None:
                    logger.error(f"Invalid department: {department}")
                    continue
                
                # Get faculty status from department collection
                faculty_doc = department_collection.find_one({"_id": associate_id})
                faculty_status = DEFAULT_STATUS  # Default status
                if faculty_doc:
                    faculty_status = faculty_doc.get("status", DEFAULT_STATUS)
                
                associate_info = {
                    "id": associate_id,
                    "name": associate_data.get("name", ""),
                    "role": associate_data.get("role", ""),
                    "department": department,
                    "status": faculty_status
                }
                associates_list.append(associate_info)

        return jsonify({
            "status": "success",
            "dean_id": dean_id,
            "associate_count": len(associates_list),
            "associates": associates_list
        }), 200

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
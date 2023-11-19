import json
from flask import Blueprint, jsonify, request, make_response, current_app
from psycopg2.extras import DictCursor
from db import close_db, get_db

caregiver_bp = Blueprint('caregiver', __name__)

@caregiver_bp.route("/mycaregiver/<phone>", methods=["GET"])
def get_mycaregivers(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the caregivers related to the phone number
        cursor.execute(
            "SELECT * FROM caregivers WHERE phone = %s ORDER BY id DESC", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Caregivers not found"}), 404

        caregivers = [
            {
                "id": row["id"],
                "name": row["name"],
                "years_of_experience": row["years_of_experience"],
                "age": row["age"],
                "education": row["education"],
                "gender": row["gender"],
                "phone": row["phone"],
                "imageurl": row["imageurl"],
                "location": row["location"]
            }
            for row in rows
        ]

        return jsonify(caregivers)
    except Exception as e:
        current_app.logger.error(
            f"Error fetching caregivers for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregivers"}), 500


@caregiver_bp.route("/mycaregiver/<int:id>", methods=["PUT"])
def update_caregiver(id):
    current_app.logger.debug(f"Entering update_caregiver for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        # Added location to the list
        columns = ["name", "location"]
        # Using .get() to avoid KeyError
        values = []

        for field in columns:
            value = data.get(field, None)
            if field == 'location' and isinstance(value, list):
                # Serialize dict to JSON string
                values.append(json.dumps(value))
            else:
                values.append(value)

        current_app.logger.debug(f"Serialized location: {json.dumps(value)}")
        current_app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE caregivers SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + f" WHERE id = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        current_app.logger.info(f"Received data: {data}")
        current_app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        current_app.logger.error(
            f"Error updating caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update caregiver"}), 500


@caregiver_bp.route('/all_caregivers', methods=['GET'])
def get_all_caregivers():
    current_app.logger.info(
        "---------------Entering GET /all_caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch caregivers from the database
        cursor.execute("SELECT * FROM caregivers ORDER BY id DESC")
        rows = cursor.fetchall()
        current_app.logger.debug(
            f"Fetched {len(rows)} caregivers from the database")

        # Close the connection
        cursor.close()

        if not rows:
            current_app.logger.warning("No caregivers found in the database")
            return jsonify({"error": "Problem of fetching caregivers"}), 404

        # Directly convert the rows into JSON
        caregivers = [dict(row) for row in rows]

        # Format the data for JSON
        caregivers = [
            {
                "id": row["id"],
                "name": row["name"],
                "years_of_experience": row["years_of_experience"],
                "age": row["age"],
                "education": row["education"],
                "gender": row["gender"],
                "phone": row["phone"],
                "imageurl": row["imageurl"],
                "location": row["location"],
                "hourlycharge": row["hourlycharge"]
            }
            for row in rows
        ]

        current_app.logger.debug("Successfully processed all caregivers data")

        response = make_response(jsonify(caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        current_app.logger.error("Error fetching all caregivers", exc_info=True)
        return jsonify({"error": "Failed to fetch all caregivers"}), 500
    
@caregiver_bp.route("/all_caregivers/<int:caregiver_id>", methods=["GET"])
def get_caregiver_detail(caregiver_id):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the specific caregiver from the database using the id
        cursor.execute("SELECT * FROM caregivers WHERE id = %s",
                       (caregiver_id,))
        row = cursor.fetchone()

        # Close the connection
        cursor.close()

        # Check if a caregiver with the given id exists
        if not row:
            return jsonify({"error": "Caregiver not found"}), 404

        # Format the data for JSON
        caregiver = {
            "id": row["id"],
            "name": row["name"],
            "years_of_experience": row["years_of_experience"],
            "age": row["age"],
            "education": row["education"],
            "gender": row["gender"],
            "phone": row["phone"],
            "imageurl": row["imageurl"],
            "location": row["location"],
            "hourlycharge": row["hourlycharge"]
        }

        return jsonify(caregiver)
    except Exception as e:
        current_app.logger.error(
            f"Error fetching caregiver detail for id {caregiver_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregiver detail"}), 500


@caregiver_bp.route("/all_caregivers", methods=["POST"])
def add_caregiver():
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the mandatory columns and values for the INSERT query
        mandatory_columns = ["name", "phone",
                             "imageurl", "location", "hourlycharge"]
        values = [data[field] if field != 'location' else json.dumps(
            data[field]) for field in mandatory_columns]

        # Optional fields: yearsOfExperience, age, education, gender
        # Add them to the INSERT query only if they are present in the data
        optional_fields = ["years_of_experience", "age", "education", "gender"]
        for field in optional_fields:
            if field in data:
                mandatory_columns.append(field)
                values.append(data[field])
            else:
                # If the optional field is missing, set a default value or NULL
                # For example, set the yearsOfExperience to NULL
                # You can customize the default values as needed
                mandatory_columns.append(field)
                values.append(None)

        # Construct the INSERT query with the appropriate number of placeholders
        insert_query = f"INSERT INTO caregivers ({', '.join(mandatory_columns)}) VALUES ({', '.join(['%s'] * len(mandatory_columns))}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_caregiver_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Return the newly created caregiver data with the assigned ID
        # imageUrl is possibly from const [imageUrl, setImageUrl] = useState<string | null>(null) in CaregiverForm.tsx
        new_caregiver = {
            "id": new_caregiver_id,
            "name": data["name"],
            "phone": data["phone"],
            "age": data["age"],
            "education": data["education"],
            "gender": data["gender"],
            "years_of_experience": data["years_of_experience"],
            "imageurl": data["imageurl"],
            "location": data["location"],
            "hourlycharge": data["hourlycharge"]
        }
        return jsonify(new_caregiver), 201

    except Exception as e:
        current_app.logger.error(f"Error adding caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add caregiver"}), 500

@caregiver_bp.route("/caregiver_schedule", methods=["POST"])
def add_caregiver_schedule():
    try:
        data = request.get_json()

        # Log the received data for debugging
        current_app.logger.debug("Received data caregiver_schedule: %s", data)

        # Validate that careneeder_id is provided
        if "caregiver_id" not in data:
            return jsonify({"error": "caregiver_id is required"}), 400

        # Define the columns for the INSERT query
        columns = ["scheduletype", "totalhours", "frequency",
                   "startdate", "selectedtimeslots", "durationdays", "caregiver_id"]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in columns:
            if column in data:
                values.append(data[column])
            else:
                values.append(None)

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO caregiverschedule ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_schedule_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the Schedule interface
        new_schedule = {
            "id": new_schedule_id,
        }

        # Include columns in the return object if they exist
        for column in columns:
            if column in data:
                new_schedule[column] = data[column]

        return jsonify(new_schedule), 201

    except Exception as e:
        if conn:
            conn.rollback()
        current_app.logger.error(
            f"Error adding schedule: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add schedule"}), 500
    finally:
        if conn:
            conn.close()    

@caregiver_bp.route('/all_caregiverschedule', methods=['GET'])
def get_all_caregiverschedule():
    current_app.logger.info("Entering GET /all_caregiverschedule request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneederschedule data from the database
        cursor.execute("SELECT * FROM caregiverschedule ORDER BY id DESC")
        rows = cursor.fetchall()
        current_app.logger.debug(
            f"Fetched {len(rows)} caregiverschedule records from the database")

        # Close the connection
        cursor.close()

        if not rows:
            current_app.logger.warning(
                "No caregiverschedule records found in the database")
            return jsonify({"error": "No caregiverschedule data available"}), 404

        # Format the data for JSON

        caregiverschedule = [dict(row) for row in rows]

        current_app.logger.debug(
            "Successfully processed all caregiverschedule data")

        response = make_response(jsonify(caregiverschedule))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        current_app.logger.error(
            "Error fetching all caregiverschedule", exc_info=True)
        return jsonify({"error": "Failed to fetch all caregiverschedule"}), 500        
        

@caregiver_bp.route("/caregiver_ads", methods=["POST"])
def add_caregiver_ad():
    try:
        data = request.get_json()

        # Define the columns for the INSERT query
        columns = ["title", "description", "caregiver_id"]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in columns:
            if column in data:
                values.append(data[column])
            else:
                values.append(None)

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO caregiverads ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_ad_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the ad interface
        new_ad = {
            "id": new_ad_id,
        }

        # Include columns in the return object if they exist
        for column in columns:
            if column in data:
                new_ad[column] = data[column]

        return jsonify(new_ad), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        current_app.logger.error(
            f"Error adding caregiver ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add caregiver ad"}), 500
    finally:
        if conn:
            conn.close()


@caregiver_bp.route("/all_caregiverads", methods=["GET"])
def get_caregiver_ads():
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        # Use DictCursor to fetch rows as dictionaries
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Execute the SELECT query to fetch all records from the caregiverads table
        select_query = "SELECT * FROM caregiverads ORDER BY id DESC"
        cursor.execute(select_query)

        # Fetch all rows and close the cursor
        rows = cursor.fetchall()
        cursor.close()

        current_app.logger.debug(
            f"Fetched {len(rows)} caregiverads records from the database")

        # Check the data type of the first row for debugging
        if rows:
            current_app.logger.debug(f"First row data type: {type(rows[0])}")

        if not rows:
            current_app.logger.warning(
                "No caregiverads records found in the database")
            return jsonify({"error": "No caregiverads data available"}), 404

        caregiverads = [dict(row) for row in rows]

        current_app.logger.debug("Successfully processed all caregiverads data")

        response = make_response(jsonify(caregiverads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        current_app.logger.error(
            f"Error fetching caregiver ads: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to fetch caregiver ads"}), 500

    finally:
        if conn:
            conn.close()    

@caregiver_bp.route("/api/mycaregiver/<int:id>/ad", methods=["PUT"])
def update_caregiver_ad(id):
    caregiver_bp.logger.debug(f"Entering update_caregiver for id {id}")
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the columns and values for the UPDATE query
        columns = ["title", "description"]
        values = [data.get(field, None) for field in columns]

        current_app.logger.debug(f"Prepared values for SQL update: {values}")

        # Construct the UPDATE query
        update_query = "UPDATE caregiverads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE caregiver_id = {id}"

        # Execute the UPDATE query with the values
        cursor.execute(update_query, values)

        current_app.logger.info(f"Received data: {data}")
        current_app.logger.info(f"Executing query: {update_query}")

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        return jsonify({"success": "更新成功"}), 200

    except Exception as e:
        current_app.logger.error(
            f"Error updating caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update caregiver"}), 500            
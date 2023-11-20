import json
from flask import Blueprint, jsonify, request, make_response, current_app
from psycopg2.extras import DictCursor
from db import close_db, get_db

animalcaregiver_bp = Blueprint('animalcaregiver', __name__)

@animalcaregiver_bp.route("/animalcaregiver_details", methods=["POST"])
def add_animalcaregiver_detail():
    conn = None
    try:
        data = request.get_json()
        print("Received data:", data)

        # Define the columns for the INSERT query
        columns = ["\"animalcaregiverid\"", "\"selectedservices\"",
                   "\"selectedanimals\"", "\"hourlycharge\""]

        # Initialize values list
        values = []

        # Iterate through the columns and append the values if they exist
        for column in ["animalcaregiverid", "selectedservices", "selectedanimals", "hourlycharge"]:
            if column in data:
                if column == 'selectedservices' or column == 'selectedanimals':
                    # Convert list of strings to PostgreSQL array format
                    values.append('{'+','.join(map(str, data[column]))+'}')
                else:
                    values.append(data[column])
            else:
                values.append(None)

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f'INSERT INTO animalcaregiver ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id'

        print("Inserting values:", values)  # Debugging line
        print(f"Executing SQL: {insert_query % tuple(values)}")

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_detail_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the interface
        new_detail = {
            "id": new_detail_id,
        }

        # Include columns in the return object if they exist
        for column in ["animalcaregiverid", "selectedservices", "selectedanimals", "hourlycharge"]:
            if column in data:
                new_detail[column] = data[column]

        return jsonify(new_detail), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        current_app.logger.error(
            f"Error adding animalcaregiver detail: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animalcaregiver detail"}), 500
    finally:
        if conn:
            conn.close()


@animalcaregiver_bp.route("/all_animalcaregivers", methods=["POST"])
def add_animalcaregiver():
    try:
        data = request.get_json()

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the mandatory columns and values for the INSERT query
        mandatory_columns = ["name", "phone", "imageurl", "location"]
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
        insert_query = f"INSERT INTO animalcaregiverform ({', '.join(mandatory_columns)}) VALUES ({', '.join(['%s'] * len(mandatory_columns))}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_animalcaregiver_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Return the newly created caregiver data with the assigned ID
        # imageUrl is possibly from const [imageUrl, setImageUrl] = useState<string | null>(null) in CaregiverForm.tsx
        new_animalcaregiverform = {
            "id": new_animalcaregiver_id,
            "name": data["name"],
            "phone": data["phone"],
            "age": data["age"],
            "education": data["education"],
            "gender": data["gender"],
            "years_of_experience": data["years_of_experience"],
            "imageurl": data["imageurl"],
            "location": data["location"]
        }
        return jsonify(new_animalcaregiverform), 201

    except Exception as e:
        current_app.logger.error(
            f"Error adding animalcaregiverform: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animalcaregiverform"}), 500


@animalcaregiver_bp.route("/animalcaregiver_ads", methods=["POST"])
def add_animal_caregiver_ad():
    conn = None
    try:
        data = request.get_json()

        # Validate if "animalcaregiverid", "title", and "description" are present in data
        if not all(key in data for key in ["animalcaregiverid", "title", "description"]):
            return jsonify({"error": "Required fields are missing"}), 400

        # Define the columns for the INSERT query
        columns = ["title", "description", "animalcaregiverid"]

        # Initialize values list
        values = [data["title"], data["description"],
                  data["animalcaregiverid"]]

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(columns)
        values_placeholder = ', '.join(['%s'] * len(columns))
        insert_query = f"INSERT INTO animalcaregiverads ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_animalcaregiver_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the ad interface
        new_ad = {
            "id": new_animalcaregiver_id,
            "title": data["title"],
            "description": data["description"],
            "animalcaregiverid": data["animalcaregiverid"]
        }

        return jsonify(new_ad), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        current_app.error(
            f"Error adding animal caregiver ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add animal caregiver ad"}), 500
    finally:
        if conn:
            conn.close()


@animalcaregiver_bp.route("/animalcaregiver_schedule", methods=["POST"])
def add_animalcaregiver_schedule():
    try:
        data = request.get_json()

        # Log the received data for debugging
        current_app.logger.debug(
            "Received data animalcaregiver_schedule: %s", data)

        # Validate that careneeder_id is provided
        if "animalcaregiverform_id" not in data:
            return jsonify({"error": "animalcaregiverform_id is required"}), 400

        # Define the columns for the INSERT query
        columns = ["scheduletype", "totalhours", "frequency",
                   "startdate", "selectedtimeslots", "durationdays", "animalcaregiverform_id"]

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
        insert_query = f"INSERT INTO animalcaregiverschedule ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

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


@animalcaregiver_bp.route('/all_animalcaregiverschedule', methods=['GET'])
def get_all_animalcaregiverschedule():
    current_app.logger.info(
        "Entering GET /all_animalcaregiverschedule request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneederschedule data from the database
        cursor.execute(
            "SELECT * FROM animalcaregiverschedule ORDER BY id DESC")
        rows = cursor.fetchall()
        current_app.logger.debug(
            f"Fetched {len(rows)} animalcaregiverschedule records from the database")

        # Close the connection
        cursor.close()

        if not rows:
            current_app.logger.warning(
                "No animalcaregiverschedule records found in the database")
            return jsonify({"error": "No animalcaregiverschedule data available"}), 404

        # Format the data for JSON

        caregiverschedule = [dict(row) for row in rows]

        current_app.logger.debug(
            "Successfully processed all animalcaregiverschedule data")

        response = make_response(jsonify(caregiverschedule))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        current_app.logger.error(
            "Error fetching all animalcaregiverschedule", exc_info=True)
        return jsonify({"error": "Failed to fetch all animalcaregiverschedule"}), 500


@animalcaregiver_bp.route('/all_animalcaregivers', methods=['GET'])
def get_all_animal_caregivers():
    current_app.logger.info(
        "---------------Entering GET /all_animal_caregivers request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcaregiverform ORDER BY id DESC")
        rows = cursor.fetchall()
        current_app.logger.debug(
            f"Fetched {len(rows)} animal caregivers from the database")

        # Close the connection
        cursor.close()

        if not rows:
            current_app.logger.warning(
                "No animal caregivers found in the database")
            return jsonify({"error": "Problem of fetching animal caregivers"}), 404

        # Directly convert the rows into JSON
        animal_caregivers = [dict(row) for row in rows]

        # Format the data for JSON
        animal_caregivers = [
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

        current_app.logger.debug(
            "Successfully processed all animal caregivers data")

        response = make_response(jsonify(animal_caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        current_app.logger.error(
            "Error fetching all animal caregivers", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal caregivers"}), 500


@animalcaregiver_bp.route('/all_animal_caregivers_details', methods=['GET'])
def get_all_animal_caregivers_details():
    current_app.logger.info(
        "---------------Entering GET /all_animal_caregivers details request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch animal caregivers from the database
        cursor.execute("SELECT * FROM animalcaregiver ORDER BY id DESC")
        rows = cursor.fetchall()
        current_app.logger.debug(
            f"Fetched {len(rows)} animal caregivers details from the database")

        # Close the connection
        cursor.close()

        if not rows:
            current_app.logger.warning(
                "No animal caregivers details found in the database")
            return jsonify({"error": "Problem fetching animal caregivers details"}), 404

        # Directly convert the rows into JSON
        animal_caregivers = [
            {
                "id": row["id"],
                "animalcaregiverid": row["animalcaregiverid"],
                "selectedservices": row["selectedservices"],
                "selectedanimals": row["selectedanimals"],
                "hourlycharge": row["hourlycharge"]
            }
            for row in rows
        ]

        current_app.logger.debug(
            "Successfully processed all animal caregivers details data")

        response = make_response(jsonify(animal_caregivers))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        current_app.logger.error(
            "Error fetching all animal caregivers details", exc_info=True)
        return jsonify({"error": "Failed to fetch all animal caregivers details"}), 500


@animalcaregiver_bp.route('/all_animal_caregiver_ads', methods=['GET'])
def get_all_animal_caregiver_ads():
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Using the correct table name
        cursor.execute("SELECT * FROM animalcaregiverads ORDER BY id DESC")
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return jsonify({"error": "No animal caregiver ads found"}), 404

        animal_caregiver_ads = [
            {
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "animalcaregiverid": row["animalcaregiverid"]
            }
            for row in rows
        ]

        response = make_response(jsonify(animal_caregiver_ads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        return jsonify({"error": "Failed to fetch animal caregiver ads"}), 500


@animalcaregiver_bp.route("/all_animalcaregiverform/<int:animalcaregiverform_id>", methods=["GET"])
def get_animalcaregiverform_detail(animalcaregiverform_id):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursall_animalcaregiverformor_factory=DictCursor)

        # Fetch the specific record from the animalcaregiverform table using the id
        cursor.execute(
            "SELECT * FROM animalcaregiverform WHERE id = %s", (animalcaregiverform_id,))
        row = cursor.fetchone()

        # Close the connection
        cursor.close()

        # Check if a record with the given id exists
        if not row:
            return jsonify({"error": "Animal Caregiver Form not found"}), 404

        # Format the data for JSON (update these keys as needed)
        animalcaregiverform = {
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

        return jsonify(animalcaregiverform)
    except Exception as e:
        current_app.error(
            f"Error fetching animal caregiver form detail for id {animalcaregiverform_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch animal caregiver form detail"}), 500


@animalcaregiver_bp.route("/myanimalcaregiverform/<phone>", methods=["GET"])
def get_myanimalcaregiverform(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the records related to the phone number from the animalcaregiverform table
        cursor.execute(
            "SELECT * FROM animalcaregiverform WHERE phone = %s ORDER BY id DESC", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Animal Caregiver Forms not found"}), 404

        animalcaregiverforms = [
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

        return jsonify(animalcaregiverforms)
    except Exception as e:
        current_app.logger.error(
            f"Error fetching animal caregiver forms for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch animal caregiver forms"}), 500


@animalcaregiver_bp.route("/myanimalcaregiver/<int:id>/ad", methods=["PUT"])
def update_animalcaregiver_ad(id):
    current_app.logger.debug(f"Entering update_animalcaregiver for id {id}")
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
        update_query = "UPDATE animalcaregiverads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE animalcaregiverid = {id}"

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
            f"Error updating animal caregiver: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update animal caregiver"}), 500
    
    
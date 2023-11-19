import json
from flask import Blueprint, jsonify, request, make_response, current_app
from psycopg2.extras import DictCursor
from db import close_db, get_db

careneeder_bp = Blueprint('careneeder', __name__)

@careneeder_bp.route("/all_careneeders", methods=["POST"])
def add_careneeder():
    try:
        data = request.get_json()

        # Validate mandatory fields
        for field in ["name", "phone"]:
            if field not in data:
                return jsonify({"error": f"{field} is required"}), 400

        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor()

        # Define the mandatory columns and values for the INSERT query
        mandatory_columns = ["name", "phone", "location", "hourlycharge"]
        values = [data[field] if field != 'location' else json.dumps(
            data[field]) for field in mandatory_columns]

        # Define optional fields and include them in columns and values if they are present
        optional_fields = [
            "imageurl", "live_in_care", "live_out_care", "domestic_work", "meal_preparation",
            "companionship", "washing_dressing", "nursing_health_care",
            "mobility_support", "transportation", "errands_shopping"
        ]

        for field in optional_fields:
            if field in data:
                mandatory_columns.append(field)
                values.append(data[field])
            else:
                mandatory_columns.append(field)
                values.append(None)

         # Construct the INSERT query with placeholders for all columns
        columns_placeholder = ', '.join(mandatory_columns)
        values_placeholder = ', '.join(['%s'] * len(mandatory_columns))
        insert_query = f"INSERT INTO careneeder ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

        # Execute the INSERT query with the values
        cursor.execute(insert_query, values)
        new_careneeder_id = cursor.fetchone()[0]

        # Commit the changes and close the connection
        conn.commit()
        cursor.close()

        # Create the returned object based on the Careneeder interface
        new_careneeder = {
            "id": new_careneeder_id,
            "name": data["name"],
            "phone": data["phone"],
            "location": data["location"],
            "hourlycharge": data["hourlycharge"]
        }

        # Include optional fields in the return object if they exist
        for field in optional_fields:
            new_careneeder[field] = data.get(field, None)

        return jsonify(new_careneeder), 201

    except Exception as e:  # Could also catch specific exceptions like psycopg2.DatabaseError
        if conn:
            conn.rollback()  # Rolling back in case of an error
        current_app.logger.error(
            f"Error adding careneeder: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add careneeder"}), 500
    finally:
        if conn:
            conn.close()  # Ensure that the connection is closed or returned to the pool


@careneeder_bp.route('/all_careneeders', methods=['GET'])
def get_all_careneeders():
    current_app.logger.info(
        "---------------Entering GET /all_careneeders request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneeders from the database
        cursor.execute("SELECT * FROM careneeder ORDER BY id DESC")
        rows = cursor.fetchall()
        current_app.logger.debug(
            f"Fetched {len(rows)} careneeders from the database")

        # Close the connection
        cursor.close()

        if not rows:
            current_app.logger.warning("No careneeders found in the database")
            return jsonify({"error": "Problem of fetching careneeders"}), 404

        # Directly convert the rows into JSON
        careneeders = [dict(row) for row in rows]

        # Format the data for JSON
        careneeders = [
            {
                "id": row["id"],
                "name": row["name"],
                "phone": row["phone"],
                "hourlycharge": row["hourlycharge"],
                "imageurl": row["imageurl"],
                "live_in_care": row["live_in_care"],
                "live_out_care": row["live_out_care"],
                "domestic_work": row["domestic_work"],
                "meal_preparation": row["meal_preparation"],
                "companionship": row["companionship"],
                "washing_dressing": row["washing_dressing"],
                "nursing_health_care": row["nursing_health_care"],
                "mobility_support": row["mobility_support"],
                "transportation": row["transportation"],
                "errands_shopping": row["errands_shopping"],
                "location": row["location"]
            }
            for row in rows
        ]

        current_app.logger.debug("Successfully processed all careneeders data")

        response = make_response(jsonify(careneeders))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        current_app.logger.error("Error fetching all careneeders", exc_info=True)
        return jsonify({"error": "Failed to fetch all careneeders"}), 500


@careneeder_bp.route("/all_careneeders/<int:careneeder_id>", methods=["GET"])
def get_careneeder_detail(careneeder_id):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the specific careneeder from the database using the id
        cursor.execute("SELECT * FROM careneeder WHERE id = %s",
                       (careneeder_id,))
        row = cursor.fetchone()

        # Close the connection
        cursor.close()

        # Check if a careneeder with the given id exists
        if not row:
            return jsonify({"error": "Careneeder not found"}), 404

        # Format the data for JSON
        careneeder = {
            "id": row["id"],
            "name": row["name"],
            "phone": row["phone"],
            "hourlycharge": row["hourlycharge"],
            "imageurl": row["imageurl"],
            "live_in_care": row["live_in_care"],
            "live_out_care": row["live_out_care"],
            "domestic_work": row["domestic_work"],
            "meal_preparation": row["meal_preparation"],
            "companionship": row["companionship"],
            "washing_dressing": row["washing_dressing"],
            "nursing_health_care": row["nursing_health_care"],
            "mobility_support": row["mobility_support"],
            "transportation": row["transportation"],
            "errands_shopping": row["errands_shopping"],
            "location": row["location"]
        }

        return jsonify(careneeder)
    except Exception as e:
        current_app.logger.error(
            f"Error fetching careneeder detail for id {careneeder_id}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeder detail"}), 500


@careneeder_bp.route("/mycareneeder/<phone>", methods=["GET"])
def get_mycareneeders(phone):
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch the careneeders related to the phone number
        cursor.execute(
            "SELECT * FROM careneeder WHERE phone = %s ORDER BY id DESC", (phone,))
        rows = cursor.fetchall()

        # Close the connection
        cursor.close()

        if not rows:
            return jsonify({"error": "Careneeders not found"}), 404

        careneeders = [
            {
                "id": row["id"],
                "name": row["name"],
                "phone": row["phone"],
                "hourlycharge": row["hourlycharge"],
                "imageurl": row["imageurl"],
                "live_in_care": row["live_in_care"],
                "live_out_care": row["live_out_care"],
                "domestic_work": row["domestic_work"],
                "meal_preparation": row["meal_preparation"],
                "companionship": row["companionship"],
                "washing_dressing": row["washing_dressing"],
                "nursing_health_care": row["nursing_health_care"],
                "mobility_support": row["mobility_support"],
                "transportation": row["transportation"],
                "errands_shopping": row["errands_shopping"],
                "location": row["location"]
            }
            for row in rows
        ]

        return jsonify(careneeders)
    except Exception as e:
        current_app.logger.error(
            f"Error fetching careneeders for phone {phone}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeders"}), 500
    

@careneeder_bp.route("/careneeder_schedule", methods=["POST"])
def add_schedule():
    try:
        data = request.get_json()

        # Log the received data for debugging
        current_app.logger.debug("Received data: %s", data)

        # Validate that careneeder_id is provided
        if "careneeder_id" not in data:
            return jsonify({"error": "careneeder_id is required"}), 400

        # Define the columns for the INSERT query
        columns = ["scheduletype", "totalhours", "frequency",
                   "startdate", "selectedtimeslots", "durationdays", "careneeder_id"]

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
        insert_query = f"INSERT INTO careneederschedule ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

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


@careneeder_bp.route("/mycareneeder/<int:id>/ad", methods=["PUT"])
def update_careneeder_ad(id):
    current_app.logger.debug(f"Entering update_careneeder for id {id}")
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
        update_query = "UPDATE careneederads SET " + \
            ', '.join([f"{col} = %s" for col in columns]) + \
            f" WHERE careneeder_id = {id}"

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
            f"Error updating careneeder: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to update careneeder"}), 500


@careneeder_bp.route("/careneeder_ads", methods=["POST"])
def add_careneeder_ad():
    try:
        data = request.get_json()

        # Define the columns for the INSERT query
        columns = ["title", "description",  "careneeder_id"]

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
        insert_query = f"INSERT INTO careneederads ({columns_placeholder}) VALUES ({values_placeholder}) RETURNING id"

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
            f"Error adding careneeder ad: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to add careneeder ad"}), 500
    finally:
        if conn:
            conn.close()


@careneeder_bp.route('/all_careneederschedule', methods=['GET'])
def get_all_careneederschedule():
    current_app.logger.info("Entering GET /all_careneederschedule request")
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Fetch careneederschedule data from the database
        cursor.execute("SELECT * FROM careneederschedule ORDER BY id DESC")
        rows = cursor.fetchall()
        current_app.logger.debug(
            f"Fetched {len(rows)} careneederschedule records from the database")

        # Close the connection
        cursor.close()

        if not rows:
            current_app.logger.warning(
                "No careneederschedule records found in the database")
            return jsonify({"error": "No careneederschedule data available"}), 404

        # Format the data for JSON

        careneederschedule = [dict(row) for row in rows]

        current_app.logger.debug(
            "Successfully processed all careneederschedule data")

        response = make_response(jsonify(careneederschedule))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        current_app.logger.error(
            "Error fetching all careneederschedule", exc_info=True)
        return jsonify({"error": "Failed to fetch all careneederschedule"}), 500


@careneeder_bp.route("/all_careneederads", methods=["GET"])
def get_careneeder_ads():
    conn = None
    try:
        # Connect to the PostgreSQL database
        conn = get_db()
        # Use DictCursor to fetch rows as dictionaries
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Execute the SELECT query to fetch all records from the table
        select_query = "SELECT * FROM careneederads ORDER BY id DESC"
        cursor.execute(select_query)

        # Fetch all rows and close the cursor
        rows = cursor.fetchall()
        cursor.close()

        current_app.logger.debug(
            f"Fetched {len(rows)} careneederads records from the database")

        # Check the data type of the first row for debugging
        if rows:
            current_app.logger.debug(f"First row data type: {type(rows[0])}")

        if not rows:
            current_app.logger.warning(
                "No careneederads records found in the database")
            return jsonify({"error": "No careneederads data available"}), 404

        careneederads = [dict(row) for row in rows]

        current_app.logger.debug("Successfully processed all careneederads data")

        response = make_response(jsonify(careneederads))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    except Exception as e:
        if conn:
            conn.rollback()  # Rolling back in case of an error
        current_app.logger.error(
            f"Error fetching careneeder ads: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to fetch careneeder ads"}), 500

    finally:
        if conn:
            conn.close()
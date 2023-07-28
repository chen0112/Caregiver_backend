from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2

app = Flask(__name__)

CORS(app)


# Database connection configuration
db_config = {
    "dbname": "react_app",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432",
}


# Sample caregiver data (you can replace this with your actual database integration)
caregivers = [
    {"id": 1, "name": "John Doe", "description": "Experienced caregiver"},
    {"id": 2, "name": "Jane Smith", "description": "Compassionate nanny"},
    # Add more caregivers as needed
]


@app.route("/api/caregivers", methods=["GET"])
def get_caregivers():
    # Connect to the PostgreSQL database
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    # Fetch caregivers from the database
    cursor.execute("SELECT * FROM caregivers")
    rows = cursor.fetchall()

    # Close the connection
    cursor.close()
    conn.close()

    # Format the data for JSON
    caregivers = [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            # add the rest of your fields here, make sure to match the order they appear in your database
            "years_of_experience": row[3],
            "age": row[4],
            "education": row[5],
            "gender": row[6]
        }
        for row in rows
    ]

    return jsonify(caregivers)



@app.route("/api/caregivers", methods=["POST"])
def add_caregiver():
    data = request.get_json()

    # Connect to the PostgreSQL database
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    # Define the columns and values for the INSERT query
    columns = ["name", "description"]
    values = [data["name"], data["description"]]

    # Optional fields: yearsOfExperience, age, education, gender
    # Add them to the INSERT query only if they are present in the data
    optional_fields = ["years_of_experience", "age", "education", "gender"]
    for field in optional_fields:
        if field in data:
            columns.append(field)
            values.append(data[field])
        else:
            # If the optional field is missing, set a default value or NULL
            # For example, set the yearsOfExperience to NULL
            # You can customize the default values as needed
            columns.append(field)
            values.append(None)

    # Construct the INSERT query with the appropriate number of placeholders
    insert_query = f"INSERT INTO caregivers ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) RETURNING id"

    # Execute the INSERT query with the values
    cursor.execute(insert_query, values)
    new_caregiver_id = cursor.fetchone()[0]

    # Commit the changes and close the connection
    conn.commit()
    cursor.close()
    conn.close()

    # Return the newly created caregiver data with the assigned ID
    new_caregiver = {
        "id": new_caregiver_id,
        "name": data["name"],
        "description": data["description"],
        "age": data["age"],
        "education": data["education"],
        "gender": data["gender"],
        "years_of_experience": data["years_of_experience"]
    }
    return jsonify(new_caregiver), 201



if __name__ == "__main__":
    app.run(debug=True)

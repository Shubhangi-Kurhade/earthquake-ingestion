import json
import logging

from pyspark.sql import SparkSession, Row
from google.cloud import bigquery
import requests
from google.cloud import storage
from pyspark.sql.types import StructType, StringType, StructField, DoubleType, LongType, IntegerType
from requests import HTTPError


def fetch_api_data(url):
    """
    This method fetch data from api,using request lib.
    :param url: API url
    :return: json object
    """
    response = requests.get(url)
    return response.json()


###upload data from url to gscs bucket

def upload_to_gcs(bucket_name, destination_blob_name, data):
    """Uploads JSON data to a Google Cloud Storage bucket."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    # Convert the dictionary to a JSON string
    json_data = json.dumps(data)  # Converts data to a JSON string

    # Upload the JSON string directly
    blob.upload_from_string(json_data, content_type='application/json')
    # print(f"File uploaded to {destination_blob_name} in bucket {bucket_name}.")

###read data from gcs bucket
def read_from_gcs(bucket_name, blob_name):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    json_data = blob.download_as_text()
    # print("Raw content from GCS:", json_data)
    return json.loads(json_data)


def flatten(spark,geojson_data):
    """
    Convert GeoJSON data to a PySpark DataFrame.

    Args:
        geojson_data (dict): A dictionary representing GeoJSON data.

    Returns:
        pyspark.sql.DataFrame: A PySpark DataFrame containing the flattened GeoJSON data.
    """
    # Define the schema explicitly
    schema = StructType([
        StructField("id", StringType(), True),
        StructField("mag", DoubleType(), True),
        StructField("place", StringType(), True),
        StructField("time", LongType(), True),
        StructField("updated", LongType(), True),
        StructField("url", StringType(), True),
        StructField("detail", StringType(), True),
        StructField("felt", IntegerType(), True),
        StructField("cdi", DoubleType(), True),
        StructField("mmi", DoubleType(), True),
        StructField("alert", StringType(), True),
        StructField("status", StringType(), True),
        StructField("tsunami", IntegerType(), True),
        StructField("sig", IntegerType(), True),
        StructField("net", StringType(), True),
        StructField("code", StringType(), True),
        StructField("ids", StringType(), True),
        StructField("sources", StringType(), True),
        StructField("types", StringType(), True),
        StructField("nst", IntegerType(), True),
        StructField("dmin", DoubleType(), True),
        StructField("rms", DoubleType(), True),
        StructField("gap", DoubleType(), True),
        StructField("magType", StringType(), True),
        StructField("type", StringType(), True),
        StructField("title", StringType(), True),
        StructField("tz", IntegerType(), True),
        StructField("longitude", DoubleType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("depth", DoubleType(), True)
    ])

    # Prepare data for PySpark DataFrame
    rows_to_insert = []
    for feature in geojson_data['features']:
        flattened_record = Row(
            id=feature['id'],
            mag=float(feature['properties']['mag']),
            place=feature['properties']['place'],
            time=feature['properties']['time'],
            updated=feature['properties']['updated'],
            url=feature['properties']['url'],
            detail=feature['properties'].get('detail'),  # Optional field
            felt=feature['properties'].get('felt', 0),  # Default to 0 if not present
            cdi=float(feature['properties'].get('cdi', 0.0)) if feature['properties'].get('cdi') is not None else 0.0,  # Ensure cdi is float, default to 0.0 if None
            mmi=float(feature['properties'].get('mmi')) if feature['properties'].get('mmi') is not None else None,            alert=feature['properties'].get('alert'),  # Optional field
            status=feature['properties']['status'],
            tsunami=feature['properties']['tsunami'],
            sig=feature['properties']['sig'],
            net=feature['properties']['net'],
            code=feature['properties']['code'],
            ids=feature['properties'].get('ids'),  # Optional field
            sources=feature['properties'].get('sources'),  # Optional field
            types=feature['properties'].get('types'),  # Optional field
            nst=feature['properties'].get('nst'),  # Optional field
            dmin=float(feature['properties'].get('dmin', 0.0)) if feature['properties'].get('dmin') is not None else 0.0,  # Ensure dmin is float
            rms=float(feature['properties'].get('rms')),  # Optional field
            gap=float(feature['properties'].get('gap', 0.0)) if feature['properties'].get('gap') is not None else 0.0,  # Default to 0.0 if None
            magType=feature['properties']['magType'],
            type=feature['properties']['type'],
            title=feature['properties']['title'],
            tz=feature['properties'].get('tz'),  # Include tz field
            longitude=float(feature['geometry']['coordinates'][0]),  # Ensure longitude is float
            latitude=float(feature['geometry']['coordinates'][1]),  # Ensure latitude is float
            depth=float(feature['geometry']['coordinates'][2])  # Explicitly cast depth to float
        )
        rows_to_insert.append(flattened_record)

    # Create PySpark DataFrame
    df = spark.createDataFrame(rows_to_insert,schema)
    return df


    ##flattening for dataflow


def flatten_feature(features):
    """
    Flatten a GeoJSON feature into a Row object.

    Args:
        features (dict): A GeoJSON feature collection.

    Returns:
        list: A list of Row representations of the flattened features.
    """
    flattened_records = []

    for feature in features.get('features', []):
        try:
            # Use a helper function to safely convert values to float
            def safe_float(value, default=0.0):
                if value is None:
                    return default
                return float(value)

            flattened_record = Row(
                id=feature['id'],
                mag=safe_float(feature['properties'].get('mag')),  # Default to 0.0 if None
                place=feature['properties'].get('place', 'Unknown'),  # Default to 'Unknown' if None
                time=feature['properties'].get('time'),  # May be None, check how to handle it
                updated=feature['properties'].get('updated'),  # May be None
                url=feature['properties'].get('url'),  # Optional field
                detail=feature['properties'].get('detail'),  # Optional field
                felt=safe_float(feature['properties'].get('felt', 0)),  # Default to 0 if not present
                cdi=safe_float(feature['properties'].get('cdi')),  # Default to 0.0 if None
                mmi=float(feature['properties'].get('mmi')) if feature['properties'].get('mmi') is not None else None,
                alert=feature['properties'].get('alert'),  # Optional field
                status=feature['properties']['status'],  # Must exist
                tsunami=int(feature['properties']['tsunami']),  # Assuming this should be an integer
                sig=feature['properties']['sig'],  # Optional field
                net=feature['properties']['net'],  # Optional field
                code=feature['properties']['code'],  # Optional field
                ids=feature['properties'].get('ids'),  # Optional field
                sources=feature['properties'].get('sources'),  # Optional field
                types=feature['properties'].get('types'),  # Optional field
                nst=feature['properties'].get('nst'),  # Optional field
                dmin=safe_float(feature['properties'].get('dmin')),  # Default to 0.0 if None
                rms=safe_float(feature['properties'].get('rms')),  # Optional field
                gap=safe_float(feature['properties'].get('gap')),  # Default to 0.0 if None
                magType=feature['properties']['magType'],  # Must exist
                type=feature['properties']['type'],  # Must exist
                title=feature['properties']['title'],  # Must exist
                tz=feature['properties'].get('tz'),  # Optional field
                longitude=safe_float(feature['geometry']['coordinates'][0]),  # Ensure longitude is float
                latitude=safe_float(feature['geometry']['coordinates'][1]),  # Ensure latitude is float
                depth=safe_float(feature['geometry']['coordinates'][2])  # Explicitly cast depth to float
            )
            flattened_records.append(flattened_record)
        except KeyError as e:
            logging.error(f"Missing essential field in feature: {e}")  # Handle missing fields
        except TypeError as e:
            logging.error(f"Type error encountered: {e}")  # Log TypeError

    return flattened_records  # Return the list of flattened records
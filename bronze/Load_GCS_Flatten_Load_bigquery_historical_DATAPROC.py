#script_name:
#script Description:
#update date:21-10-2024
#################################################
import json
import os
from datetime import datetime
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from pyspark.sql.functions import col, from_unixtime, regexp_extract, col, avg, year, month, dayofmonth, count, \
    to_timestamp, expr,col, max, to_timestamp, current_timestamp, expr
from pyspark.sql.functions import current_timestamp
import utils
import argparse
from pyspark.sql import SparkSession

def load_data_GCS():
    ##define spark session
    spark=SparkSession.builder.master('local[*]').appName('historical data').getOrCreate()

    # os.environ['GOOGLE_APPLICATION_CREDENTIALS']=r'D:\earthquake-ingestion\eathquake-73bed61ccae3.json'
    ##pulling data from url

    url='https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.geojson'

    ### using python request liabrary fetching data from given liabrary

    response=utils.fetch_api_data(url)
    current_date = datetime.now().strftime("%Y%m%d")  # Format the date as YYYYMMDD

    ## GCS bucket information

    bucket_name = 'earthquake_analysis_shu'  # Replace with your GCS bucket name
    destination_blob_name = f'landing/{current_date}/data.json'  # The destination path inside the bucket

    # Upload the data to GCS by  calling method
    utils.upload_to_gcs(bucket_name, destination_blob_name, response)

def Fatten_Data():
    spark = SparkSession.builder.master('local[*]').appName('historical data').getOrCreate()
    bucket_name = 'earthquake_analysis_shu'  # Replace with your GCS bucket name

    current_date = datetime.now().strftime("%Y%m%d")  # Format the date as YYYYMMDD

    destination_blob_name = f'landing/{current_date}/data.json'  # The destination path inside the bucket

    ## Read the data back from GCS
    read_data = utils.read_from_gcs(bucket_name, destination_blob_name)
    ## Flatten the data

    df = utils.flatten(spark,read_data)
    # Convert 'time' and 'updated' from milliseconds (epoch) to timestamp
    df = df.withColumn('time', from_unixtime(col('time') / 1000)) \
        .withColumn('updated', from_unixtime(col('updated') / 1000))

    # Define the regex pattern to extract everything after "of"
    pattern = r'of\s(.*)'

    # Create the new "area" column by extracting the text after "of"
    df = df.withColumn('area', regexp_extract(col('place'), pattern, 1))

    # Show the resulting DataFrame
    # df.show(truncate=False)

    #upload to gcs bucket into silver folder

    # Write DataFrame to GCS in json format
    destination_blob_name_silver = f'silver/{current_date}/data.json'
    json_data = df.toJSON().collect()  # Collects the DataFrame as a list of JSON strings
    data_to_upload = [json.loads(record) for record in json_data]  # Convert each string to a dictionary

    # Upload the flattened data
    utils.upload_to_gcs(bucket_name, destination_blob_name_silver, data_to_upload)



def Load_BigQuery():

    spark = SparkSession.builder.master('local[*]').appName('historical data').config("spark.jars.packages", "com.google.cloud.spark:spark-bigquery-with-dependencies_2.12:0.34.0") \
.getOrCreate()
    bucket_name = 'earthquake_analysis_shu'
    current_date = datetime.now().strftime("%Y%m%d")
    destination_blob_name_silver=f'silver/{current_date}/data.json'  # The destination path inside the bucket

    flatten_data = utils.read_from_gcs(bucket_name, destination_blob_name_silver)
    # print(flatten_data)
   # Insert data : insert_dt (Timestamp)
    df=spark.createDataFrame(flatten_data)

    df1 = df.withColumn('insert_date', current_timestamp())
    # df1.show(truncate=False)
    df1.write.format("bigquery") \
        .option("table", "eathquake.Earthquake.historical_data_dataproc") \
        .option("writeMethod", "direct") \
        .save()

# Define default arguments for the Airflow DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 10, 24),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Create the Airflow DAG
with DAG('pyspark_dag2',
         default_args=default_args,
         description='DAG for running Pyspark job in 3 steps',
         schedule_interval=None,  # Daily schedule
         catchup=False) as dag:
    # Task 1: Fetch GeoJSON data from API
    task_step1 = PythonOperator(
        task_id='load_data_GCS',
        python_callable=load_data_GCS,
    )

    # Task 2: Process and flatten data
    task_step2 = PythonOperator(
        task_id='Fatten_Data',
        python_callable=Fatten_Data,
    )

    # Task 3: Write to BigQuery
    task_step3 = PythonOperator(
        task_id='Load_BigQuery',
        python_callable=Load_BigQuery,
    )

# Set task dependencies
task_step1 >> task_step2 >> task_step3










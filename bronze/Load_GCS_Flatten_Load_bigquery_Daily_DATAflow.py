from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import json
from datetime import datetime
import re
from requests.exceptions import HTTPError
import logging
import os
from apache_beam.options.pipeline_options import PipelineOptions, GoogleCloudOptions
import apache_beam as beam
from apache_beam import DoFn, Row
from utils import fetch_api_data,flatten_feature

# Define the FetchAPIData class
class FetchAPIData(DoFn):
    def process(self, element):
        try:
            geojson_data = fetch_api_data(element)  # Assuming 'element' is a URL
            yield geojson_data
        except HTTPError as e:
            logging.error(f"HTTP error occurred: {e}")
        except Exception as e:
            logging.error(f"An error occurred: {e}")

class FlattenFeature(DoFn):
    def process(self, feature_collection):
        logging.info(f"Processing feature_collection of type: {type(feature_collection)}")
        if isinstance(feature_collection, str):
            feature_collection = json.loads(feature_collection)
        flattened_records = flatten_feature(feature_collection)
        for record in flattened_records:
            yield record

class ConvertTimestamp(DoFn):
    def process(self, element):
        # Convert Row to dictionary using asDict() to access the fields
        record = element.asDict()  # Adjust if you're using a different method to convert Row

        # Convert 'time' from epoch to local timestamp if it's present
        if 'time' in record and record['time'] is not None:
            try:
                # Convert milliseconds to seconds and format to timestamp
                epoch_time = float(record['time']) / 1000
                # Use local time conversion and format without UTC
                record['time'] = datetime.fromtimestamp(epoch_time).strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                logging.error(f"Error converting 'time': {e}")

        # Convert 'updated' from epoch to local timestamp if it's present
        if 'updated' in record and record['updated'] is not None:
            try:
                # Convert milliseconds to seconds and format to timestamp
                epoch_updated = float(record['updated']) / 1000
                # Use local time conversion and format without UTC
                record['updated'] = datetime.fromtimestamp(epoch_updated).strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                logging.error(f"Error converting 'updated': {e}")

        # Optionally extract 'area' from 'place' field if it exists
        if 'place' in record and record['place']:
            try:
                pattern = r'of\s+(.*)'  # Regex to extract everything after "of"
                match = re.search(pattern, record['place'])
                if match:
                    record['area'] = match.group(1).strip()
            except Exception as e:
                logging.error(f"Error extracting 'area': {e}")

        # Yield the modified record
        yield record

class AddInsertDate(beam.DoFn):
    def process(self, element):
        record = json.loads(element)
        record['insert_date'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        yield record


# Step 1: Fetch GeoJSON data from the API
def load_data_GCS():
    options = PipelineOptions()
    google_cloud_option = options.view_as(GoogleCloudOptions)
    google_cloud_option.project = 'eathquake'
    google_cloud_option.region = 'us-central1'
    google_cloud_option.job_name = 'historicaldatadagstep1'
    google_cloud_option.staging_location = 'gs://dataproc-staging-us-central1-486196425494-ivlyiah3/s1'
    google_cloud_option.temp_location = 'gs://dataproc-staging-us-central1-486196425494-ivlyiah3/t1'

    url = 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson'
    current_date = datetime.now().strftime("%Y%m%d")

    with beam.Pipeline(options=options) as p1:
        api_urls = [url]
        geojson_data = (
                p1
                | "Create API URLs" >> beam.Create(api_urls)
                | "Fetch API Data" >> beam.ParDo(FetchAPIData())
        )

        output_path_1 = f'gs://earthquake_analysis_dataflow/landing/{current_date}/data.json'
        geojson_data | 'Format as JSON' >> beam.Map(lambda x: json.dumps(x)) | 'Write to GCS' >> beam.io.WriteToText(
            output_path_1, file_name_suffix='.json', num_shards=1)


# Step 2: Read from GCS and process data
def Fatten_Data():
    options = PipelineOptions()
    google_cloud_option = options.view_as(GoogleCloudOptions)
    google_cloud_option.project = 'eathquake'
    google_cloud_option.region = 'us-central1'
    google_cloud_option.job_name = 'historicaldatadagstep2'
    google_cloud_option.staging_location = 'gs://dataproc-staging-us-central1-486196425494-ivlyiah3/s1'
    google_cloud_option.temp_location = 'gs://dataproc-staging-us-central1-486196425494-ivlyiah3/t1'

    current_date = datetime.now().strftime("%Y%m%d")
    input_path_2 = f'gs://earthquake_analysis_dataflow/landing/{current_date}/data.*'

    with beam.Pipeline(options=options) as p2:
        read_result = p2 | 'Read from GCS' >> beam.io.ReadFromText(input_path_2)
        flattened_data = read_result | "Flatten Data" >> beam.ParDo(FlattenFeature())
        processed_data = flattened_data | 'ConvertTimestamps' >> beam.ParDo(ConvertTimestamp())

        output_path_2 = f'gs://earthquake_analysis_dataflow/silver/{current_date}/data.json'
        processed_data | 'Format as JSON' >> beam.Map(lambda x: json.dumps(x)) | 'Write to GCS' >> beam.io.WriteToText(
            output_path_2, file_name_suffix='.json', num_shards=1)


# Step 3: Read from GCS and write to BigQuery
def Load_BigQuery():
    options = PipelineOptions()
    google_cloud_option = options.view_as(GoogleCloudOptions)
    google_cloud_option.project = 'eathquake'
    google_cloud_option.region = 'us-central1'
    google_cloud_option.job_name = 'historicaldatadagstep3'
    google_cloud_option.staging_location = 'gs://dataproc-staging-us-central1-486196425494-ivlyiah3/s1'
    google_cloud_option.temp_location = 'gs://dataproc-staging-us-central1-486196425494-ivlyiah3/t1'

    current_date = datetime.now().strftime("%Y%m%d")
    input_path_3 = f'gs://earthquake_analysis_dataflow/silver/{current_date}/data.*'

    with beam.Pipeline(options=options) as p3:
        read_result_3 = p3 | 'Read from GCS2' >> beam.io.ReadFromText(input_path_3)
        read_result_3 | 'Add Insert Date' >> beam.ParDo(
            AddInsertDate()) | 'Write to BigQuery' >> beam.io.WriteToBigQuery(
            'eathquake:Earthquake.earthquake_db_earthquake_data_dataflow',
            schema='SCHEMA_AUTODETECT',
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
        )


# Define default arguments for the Airflow DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 10, 25),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Create the Airflow DAG
with DAG('beam_pipeline_dag_final',
         default_args=default_args,
         description='DAG for running Apache Beam pipeline in 3 steps',
         schedule_interval="@daily",  # Daily schedule
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

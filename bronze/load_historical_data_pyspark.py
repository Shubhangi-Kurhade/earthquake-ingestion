import requests
import argparse
from pyspark.sql import SparkSession

if __name__ == "__main__":
    spark=SparkSession.builder.master('local[*]').appName('historical data').getOrCreate()
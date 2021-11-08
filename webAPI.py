#!/usr/bin/env python
# coding: utf-8

import json
import boto3
import os


def handler(event, context):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Credentials": True,
    }
    try:
        dynamodb = boto3.resource(
            "dynamodb",
            region_name=os.environ["region_name"],
            aws_access_key_id=os.environ["access_key"],
            aws_secret_access_key=os.environ["secret_access"],
        )
        main_table = dynamodb.Table(os.environ["main_table"])
        main_response = main_table.get_item(Key={"product": "Primo"})
        emergency_table = dynamodb.Table(os.environ["emergency_table"])
        emergency_table_response = emergency_table.get_item(Key={"id": "live"})
        conglomeration = main_response["Item"]
        conglomeration["emergency_status"] = emergency_table_response["Item"]["message"]
    except:
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps(
                {
                    "result": "An error has occurred, please check with your local library developer."
                }
            ),
        }
    else:
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps(conglomeration),
        }

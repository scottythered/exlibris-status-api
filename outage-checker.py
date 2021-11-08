#!/usr/bin/env python
# coding: utf-8

import requests as r
import json
from datetime import datetime
from dateutil import tz
import boto3
import os


def utc_time_now():
    from_zone = tz.gettz("UTC")
    return (datetime.utcnow()).replace(tzinfo=from_zone)


def utc_to_local_time(time):
    from_zone = tz.gettz("UTC")
    to_zone = tz.gettz(os.environ["local_timezone"])
    time_zoned = time.replace(tzinfo=from_zone)
    return time_zoned.astimezone(to_zone)


def slacker(slackurl, markdown):
    formatted = [
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": ":warning: *ExL System Status API*"}
            ],
        },
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": markdown}},
    ]
    slackdata = {
        "text": "Ex Libris System Status Issue",
        "blocks": json.dumps(formatted),
    }
    headers = {"Content-Type": "application/json"}
    r.post(slackurl, json=slackdata, headers=headers)


def dynamodb_starter():
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=os.environ["region_name"],
        aws_access_key_id=os.environ["access_key"],
        aws_secret_access_key=os.environ["secret_access"],
    )
    return dynamodb


def slack_flag_reset(bool):
    dynamodb = dynamodb_starter()
    table = dynamodb.Table(os.environ["outage_table"])
    table.update_item(
        Key={"product": "Outage"},
        UpdateExpression=("SET slack_alert = :val1"),
        ExpressionAttributeValues={":val1": bool},
    )


def handler(event, context):
    # setup
    slack_scott = os.environ["slack_scott"]
    slack_dis_dev = os.environ["slack_dis_dev"]

    # get current time
    now = (utc_to_local_time(utc_time_now())).strftime("%Y-%m-%d %H:%M")

    # check the API
    api = r.get(os.environ["lambda_api"])
    api_response = api.json()

    if api.status_code == 200:
        dynamodb = dynamodb_starter()
        table = dynamodb.Table(os.environ["outage_table"])
        dynamo_response = table.get_item(Key={"product": "Outage"})

        # if status is the same, only change the update date
        if dynamo_response["Item"]["service_status"] == api_response["service_status"]:
            table.update_item(
                Key={"product": "Outage"},
                UpdateExpression="SET last_update = :val1",
                ExpressionAttributeValues={":val1": now},
            )
        # if different, update entire DynamoDB entry
        else:
            # update table entry
            table.update_item(
                Key={"product": "Outage"},
                UpdateExpression=("SET last_update = :val1, service_status = :val2"),
                ExpressionAttributeValues={
                    ":val1": now,
                    ":val2": api_response["service_status"],
                },
            )
            if dynamo_response["Item"]["slack_alert"] == "true":
                slack_flag_reset("false")

            # if status is "unknown", send Scott a slack message
            if api_response["service_status"] == "unknown":
                if dynamo_response["Item"]["slack_alert"] == "false":
                    message = "*There may be a problem with the System Status API.*"
                    slacker(slack_scott, message)
                    slack_flag_reset("true")

            elif api_response["service_status"] == "Possible service interruption":
                if dynamo_response["Item"]["slack_alert"] == "false":
                    message = "*Possible service interruption with Primo. Suggest investigation.*"
                    slacker(slack_scott, message)
                    slack_flag_reset("true")

            elif api_response["service_status"] == "OUTAGE":
                if dynamo_response["Item"]["slack_alert"] == "false":
                    message = "*Status server currently returning ERROR, Primo may be down. Suggest investigation.*"
                    slacker(slack_scott, message)
                    slack_flag_reset("true")

    # in case the API is down for some reason
    elif (api.status_code == 500) or (api.status_code != 200):
        message = "**Sir, there may be a problem with the System Status API.**"
        slacker(slack_scott, message)

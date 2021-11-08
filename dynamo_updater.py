#!/usr/bin/env python
# coding: utf-8

import re
import json
import requests as r
from requests.auth import HTTPBasicAuth
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


def message_time_parse(text, mode):
    times = re.search(
        "Estimated Start: (.*) UTC Estimated End: (.*) UTC Description:", text
    )
    if mode == "start":
        return datetime.strptime(times.group(1), "%A, %Y-%B-%d %H:%M")
    elif mode == "stop":
        return datetime.strptime(times.group(2), "%A, %Y-%B-%d %H:%M")
    else:
        raise NameError("Time mode not understood")


def handler(event, context):
    # get current time, check ExL's api
    now = (utc_to_local_time(utc_time_now())).strftime("%Y-%m-%d %H:%M")
    raw_exlib_api_status = (
        r.get(
            f"https://exlprod.service-now.com/api/now/table/cmdb_ci_outage?sysparm_fields=cmdb_ci.u_external_name%2Cbegin%2Cend%2Cdetails%2Cu_investigating%2Cu_identified%2Cu_in_progress%2Cu_fixed%2Ctype&sysparm_query=cmdb_ciLIKE{os.environ['exl_system_id']}^end=NULL",
            auth=HTTPBasicAuth(os.environ["exl_user"], os.environ["exl_pass"]),
        )
    ).json()

    # retrieve previous ExL api status in DynamoDB
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=os.environ["region_name"],
        aws_access_key_id=os.environ["access_key"],
        aws_secret_access_key=os.environ["secret_access"],
    )
    table = dynamodb.Table(os.environ["main_table"])
    response = table.get_item(Key={"product": "Primo"})

    # if status is the same, only change the update date; if different, update entire DynamoDB entry
    if response["Item"]["raw_api_response"] == raw_exlib_api_status:
        table.update_item(
            Key={"product": "Primo"},
            UpdateExpression="SET last_update = :val1",
            ExpressionAttributeValues={":val1": now},
        )
    else:
        asu_api = {}
        if len(raw_exlib_api_status["result"]) == 0:
            asu_api["service_status"] = "OK"
            asu_api["maintenance"] = False
            asu_api["affected_env"] = "NA"
            asu_api["maintenance_start"] = "NA"
            asu_api["maintenance_stop"] = "NA"
            asu_api["maintenance_message"] = "NA"
            asu_api["maintenance_date"] = "NA"
            asu_api["system_id"] = os.environ["exl_system_id"]

        else:
            primary_result = raw_exlib_api_status["result"][0]

            if ("details" in primary_result) and (primary_result["details"] != ""):
                parsed_details = (
                    primary_result["details"]
                    .replace("<br />", " ")
                    .replace("<b>", "")
                    .replace("</b>", "")
                    .replace("<strong>", "")
                    .replace("</strong>", "")
                    .replace("\\n", " ")
                    .replace("\n", " ")
                    .replace("\\r", "")
                    .replace("\r", "")
                ).strip()
                parsed_details = re.sub(r"\s{2,}", " ", parsed_details)
                parsed_details = re.sub(r"<a[^<]+?>|</a>", "", parsed_details)
            else:
                parsed_details = ""

            env = re.search(
                "we will be performing the following maintenance on your (Sandbox|Production) environment",
                parsed_details,
            )

            if (primary_result["type"] == "planned") and (
                primary_result["begin"] == ""
            ):
                if env:
                    asu_api["affected_env"] = env.group(1)
                    asu_api["service_status"] = "OK, Maintenance Scheduled"
                    asu_api["maintenance"] = True
                    asu_api["maintenance_start"] = utc_to_local_time(
                        message_time_parse(parsed_details, "start")
                    )
                    asu_api["maintenance_stop"] = utc_to_local_time(
                        message_time_parse(parsed_details, "stop")
                    )
                    asu_api[
                        "maintenance_message"
                    ] = f"Due to routine maintenance, Library One Search may be unavailable between {asu_api['maintenance_start'].strftime('%B %-d at %-I:%M %p')} and {asu_api['maintenance_stop'].strftime('%B %-d at %-I:%M %p')}, Phoenix time. We apologize for the inconvenience."
                    asu_api["maintenance_date"] = (
                        message_time_parse(parsed_details, "start")
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    asu_api["system_id"] = primary_result["cmdb_ci.u_external_name"]
                else:
                    asu_api["service_status"] = "unknown"
                    asu_api["maintenance"] = "unknown"
                    asu_api["affected_env"] = "unknown"
                    asu_api["maintenance_start"] = "unknown"
                    asu_api["maintenance_stop"] = "unknown"
                    asu_api["maintenance_message"] = "unknown"
                    asu_api["maintenance_date"] = "unknown"
                    asu_api["system_id"] = "unknown"

            elif (primary_result["type"] == "planned") and (
                primary_result["begin"] != ""
            ):
                asu_api["service_status"] = "Maintenance In-Progress"
                asu_api["maintenance"] = True
                asu_api["maintenance_start"] = "NA"
                asu_api["maintenance_stop"] = "NA"
                asu_api[
                    "maintenance_message"
                ] = "Library One Search is currently undergoing routine maintenance and may be intermittently unavailable. We apologize for the inconvenience."
                asu_api["maintenance_date"] = "NA"
                asu_api["affected_env"] = env.group(1)
                asu_api["system_id"] = primary_result["cmdb_ci.u_external_name"]

            elif primary_result["type"] == "outage" and (primary_result["begin"] != ""):
                asu_api["service_status"] = "OUTAGE"
                asu_api["affected_env"] = "NA"
                asu_api["maintenance"] = False
                asu_api["maintenance_start"] = "NA"
                asu_api["maintenance_stop"] = "NA"
                asu_api["maintenance_message"] = "NA"
                asu_api["maintenance_date"] = "NA"
                asu_api["system_id"] = primary_result["cmdb_ci.u_external_name"]

            else:
                asu_api["service_status"] = "Possible service interruption"
                asu_api["maintenance"] = "unknown"
                asu_api["affected_env"] = "unknown"
                asu_api["maintenance_start"] = "unknown"
                asu_api["maintenance_stop"] = "unknown"
                asu_api["maintenance_message"] = "unknown"
                asu_api["maintenance_date"] = "unknown"
                asu_api["system_id"] = "unknown"

        table.update_item(
            Key={"product": "Primo"},
            UpdateExpression=(
                "SET last_update = :val1, affected_env = :val2, maintenance = :val3, "
                "maintenance_message = :val4, raw_api_response = :val5, "
                "service_status = :val6, maintenance_date = :val7"
            ),
            ExpressionAttributeValues={
                ":val1": now,
                ":val2": asu_api["affected_env"],
                ":val3": asu_api["maintenance"],
                ":val4": asu_api["maintenance_message"],
                ":val5": raw_exlib_api_status,
                ":val6": asu_api["service_status"],
                ":val7": asu_api["maintenance_date"],
            },
        )

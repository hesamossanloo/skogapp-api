import json
import requests
import os
import pandas as pd
import Bio_growth
import numpy as np

# Airtable configuration
AIRTABLE_PERSONAL_ACCESS_TOKEN = os.getenv('AIRTABLE_PERSONAL_ACCESS_TOKEN')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')

def log(forestID, message):
    if forestID:
        print(f"forestID: {forestID} - {message}")
    else:
        forestID = "unknown"
        print(f"forestID: {forestID} - {message}")
        
def model(event):
    print("Running the model...")
    data = json.loads(event['body'])
    if not data:
        print("Received empty body.")
        response = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing body'})
        }
        return add_cors_headers(response)
    yield_requirement = float(data.get('yield_requirement', 0.03) ) # Default to 0.03 if 'yield_requirement' is not provided
    
    forestID = data.get('forestID')
    # if forestID is not found, the function will not proceed
    if not forestID:
        airtableResponse = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing forestID'})
        }
        return add_cors_headers(airtableResponse)
    log(forestID, f"Received body: {data}")
    # Airtable configuration
    TABLE_NAME = f'{forestID}_bestandsdata'
    AIRTABLE_API_URL = f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_NAME}'
    
    # Fetch data from Airtable
    log(forestID, f"Fetching data from Airtable for Table name: {TABLE_NAME}")
    airtable_data = fetch_airtable_data(AIRTABLE_API_URL)
    df_airtable = pd.DataFrame(airtable_data)
    log(forestID, f"Fetched {len(df_airtable)} records from Airtable.")

    # Process the DataFrame using Bio_growth.main
    log(forestID, f"Running Bio_growth model with yield requirement: {yield_requirement}")
    df_bestander = Bio_growth.main(df=df_airtable, yield_requirement=yield_requirement, forestID=forestID)
    log(forestID, f"Bio_growth model completed.")

    # Replace missing values with 0
    df_bestander.fillna(0, inplace=True)

    # Convert DataFrame to a dictionary or JSON serializable format
    result = df_bestander.to_dict(orient='records')

    # Get existing records from Airtable
    log(forestID, f"Fetching existing records from Airtable for Table name: {TABLE_NAME}")
    existing_records = get_existing_records(AIRTABLE_API_URL)
    log(forestID, f"Fetched {len(existing_records)} existing records from Airtable.")

    # Prepare batches of records to be sent
    records_to_update = []
    records_to_create = []
    unique_updates = {}
    for record in result:
        bestand_id = record.get('bestand_id')
        if bestand_id in existing_records:
            unique_updates[bestand_id] = {'id': existing_records[bestand_id], 'fields': record}
        else:
            records_to_create.append({'fields': record})

    # Ensure unique updates only
    records_to_update = list(unique_updates.values())

    batch_size = 10
    log(forestID, f"Updating records in batches...")
    for i in range(0, len(records_to_update), batch_size):
        batch = records_to_update[i:i + batch_size]
        airtableResponse = batch_update_airtable_records(batch, AIRTABLE_API_URL)
        if airtableResponse.status_code in [200, 201]:
            updated_ids = [record['fields']['bestand_id'] for record in batch]
            log(forestID, f"Updated batch of {len(batch)} records: {updated_ids}")
        else:
            log(forestID, f"Failed batch update")
            response = {
                'statusCode': airtableResponse.status_code,
                'body': json.dumps({'error': 'Failed to update records to Airtable', 'details': airtableResponse.json()})
            }
            return add_cors_headers(response)

    log(forestID, f"Creating records in batches...")
    for i in range(0, len(records_to_create), batch_size):
        batch = records_to_create[i:i + batch_size]
        airtableResponse = batch_create_airtable_records(batch, AIRTABLE_API_URL)
        if airtableResponse.status_code in [200, 201]:
            created_ids = [record['fields']['bestand_id'] for record in batch]
            log(forestID, f"Created batch of {len(batch)} records: {created_ids}")
        else:
            log(forestID, f"Failed batch create")
            response = {
                'statusCode': airtableResponse.status_code,
                'body': json.dumps({'error': 'Failed to create records to Airtable', 'details': airtableResponse.json()})
            }
            return add_cors_headers(response)

    log(forestID, "Data update completed.")
    response = {
        'statusCode': 200,
        'body': json.dumps({'message': 'Data update completed'})
    }
    return add_cors_headers(response)

def fetch_airtable_data(airtableURL):
    headers = {
        'Authorization': f'Bearer {AIRTABLE_PERSONAL_ACCESS_TOKEN}',
    }
    params = {
        'pageSize': 100
    }
    all_records = []
    while True:
        response = requests.get(airtableURL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        records = data['records']
        all_records.extend(record['fields'] for record in records)
        if 'offset' in data:
            params['offset'] = data['offset']
        else:
            break
    return all_records

def get_existing_records(airtableURL):
    headers = {
        'Authorization': f'Bearer {AIRTABLE_PERSONAL_ACCESS_TOKEN}',
    }
    params = {
        'pageSize': 100
    }
    records = {}
    while True:
        response = requests.get(airtableURL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        for record in data['records']:
            fields = record.get('fields', {})
            bestand_id = fields.get('bestand_id')
            if bestand_id:
                records[bestand_id] = record['id']
        if 'offset' in data:
            params['offset'] = data['offset']
        else:
            break
    return records

def batch_update_airtable_records(records, airtableURL):
    headers = {
        'Authorization': f'Bearer {AIRTABLE_PERSONAL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {'records': records}
    response = requests.patch(airtableURL, json=data, headers=headers)
    return response

def batch_create_airtable_records(records, airtableURL):
    headers = {
        'Authorization': f'Bearer {AIRTABLE_PERSONAL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {'records': records}
    response = requests.post(airtableURL, json=data, headers=headers)
    return response

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def lambda_handler(event, context):
    if event['httpMethod'] == 'OPTIONS':
        response = {
            'statusCode': 200,
            'body': json.dumps({})
        }
        return add_cors_headers(response)
    elif event['httpMethod'] == 'POST':
        return model(event)
    else:
        response = {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
        return add_cors_headers(response)
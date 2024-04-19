import asyncio
import uuid
import requests
from fastapi import BackgroundTasks
import time
import urllib.parse
test_video_url  = "https://www.youtube.com/watch?v=l3qi3E40aWE"
base_url = "http://127.0.0.1:8000"


def full_test():
    response = requests.post(f"{base_url}/remove-vocals", json={"youtube_url": test_video_url}).json()
    request_id = response['request_id']
    wait_until_done(request_id)

def wait_until_done(request_id):
    status = "pending"
    while status != "success":
        status_response = requests.get(f"{base_url}/check-status/{request_id}").json()
        status = status_response["status"]
        print(f"Current status: {status_response['status']}. Progress: {status_response.get('progress', 'N/A')}")
        if status == "error":
            print(f"Error message: {status_response['error_message']}")
            break
        time.sleep(0.25)  # Poll every 1 second

    if status == "success":
        print("Sucessfully removed vocals, downloading file now")
        output_path = status_response['output_path']
        output_file = requests.get(urllib.parse.urljoin(base_url, output_path))
        with open(status_response['filename'], 'wb') as f:
            f.write(output_file.content)
        print(f"Download completed: {status_response['filename']}")
        
 
def run_tmp_api():
    base_url = "http://127.0.0.1:8000"
    response = requests.get(f"{base_url}/run-temp").json()
    request_id = 'temp'
    wait_until_done(request_id)

run_tmp_api()
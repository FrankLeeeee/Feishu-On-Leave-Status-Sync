import requests
from datetime import datetime, timedelta
import json
import argparse
from pytz import timezone
from pathlib import Path

TIME_ZONE = timezone('Asia/Shanghai')
DB_PATH = "data.cache"

def parse_args():
    parser = argparse.ArgumentParser(description='Sync time from Feishu On-Leave Approval to Calendar')
    parser.add_argument('--hours', type=int, default=2, help='Check the approval in the last N hours')
    parser.add_argument('--approval-code', type=str, help='The approval code for on-leave application')
    parser.add_argument('--app-id', type=str, help='The app id for Feishu App')
    parser.add_argument('--app-secret', type=str, help='The app secret for Feisu App')
    return parser.parse_args()

def get_datetime_now():
    now = datetime.now(TIME_ZONE)
    # truncate the second and microsecond
    now = now.replace(second=0, microsecond=0)
    return now

def get_time_stamp(date_time: datetime):
    # convert to unix timestamp to microseconds
    return int(date_time.timestamp() * 1000)
    

def get_time_before(date_time: datetime, hours: int):
    return date_time - timedelta(hours=hours)

def get_feishu_tenant_token(app_id: str, app_secret: str):
    URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    data = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    response = requests.post(URL, json=data, headers=headers)
    return response.json()['tenant_access_token']


def get_approval_list(tenant_acccess_token: str,
                      approval_code: str,
                      start_time: int,
                      end_time: int
                    ):
    URL = "https://open.feishu.cn/open-apis/approval/v4/instances"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {tenant_acccess_token}"
    }
    query_params = {
        "approval_code": approval_code,
        "start_time": start_time,
        "end_time": end_time
    }
    response = requests.get(URL, headers=headers, params=query_params)
    return response.json()

def get_instance_form_data(tenant_acccess_token: str, instance_id: str):
    URL = f"https://open.feishu.cn/open-apis/approval/v4/instances/{instance_id}"
    headers = {
        "Authorization": f"Bearer {tenant_acccess_token}"
    }
    response = requests.get(URL, headers=headers)
    data = response.json()

    def _extract_form_data(data: dict):
        form_data = json.loads(data['data']['form'])[0]
        # from pprint import pprint
        # pprint(data)
        extracted_data = {
            "start_time": form_data['value']['start'],
            "end_time": form_data['value']['end'],
            "name": form_data['value']['name'],
            "user_id": data['data']['user_id']
        }
        return extracted_data
    
    return _extract_form_data(data)

def create_onleave_calendar(
        tenant_acccess_token: str,
        user_id: str, name: str, start_time: str, end_time: str):
    URL = "https://open.feishu.cn/open-apis/calendar/v4/timeoff_events"

    # convert the date string to a datetime object
    start_date = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S%z")
    end_date = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S%z")

    # format the date object to MM/DD
    start_date_str = start_date.strftime("%m/%d")
    end_date_str = end_date.strftime("%m/%d")

    # get the timestamp
    start_time_stamp = int(get_time_stamp(start_date) / 1000)
    end_time_stamp = int(get_time_stamp(end_date) / 1000)

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {tenant_acccess_token}"
    }
    query_params = {
        "user_id_type": "user_id"
    }
    data = {
        "user_id": user_id,
        "timezone": "Asia/Shanghai",
        "start_time": f"{start_time_stamp}",
        "end_time": f"{end_time_stamp}",
        "title": f"{name}, {start_date_str} - {end_date_str}",
        "description": "此日程由机器人自动生成"
    }
    response = requests.post(URL, headers=headers, params=query_params, json=data)
    return response.json()
    

def load_cache_data():
    with open(DB_PATH, 'r') as f:
        data = json.load(f)
    return data

def save_cache_data(data: dict):
    with open(DB_PATH, 'w') as f:
        json.dump(data, f)

def main():
    args = parse_args()

    # get feishu tenant access token
    tenent_access_token = get_feishu_tenant_token(args.app_id, args.app_secret)

    # get time stamps
    end_time = get_datetime_now()
    start_time = get_time_before(end_time, args.hours)
    start_time_stamp = get_time_stamp(start_time)
    end_time_stamp = get_time_stamp(end_time)

    # get approval list
    approval_list = get_approval_list(tenent_access_token, args.approval_code, start_time_stamp, end_time_stamp)
    
    # get instance code list
    instance_code_list = approval_list['data']['instance_code_list']

    # cache data 
    if Path(DB_PATH).exists():
        cache_data = load_cache_data()
    else:
        cache_data = dict(instance_ids=[])

    # create on-leave status
    for instance_code in instance_code_list:
        if cache_data and instance_code in cache_data['instance_ids']:
            continue

        instance_data = get_instance_form_data(tenent_access_token, instance_code)
        
        # create on-leave calendar
        out = create_onleave_calendar(
            tenent_access_token,
            instance_data['user_id'],
            instance_data['name'],
            instance_data['start_time'],
            instance_data['end_time']
        )

        cache_data['instance_ids'].append(instance_code)

    # make sure data does not exceed 1024 to truncate old data
    if len(cache_data['instance_ids']) > 1024:
        cache_data['instance_ids'] = cache_data['instance_ids'][-1024:]

    # save cache data
    save_cache_data(cache_data)
    
if __name__ == '__main__':
    main()


    



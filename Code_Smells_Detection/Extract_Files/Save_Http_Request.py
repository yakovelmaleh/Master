import Code_Smells_Detection.Extract_Files.PATH as PATH
import requests
import datetime
import time

headers = {"Authorization": f"token {PATH.GITHUB_TOKEN}"}


def _validate_http_request(response, url, get_data=None):
    if response.status_code == 200:
        return get_data(response) if get_data is not None else response
    else:
        raise Exception(f"❌ HTTP request failed: {url} with code: {response.status_code}")


def get(url_api, get_data=(lambda content: content.json()), second_run: bool = False):
    response = requests.get(url_api, headers=headers)

    try:
        response = _validate_http_request(response, url_api, get_data)
        return response

    except Exception as e:
        if second_run:
            raise e

        remaining = int(response.headers.get("X-RateLimit-Remaining", 1))

        if remaining == 0:

            reset_ts = int(response.headers.get("X-RateLimit-Reset", 0))

            if reset_ts > 0:

                reset_time = datetime.datetime.fromtimestamp(reset_ts)
                now = datetime.datetime.utcnow()
                wait_seconds = max((reset_time - now).total_seconds(), 0)

                print(f"⚠️ Rate limit exceeded. Sleeping for {int(wait_seconds)} seconds...")
                time.sleep(wait_seconds)

                # Retry once after sleeping
                return get(url_api=url_api,
                           get_data=get_data,
                           second_run=True)

        raise e


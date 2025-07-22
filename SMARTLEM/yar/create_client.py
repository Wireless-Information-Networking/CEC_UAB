import requests

url = 'https://sirienergy.uab.cat/create_user'

headers = {
    "Content-Type": "application/json",
}

data = {
        "user_name": "Jhon",
        "user_email": "jhondoe@uab.cat",
        "user_password": "69220"
        }

try:
    response = requests.post(url, headers=headers, json=data)
    print(response.status_code)
    if response.status_code == 200:
        correct_response = response.json()
        print(correct_response)
    else:
        error = response.json()    
        print(f"Error: {error}")

except requests.exceptions.RequestException as e:
    print(f"Connection error: {e}")



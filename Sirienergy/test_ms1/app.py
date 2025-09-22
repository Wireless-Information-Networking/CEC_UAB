from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/test_ms1', methods=['GET'])
def test_ms1():
    return jsonify({"message": "Hello from OPEN4CEC testing microservice!"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    # Process the incoming message here
    # For example, you can extract the message and user ID
    message = data.get('message', '')
    user_id = data.get('userId', '')
    response_message = f'Hello User {user_id}, you said: {message}'
    return jsonify({'reply': response_message})

@app.route('/vote', methods=['POST'])
def vote():
    # Retrieve vote information from the request
    vote_data = request.json
    # Process the vote data (e.g., store it in a database)
    return jsonify({'status': 'Vote received', 'vote': vote_data})

if __name__ == '__main__':
    app.run(debug=True)
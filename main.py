from flask import Flask, request, jsonify
from flask_mongoengine import MongoEngine
import jwt
import json
import uuid
import redis

app = Flask(__name__)

with open('config.json', 'r') as config_file:
    config_data = json.loads(config_file.read())

app.config['MONGODB_SETTINGS'] = {
    'db': config_data['mongo_db'],
    'host': config_data['mongo_host'],
    'port': config_data['mongo_port']
}

app.config['REDIS_SETTINGS'] = {
    'db': config_data['redis_db'],
    'host': config_data['redis_host'],
    'port': config_data['redis_port']
}

app.config['SECRET_JWT'] = config_data['secret_value']

db = MongoEngine()
db.init_app(app)

redis_db = redis.Redis(host=app.config['REDIS_SETTINGS']['host'], port=app.config['REDIS_SETTINGS']['port'], db=app.config['REDIS_SETTINGS']['db'])


class User(db.Document):
    name = db.StringField()
    password = db.StringField()
    follower = db.ListField(default=[])
    following = db.ListField(default=[])

@app.route('/sign_up', methods=['POST'])
def sign_up():
    username = request.form['username']
    password = request.form['password']

    if not username or not password:
        return jsonify({'message': 'Some data are missing'}), 400

    username_db = User.objects(name=username).first()

    if username_db:
        return jsonify({'message': 'This user already exists'}), 400

    user = User(name=username, password=password)
    user.save()

    return jsonify({'message': 'Success'}), 200

@app.route('/log_in', methods=['POST'])
def log_in():
    username = request.form['username']
    password = request.form['password']

    if not username or not password:
        return jsonify({'message': 'Some data are missing'}), 401

    username_db = User.objects(name=username, password=password).first()

    if not username_db:
        return jsonify({'message': 'Username or password is incorrect'}), 401

    token = jwt.encode({'user': username, 'uuid': uuid.uuid4().hex}, key=app.config['SECRET_JWT'], algorithm='HS256')
    redis_db.set(username, token)
    redis_db.expire(username, 30*60)

    return token, 200

@app.route('/follow', methods=['GET'])
def follow():
    access_token = request.headers['X-Access-Token']

    if not access_token:
        return jsonify({'message': 'Access token is missing'}), 401

    user = None

    try:
        user = jwt.decode(access_token, app.config['SECRET_JWT'], algorithms='HS256')
    except jwt.exceptions.InvalidSignatureError:
        return jsonify({'message': 'Access token is invalid'}), 401

    db_token = redis_db.get(user['user']).decode()

    if not db_token or db_token != access_token:
        return jsonify({'message': 'Access token is expired'}), 401

    username_to_be_follow = request.args['username']

    if not username_to_be_follow:
        return jsonify({'message': 'Some data are missing'}), 400

    username_to_be_follow_db = User.objects(name=username_to_be_follow).first()
    user_db = User.objects(name=user['user']).first()

    if not username_to_be_follow_db:
        return jsonify({'message': 'This user does not exist'}), 400

    if username_to_be_follow_db.name == user_db.name:
        return jsonify({'message': 'You cannot follow yourself'}), 400

    if user_db.name not in username_to_be_follow_db.follower:
        following = user_db.following
        following.append(username_to_be_follow_db.name)
        user_db.update(following=following)

        follower = username_to_be_follow_db.follower
        follower.append(user_db.name)
        username_to_be_follow_db.update(follower=follower)

    return jsonify({'message': 'Success'}), 200

if __name__ == '__main__':
    app.run()
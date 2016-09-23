# System imports

# Third-party imports
from flask import Blueprint
from flask import jsonify
from flask import request

# Local source tree imports
from core.models import User
from core.decorators import (validate_json, validate_schema)

from core.exceptions import NappsEntryDoesNotExists

# Flask Blueprints
api = Blueprint('user_api', __name__)

@api.route("/api/users/", methods=["POST"])
@validate_json
@validate_schema(User.schema)
def register_user():
    """
    This endpoing will be used to add a new user into the system.
    :return: Return HTTP code 201 if user were succesfully and 4XX in case of
    failure.
    """
    content = request.get_json()
    try:
        User.get(content['username'])
        return jsonify({"error": "Username already exists"}), 401
    except NappsEntryDoesNotExists:
        # TODO: Create user with all attributes
        user = User(username=content['username'],
                    password=content['password'],
                    email=content['email'],
                    first_name=content['first_name'],
                    last_name=content['last_name'])
        user.save()
        token = user.create_token()
        user.send_token()
        return '', 201

@api.route('/api/users/', methods=['GET'])
def get_users():
    """
    This routine creates an endpoint that shows all applications developers
    (application authors) with their information. It returns all information
    in JSON format.
    """

    users = {user.username: user.as_dict() for user in User.all()}
    return jsonify({'users': users }), 200

@api.route('/api/users/<username>/', methods=['GET'])
def get_user(username):
    """
    This routine creates an endpoint that shows details about a specific
    application author. It returns all information in JSON format.
    """
    try:
        user = User.get(username)
    except NappsEntryDoesNotExists:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(user.as_dict()), 200

@api.route("/api/users/<username>/confirm/<token>/", methods=["GET"])
def confirm_user(username, token):
    # Check if user exists
    try:
        user = User.get(username)
    except NappsEntryDoesNotExists:
        return jsonify({"error": "User not found"}), 404

    if not (user.token):
        return jsonify({"error": "Invalid token"}), 400

    # Check if token belongs to user and is a valid token
    if (user.token.hash != token) or (not user.token.is_valid()):
        return jsonify({"error": "Invalid token"}), 400

    user.enable()
    user.token.invalidate()
    user.send_welcome()
    return '', 200

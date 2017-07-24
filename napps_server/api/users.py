"""Module to manager users."""

# Third-party imports
from flask import Blueprint, Response, jsonify, redirect, request
from redis.exceptions import RedisError

# Local source tree imports
from napps_server.core.decorators import (requires_token, validate_json,
                                          validate_schema)
from napps_server.core.exceptions import InvalidUser, NappsEntryDoesNotExists
from napps_server.core.models import User
from napps_server.core.utils import get_request_data

# System imports


# Flask Blueprints
api = Blueprint('user_api', __name__)


@api.route("/users/", methods=["POST"])
@validate_json
@validate_schema(User.schema)
def register_user():
    """Method used to register new user into the system.

    This method will register  '/users/' endpoint and receive POST requests.
    If the username already exists will return a JSON with a error message and
    HTTP code 403, otherwise will return HTTP code 201 and a empty string.

    Returns:
        HTTP code 201 if the user was successfully created.
        HTTP code 403 if the user already exists.
    """
    content = get_request_data(request, User.schema)

    try:
        User.get(content.get('username'))
        return Response("error: Username already exists", 403)
    except NappsEntryDoesNotExists:
        user = User(username=content.get('username', ''),
                    email=content.get('email', ''),
                    first_name=content.get('first_name', ''),
                    last_name=content.get('last_name', ''),
                    phone=content.get('phone', None),
                    city=content.get('city', None),
                    state=content.get('state', None),
                    country=content.get('country', None))

        user.set_password(content['password'])
        user.save()
        user.create_token()
        user.send_token()
        return Response('User successfully created.', 201)


@api.route('/users/', methods=['GET'])
def get_users():
    """Method used to show all applications developers.

    This method will creates '/users/' endpoint that shows all application
    author usernames with their informations.

    Returns:
        json (string): JSON with detailed users.
    """
    users = {user.username: user.as_dict() for user in User.all()}
    return jsonify({'users': users}), 200


@api.route('/users/<username>/', methods=['GET'])
def get_user(username):
    """Method used to show details about a specific user.

    This method creates '/users/<username>/' endpoint that shows details
    about a specific application author. If the username can't be found
    by system will return HTTP code 404 and a error message. Otherwise will
    return the HTTP code 200 and render a json with user informations.

    Parameters:
        username (string): Name of a user.
    Returns:
        json (string): JSON with all information about a specific author.
        HTTP code 404 if the user was not found
    """
    try:
        user = User.get(username)
    except NappsEntryDoesNotExists:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(user.as_dict()), 200


@api.route("/users/<username>/confirm/<token>/", methods=["GET"])
def confirm_user(username, token):
    """Method used to confirm the user and his token.

    This method will get a username and a token and verify if they are valid.
    If these are invalid must return the HTTP code 40X and a JSON with the
    message error. Otherwise must return the HTTP code 200.

    Parameters:
        username (string):  Name of a user.
        token (string): valid token.
    Returns:
        HTTP code 307 redirect to the NApps Repository home page if the
            confirmation was successful.
        HTTP code 401 if user does not hold a valid Token or if the url passed
            token does not match the user token.
        HTTP code 404 if the user was not found
    """
    # Check if user exists
    url = 'http://napps.kytos.io?{}'

    try:
        user = User.get(username)
    except NappsEntryDoesNotExists:
        return redirect(url.format("user_not_found"), code=404)

    # Check if token belongs to user and is a valid token
    if not (user.token and user.token.hash == token):
        return redirect(url.format('invalid_token'), code=401)

    user.enable()
    user.token.invalidate()
    user.send_welcome()
    return redirect(url.format('activated'), code=307)


# @api.route("/users/<username>/", methods=['DELETE'])
@requires_token
def delete_user(user, username):
    """Method used to create an endpoint to delete an user.

    The endpoint created is /users/<username>/
    Parameters:
        username (string)
    Returns:
        HTTP code 200 if the user was successfully deleted.
        HTTP code 403 if the username does not match the authenticated user
        HTTP code 500 if any unexpected error occurs while deleting the user.
    """
    if not user.username == username:
        msg = 'You cannot delete other users.'
        return jsonify({'error': msg}), 403

    try:
        user.delete()
    except (RedisError, InvalidUser):
        msg = 'Ops! Something went wrong while trying to delete the user {}'
        return jsonify({'error': msg.format(username)}), 500

    msg = 'The user {} was deleted.'.format(username)
    return jsonify({'success': msg}), 200

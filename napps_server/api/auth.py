"""Method used to perform user authentication."""

# System imports

# Third-party imports
from flask import Blueprint, Response, jsonify, request

# Local source tree imports
from napps_server.core.decorators import requires_auth, requires_token
from napps_server.core.models import User
from napps_server.core.utils import authenticate

# Flask Blueprints
api = Blueprint('auth_api', __name__)


@api.route("/auth/", methods=["GET"])
@requires_auth
def napps_auth():
    """Endpoint to perform the authentication.

    :return: A token to the user
    """
    auth = request.authorization
    user = User.get(auth.username)
    if not auth or not User.check_auth(auth.username, auth.password):
        return authenticate()
    token = user.create_token()
    return jsonify(token.as_dict()), 201


@api.route("/auth/verify/", methods=["POST"])
@requires_token
def check_token(user):
    """Enpoint to check user authentication token.

    If the token is a valid token and the token is from the given user, then
    return 201, except return 401.
    Returns:
        201 if the token is still valid and is related to the user
        401 otherwise.
    """
    msg = 'User {} authorization correctly verified'.format(user.username)
    return Response(msg, 201)

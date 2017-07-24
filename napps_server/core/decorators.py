"""Module with main decorators used by napps-server."""
from functools import wraps

from flask import Response, jsonify, request
from jsonschema import ValidationError, validate

from napps_server.core.exceptions import NappsEntryDoesNotExists
from napps_server.core.models import Token, User
from napps_server.core.utils import authenticate, get_request_data


def validate_json(f):
    """Method used to validate a json from request."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        """Wrapper called to validate a json from request."""
        if request.form is None and request.get_json() is None and \
                request.get_data() is None:
            return jsonify({'error': "Payload must be a valid json"}), 400
        return f(*args, **kwargs)
    return wrapper


def validate_schema(schema):
    """Method used to validate a json from request using a schema."""
    def decorator(f):
        """Decorator to be called when validate_schema is called."""
        @wraps(f)
        def wrapper(*args, **kwargs):
            """Wrapper to validate the schema."""
            content = get_request_data(request, schema)

            try:
                validate(content, schema)
            except ValidationError as e:
                return Response(e.message, 400)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def requires_auth(f):
    """Method used to handle user authentication."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        """Wrapper to verify the user authentication."""
        auth = request.authorization
        if not auth or not User.check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return wrapper


def requires_token(f):
    """Method used to handle tokens from requests."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        """Wrapper used to verify the requires of token."""
        content = request.get_json()
        if content is None:
            token = request.form['token']
        else:
            token = content.get('token', None)

        try:
            token = Token.get(token)
            if not token or not token.is_valid():
                raise NappsEntryDoesNotExists
        except NappsEntryDoesNotExists:
            return authenticate()
        except (KeyError, TypeError):
            return Response("Invalid request", 400)

        # Otherwise just send them where they wanted to go
        return f(token.user, *args, **kwargs)

    return wrapper

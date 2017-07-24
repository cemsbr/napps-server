"""Module with main abstraction of models used by napps-server."""

# System imports
import json
import re
import smtplib
from copy import deepcopy
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from hashlib import md5

import bcrypt
from docutils import core

# Local source tree imports
from napps_server import config
from napps_server.core.exceptions import (InvalidNappMetaData, InvalidUser,
                                          NappsEntryDoesNotExists)
from napps_server.core.utils import generate_hash, render_template

db_con = config.DB_CON
napps_api_url = config.NAPPS_API_URL


class User(object):
    """Class to manage User Models."""

    schema = {
        "username": {"type": "string"},
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "password": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "city": {"type": "string"},
        "state": {"type": "string"},
        "country": {"type": "string"},
        "required": ["username", "first_name", "password", "email"]
    }

    def __init__(self, username, email, first_name, last_name,
                 phone=None, city=None, state=None, country=None,
                 enabled=False):
        """Constructor used to create a new user.

        Parameters:
            username (string): username of a new user.
            email (string): email of a new user.
            first_name (string): first name of a new user.
            last_name (string): last name of a new user.
            phone (string): phone number of a new user.
            city (string): city of a new user.
            state (string): state of a new user.
            country (string): contry of a new user.
            enabled (bool): indicate if the user is active.
        """
        self.username = username
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.phone = phone
        self.city = city
        self.state = state
        self.country = country
        self.enabled = enabled
        self.password = None

    @classmethod
    def attributes(cls):
        """Method used to return a set of attributes from User class.

        Returns:
            attributes_name (set): Set of attributes.
        """
        excludes = set(['required'])
        attributes_names = set(User.schema)
        return attributes_names.difference(excludes)

    @property
    def avatar(self):
        """Return an avatar url based on user email.

        Returns:
            string: Avatar url.
        """
        email_hash = md5(self.email.encode('utf-8'))
        avatar_url = 'https://www.gravatar.com/avatar/'
        avatar_url += email_hash.hexdigest()
        avatar_url += '?d=https%3A%2F%2Favatars.githubusercontent.com%2Fkytos'
        return avatar_url

    @property
    def redis_key(self):
        """Method used to built a redis key.

        Returns:
            key (string): String with redis key.
        """
        return "user:{}".format(self.username)

    @property
    def token(self):
        """Method used to return a token from User instance.

        Returns:
            token (string): key to identify a user.
        """
        try:
            key = db_con.lrange("%s:tokens" % self.redis_key, 0, 0)[0]
        except IndexError:
            return None

        attributes = db_con.hgetall(key)
        token = Token.from_dict(attributes)
        if token.is_valid():
            return token

    @classmethod
    def get(cls, username):
        """Method used to get a user of a given username.

        Parameters:
            username (string): Username of a valid user registered.

        Returns:
            user (:class:`napps.core.models.User`):
                User class with the given username.
        """
        attributes = db_con.hgetall("user:%s" % username)
        if attributes:
            user = User.from_dict(attributes)
            user.password = attributes['password'].encode('utf-8')
            return user
        else:
            msg = "User {} not found.".format(username)
            raise NappsEntryDoesNotExists(msg)

    @classmethod
    def all(cls):
        """Method used to return all users registered.

        Returns:
            users (list): List of users registered.
        """
        users = db_con.smembers("users")
        return [User.get(re.sub(r'^user:', '', user)) for user in users]

    @classmethod
    def check_auth(cls, username, password):
        """Method used to verify authenticity of a user.

        Parameters:
            username (string): Name of user registered.
            password (string): Password of a given username.
        Returns:
            result (bool): True if the user have the given password or False
                           otherwise.
        """
        try:
            user = User.get(username)
        except NappsEntryDoesNotExists:
            return False

        if not bcrypt.checkpw(password.encode('utf-8'), user.password):
            return False
        return True

    @classmethod
    def from_dict(cls, attributes):
        """Method to create a user based on attributes from a dict.

        Paramters:
            attributes (dict): Dict with user attributes.
        Returns:
            user (:class:`napps.core.models.User`): User class built from dict.
        """
        user = User(attributes['username'], attributes['email'],
                    attributes['first_name'], attributes['last_name'])

        for attribute in User.attributes():
            setattr(user, attribute, attributes.get(attribute, None))

        user.enabled = attributes.get('enabled') == 'True'

        return user

    def set_password(self, password):
        """Update the password attribute of a User.

        Parameters:
            password (string): New password to be updated.
        """
        password = password.encode('utf-8')
        self.password = bcrypt.hashpw(password, bcrypt.gensalt())
        self.save()

    def disable(self):
        """Method used to disable the user."""
        self.enabled = False
        token = self.token
        token.invalidate()
        self.save()

    def enable(self):
        """Method used to enable the user."""
        self.enabled = True
        self.save()

    def as_dict(self, hide_sensible=True, detailed=False):
        """Method used to return a User as a python dict.

        Parameters:
            hide_sensible (bool): used to show or hide the password.
            detailed (bool): used to show napps,comments and token attributes.
        Return:
            user (dict): Python dict with user informations.
        """
        result = deepcopy(self.__dict__)
        if hide_sensible:
            del result['password']

        if detailed:
            result['napps'] = "%s:napps" % self.redis_key
            result['comments'] = "%s:comments" % self.redis_key
            result['tokens'] = "%s:tokens" % self.redis_key

        return result

    def as_json(self, hide_sensible=True, detailed=False):
        """Method used to return a User as a JSON format.

        Parameters:
            hide_sensible (bool): used to show or hide the password.
            detailed (bool): used to show napps,comments and token attributes.
        Return:
            user (string): JSON format with user informations.
        """
        return json.dumps(self.as_dict(hide_sensible, detailed))

    def save(self):
        """Save a object into redis database.

        This is a save/update method. If the user already exists then update.
        """
        if not self.password:
            raise InvalidUser('Impossible to save a user without password.')
        db_con.sadd("users", self.redis_key)
        db_con.hmset(self.redis_key, self.as_dict(hide_sensible=False,
                                                  detailed=True))

    def delete(self):
        """Delete a object into redis databse.

        This method will delete the user instance and yours napps.
        """
        if not self.password:
            msg = 'Impossible to delete a user without password.'
            raise InvalidUser(msg)

        for napp in self.get_all_napps():
            napp.delete()

        if db_con.delete(self.redis_key) == 0 or \
           db_con.srem('users', self.redis_key) == 0:
            return False
        return True

    def create_token(self, expiration_time=86400):
        """Method used to create a valid token.

        Parameters:
            expiration_time (int): integer to represent token lifetime.
        Returns:
            token (:class:`napps_server.core.models.Token`):
                Token class created.
        """
        token = Token(user=self, expiration_time=expiration_time)
        token.save()
        db_con.lpush("%s:tokens" % self.redis_key, token.redis_key)
        return token

    def send_email(self, template, subject):
        """Method used to send a email."""
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = 'no-reply@kytos.io'
        message['To'] = self.email
        part1 = MIMEText(template, 'html')
        message.attach(part1)
        try:
            smtp = smtplib.SMTP('localhost')
            smtp.sendmail('no-reply@kytos.io', self.email, message.as_string())
            smtp.quit()
        except smtplib.SMTPRecipientsRefused:
            return '', 500
        except ConnectionRefusedError:
            msg = 'Ops, some error occurred while trying to send an email to '
            msg += '{}, please contact the admin team at contact@kytos.io.'
            return msg.format(self.email), 500

    def send_token(self):
        """Method used to send a message with a valid token to a user."""
        if not self.token:
            return False

        context = {'napps_api_url': napps_api_url,
                   'username': self.username,
                   'token': self.token.hash}

        html = render_template('confirm_user.phtml', context)
        self.send_email(html, 'Kytos NApps Repository: Confirm your account')

    def send_welcome(self):
        """Method used to send a welcome message to a user."""
        if not self.enabled:
            return False

        context = {'username': self.username}
        html = render_template('welcome.phtml', context)
        self.send_email(html, 'Welcome to Kytos NApps Repository')

    def get_all_napps(self):
        """Method used to return a list of napps.

        Returns:
            napps (list): list of Napps from this user.
        """
        napps = db_con.smembers("{}:napps".format(self.redis_key))
        return [Napp(db_con.hgetall(napp), self.username) for napp in napps]

    def get_napp_by_name(self, name):
        """Method used to return Napp with specific name.

        Parameters:
            name (string): Name of specific Napp.

        Return:
            napp (:class:`napps_server.core.models.NApp`):
                Napp found with the given name.
        """
        try:
            napp = Napp(db_con.hgetall("napp:{}/{}".format(self.username,
                                                           name)))
            return napp
        except Exception:
            msg = "Napp {} not found for user {}.".format(name, self.username)
            raise NappsEntryDoesNotExists(msg)


class Token(object):
    """Class to manage Tokens Models."""

    def __init__(self, hash_value=None, created_at=None, user=None,
                 expiration_time=86400):
        """Constructor of Token class.

        Parameters:
            hash (string): Hash to identify this token.This will be generated
            if the parameter is None.
            created_at (datetime): Datetime to register when this token was
                                   created.
            user (:class:`napps_server.core.models.User`):
                User that this token belong.
            expiration_time (int): integer to represent token lifetime.
        """
        self.hash = hash_value if hash_value else generate_hash()
        self.created_at = created_at if created_at else datetime.utcnow()
        self.user = user
        self.expiration_time = expiration_time

    @property
    def redis_key(self):
        """Method used to build a redis key.

        Returns:
            key (string): String with redis key.
        """
        return "token:{}".format(self.hash)

    @property
    def expires_at(self):
        """Method used to return the endtime of this token.

        Returns:
            end_time (datetime.timedelta): endtime of this token.
        """
        return self.created_at + timedelta(seconds=self.expiration_time)

    @classmethod
    def from_dict(cls, attributes):
        """Method used to create a Token based on dict with Token attributes.

        Parameters:
            attributes (dict): Python dictionary with Token attributes.

        Returns:
            token (:class:`napps_server.core.models.Token`):
                Token built using the given attributes.
        """
        return Token(attributes['hash'],
                     datetime.strptime(attributes['created_at'],
                                       '%Y-%m-%d %H:%M:%S.%f'),
                     User.get(attributes['user']),
                     int(attributes['expiration_time']))

    @classmethod
    def get(cls, token):
        """Method used to get a existing Token.

        Parameters:
            token (string): Token hash.
        Returns:
            token (:class:`napps_server.core.models.Token`):
                Token found from the given token hash.
        """
        attributes = db_con.hgetall("token:%s" % token)
        if attributes:
            return Token.from_dict(attributes)
        else:
            raise NappsEntryDoesNotExists("Token not found.")

    def is_valid(self):
        """Method to validate if the token instance is valid.

        Returns:
            is_valid (bool): True if this token is valid yet, otherwsise False.
        """
        return datetime.utcnow() <= self.expires_at

    def invalidate(self):
        """Method used to invalidate a token instance.

        This method will attribute 0 to the expiration_time attribute.
        """
        self.expiration_time = 0
        self.save()

    def as_dict(self):
        """Method used to create a dict based on current token instance.

        Returns:
            token (dict): Dict built from this Token attributes.
        """
        token = deepcopy(self.__dict__)
        token['user'] = self.user.username
        return token

    def as_json(self):
        """Method used to create a JSON string based on current token instance.

        Returns:
            json (string): JSON with attributes of current token instance.
        """
        token_dict = self.as_dict()
        return json.dumps(token_dict)

    def assign_to_user(self, user):
        """Method used to change the token user.

        Parameters:
            user (:class:`napps_server.core.models`):
                User that contain this token instance.
        """
        self.user = user

    def save(self):
        """Save a object into redis database.

        This is a save/update method. If the token exists then update.
        """
        db_con.sadd("tokens", self.redis_key)
        db_con.hmset(self.redis_key, self.as_dict())


class Napp(object):
    """Class to manage Napp models."""

    schema = {
        "username": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "long_description": {"type": "string"},
        "version": {"type": "string"},
        "napp_dependencies": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "uniqueItems": True},
        "license": {"type": "string"},
        "url": {"type": "string"},
        "readme": {"type": "string"},  # To be read from README.rst
        "tags": {"type": "array",
                 "items": {"type": "string"},
                 "minItems": 1,
                 "uniqueItems": True},
        "user": {"type": "string"},  # Not to be retrieved from json.
        "required": ["username", "name", "description"]
    }

    def __init__(self, content, user=None):
        """Constructor of Napp class.

        Parameters:
            content (dict): Basic informations  of new napp.
            user (:class:`napps_server.core.models.User`):
                Associate a user that belongs this Napp.
        """
        # WARNING: This will be removed in future versions, when 'author' will
        # be removed.
        username = content.get('username', content.get('author'))

        self.user = User.get(username)
        self.readme = ""
        if content is not None:
            self._populate_from_dict(content)

    @property
    def redis_key(self):
        """Method used to built a redis key.

        Returns:
            string: String with redis key.
        """
        return "napp:{}/{}".format(self.username, self.name)

    @property
    def readme_rst(self):
        """Method used to return a readme string from this Napp instance.

        Returns:
            readme (string): Text with details of this Napp.
        """
        return self.readme or self.long_description or self.description

    @property
    def readme_html(self):
        """Method used to build a html based on readme of the current instance.

        Returns:
            readme_html (string): Text with html based on readme.
        """
        parts = core.publish_parts(source=self.readme_rst, writer_name='html')
        return parts['body_pre_docinfo'] + parts['fragment']

    @classmethod
    def all(cls):
        """Method used to return all Napp instances.

        Returns:
            napps (list): List with all napps registered.
        """
        napps = db_con.smembers("napps")
        return [Napp(db_con.hgetall(napp)) for napp in napps]

    def _populate_from_dict(self, attributes):
        """Method used to populate a Napp instance based on python dict.

        Parameters:
            attributes (dict): Attributes of a Napp instance.
        """
        for key in self.schema:
            if key != 'required' and key != 'user':
                # This is a validation for required items...
                # But it can be improved
                if key in self.schema['required'] and key not in attributes:
                    raise InvalidNappMetaData('Missing key {}'.format(key))

                # Converting to list, if needed.
                if self.schema[key]['type'] == 'array' and \
                   not isinstance(attributes.get(key), list):
                    attributes[key] = list(attributes.get(key, []))

                setattr(self, key, attributes.get(key))

        self.readme = self.readme or self.long_description or self.description

    @classmethod
    def new_napp_from_dict(cls, attributes, user):
        """Method used to register a new Napp from dict.

        Parameters:
            attributes (dict):
                Python dictionary with napp attributes.
            user (:class:`napps_server.core.models.User`):
                User that belongs the new napp instance.
        Returns:
            napp (:class:`napps_server.core.models.Napp`):
                The new Napp instance registered.
        """
        napp = cls(attributes, user)
        if napp.user.username != napp.username:
            raise InvalidUser
        else:
            napp.save()
            return napp

    def update_from_dict(self, attributes):
        """Method used to update the Napp instance with dict attributes.

        Parameters:
            attributes (dict): Python dictionary with napp attributes.
        """
        if self.user.username != attributes.username:
            raise InvalidUser
        else:
            self._populate_from_dict(attributes)
            self.save()

    def as_dict(self):
        """Method used to create a dict based on Napp instance.

        Returns:
            json (string): JSON string with attributes from current instance.
        """
        data = {}
        for key in self.schema:
            if key != 'required':
                if self.schema[key]['type'] == 'array':
                    data[key] = getattr(self, key, [])
                else:
                    data[key] = getattr(self, key, '')
        data['user'] = self.username
        # WARNING: This will be removed in future versions, when 'author' will
        # be removed.
        data['author'] = self.username
        data['readme'] = self.readme_html

        # Add User avatar link
        user = User.get(self.username)
        data['avatar'] = user.avatar
        return data

    def as_json(self):
        """Method used to create a JSON based on Napp instance.

        Returns:
            json (string): JSON string with attributes from current instance.
        """
        data = self.as_dict()
        return json.dumps(data)

    def save(self):
        """Save a object into redis database.

        This is a save/update method. If the app exists then update.
        """
        db_con.sadd("napps", self.redis_key)
        db_con.sadd("user:%s:napps" % self.username, self.redis_key)
        data = self.as_dict()
        data['readme'] = self.readme_rst
        db_con.hmset(self.redis_key, data)

    def delete(self):
        """Delete a object from redis database."""
        if not self.user.password:
            msg = 'Impossible to delete a napp without password.'
            raise InvalidUser(msg)

        if db_con.delete(self.redis_key) == 0 or \
           db_con.srem('napps', self.redis_key) == 0 or \
           db_con.srem('{}:napps'.format(self.user.redis_key), self.redis_key):
            return False
        return True

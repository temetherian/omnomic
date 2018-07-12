#!/usr/bin/python

import base64
import json
import os
import re
import time
import uuid

from google.appengine.api import app_identity

try:
    from functools import lru_cache
except ImportError:
    from functools32 import lru_cache

import httplib2
from oauth2client.client import GoogleCredentials


_FIREBASE_SCOPES = [
    'https://www.googleapis.com/auth/firebase.database',
    'https://www.googleapis.com/auth/userinfo.email']

_FIREBASE_CONFIG = '_firebase_config.html'

_IDENTITY_ENDPOINT = ('https://identitytoolkit.googleapis.com/'
                      'google.identity.identitytoolkit.v1.IdentityToolkit')


# Memoize the authorized http, to avoid fetching new access tokens
@lru_cache()
def _get_http():
    """Provides an authed http object."""
    http = httplib2.Http()
    # Use application default credentials to make the Firebase calls
    # https://firebase.google.com/docs/reference/rest/database/user-auth
    creds = GoogleCredentials.get_application_default().create_scoped(
        _FIREBASE_SCOPES)
    creds.authorize(http)
    return http


@lru_cache()
def _get_firebase_db_url():
    """Grabs the databaseURL from the Firebase config snippet. Regex looks
    scary, but all it is doing is pulling the 'databaseURL' field from the
    Firebase javascript snippet"""
    regex = re.compile(r'\bdatabaseURL\b.*?["\']([^"\']+)')
    cwd = os.path.dirname(__file__)
    try:
        with open(os.path.join(cwd, 'templates', _FIREBASE_CONFIG)) as f:
            url = next(regex.search(line) for line in f if regex.search(line))
    except StopIteration:
        raise ValueError(
            'Error parsing databaseURL. Please copy Firebase web snippet '
            'into templates/{}'.format(_FIREBASE_CONFIG))
    return url.group(1)


def create_custom_token(channel_id, valid_minutes=60):
    """Create a secure token for the given id.
    This method is used to create secure custom JWT tokens to be passed to
    clients. It takes a unique id (uid) that will be used by Firebase's
    security rules to prevent unauthorized access. In this case, the uid will
    be the channel id which is a combination of user_id and game_key
    """

    # use the app_identity service from google.appengine.api to get the
    # project's service account email automatically
    client_email = app_identity.get_service_account_name()

    now = int(time.time())
    # encode the required claims
    # per https://firebase.google.com/docs/auth/server/create-custom-tokens
    payload = base64.b64encode(json.dumps({
        'iss': client_email,
        'sub': client_email,
        'aud': _IDENTITY_ENDPOINT,
        'uid': channel_id,
        'iat': now,
        'exp': now + (valid_minutes * 60),
    }))
    # add standard header to identify this as a JWT
    header = base64.b64encode(json.dumps({'typ': 'JWT', 'alg': 'RS256'}))
    to_sign = '{}.{}'.format(header, payload)
    # Sign the jwt using the built in app_identity service
    return '{}.{}'.format(to_sign, base64.b64encode(
        app_identity.sign_blob(to_sign)[1]))


def MaybeSendToChannel(channel_id, msg):
  """Send to channel if it exists, otherwise ignore it."""
  if not channel_id:
    return
  url = '{}/channels/{}.json'.format(_get_firebase_db_url(), channel_id)
  return _get_http().request(url, 'PUT', body=msg)


def DeleteChannel(channel_id):
  """Send to channel if it exists, otherwise ignore it."""
  if not channel_id:
    return
  url = '{}/channels/{}.json'.format(_get_firebase_db_url(), channel_id)
  return _get_http().request(url, 'DELETE')


#############
# Datastore #
#############

class PlayerClient(ndb.Model):
  player_id = ndb.StringProperty()
  auth_token = ndb.StringProperty(indexed=False)
  channel = ndb.StringProperty(indexed=False)

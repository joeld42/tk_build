import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin.firestore import SERVER_TIMESTAMP
from google.cloud import logging

default_app = firebase_admin.initialize_app()
db = firestore.client()

def create_job(request_json):

    # Get some info from the commit
    commit_ref = request_json['ref'] # Branch, e.g. refs/head/main
    commit_hash = request_json['after'] # Commit hash, eg 7aff1487f31a
    repo = request_json['repository']
    repo_name = repo['name']

    # TODO: Check commit_ref and don't make a job if it's not on master

    # Make a new document and set some stuff on it
    # FIXME: make Job work if defaults are omitted (like warnCount)
    for osTag in [ 'win', 'ios']:
        doc_ref = db.collection(u'jobs').document()
        doc_ref.set({
         'platform': osTag,
         'projectId': 'civclicker',
         'commitVer': commit_hash,
         'githubJson': None,
         'errorCount': 0, 'lastError': '', 'warnCount': 0,
         'version': '0.0.0', 'buildNum': 0,
         'worksteps': {'fetch': 'todo', 'build': 'todo', 'package': 'todo'},
         'tags' : [ osTag ],
         'timestamp': SERVER_TIMESTAMP} )

    return f'Created job(s) for %s (%s) on %s' % ( repo_name, commit_hash, commit_ref )

def on_civclicker_pushed(request):
    """Responds to any HTTP request.
    Args:
        request (flask.Request): HTTP request object.
    Returns:
        The response text or any set of values that can be turned into a
        Response object using
        `make_response <http://flask.pocoo.org/docs/1.0/api/#flask.Flask.make_response>`.
    """
    request_json = request.get_json()
    return create_job( request_json )

import os, sys, time, re
import datetime
import subprocess
from enum import Enum

import platform
import threading

import yaml

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


import google.cloud.logging
import logging

from tkbuild.job import TKBuildJob, TKWorkstepDef, JobStatus
from tkbuild.project import TKBuildProject
from tkbuild.agent import TKBuildAgent


def connectCloudStuff( agent, do_cloud_logging ):

    """ Connects to logging and firestore DB and returns the db connection"""

    # Initialze google stuff
    credKey = "GOOGLE_APPLICATION_CREDENTIALS"
    if not credKey in os.environ:
        print ("Creds:", agent.googleCredentialFile )
        os.environ[credKey] = agent.googleCredentialFile

    cred = credentials.Certificate( os.environ.get( credKey ) )
    firebase_admin.initialize_app(cred, {
      #'projectId': 'rising-environs-295900',
        'projectId' : agent.googleProjectId
    })
    db = firestore.client()

    # Initialize logging
    if do_cloud_logging:
        # logger = logging_client.logger("tkbuild-agent-" + agent.name )
        logging_client = google.cloud.logging.Client( )
        logging_handler = google.cloud.logging.handlers.CloudLoggingHandler(logging_client, name="tkbuild-agent-" + agent.name )
        google.cloud.logging.handlers.setup_logging( logging_handler )
    else:
        logging.basicConfig( level=logging.INFO )

    # logging.debug("log debug")
    # logging.info("log info")
    # logging.warning("log warn")
    # logging.error("log error")


    logging.info ( f"Agent: {agent.name}: {agent.desc}" )
    testRepoProj = None
    for p in agent.projects.values():
        logging.info( f"Project: {p.projectId} -- {p.repoUrl}" )

    return db


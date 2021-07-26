
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
        'projectId' : agent.googleProjectId
    })
    db = firestore.client()

    # Initialize logging
    if do_cloud_logging:
        # logger = logging_client.logger("tkbuild-agent-" + agent.name )
        logging_client = google.cloud.logging.Client( )

        logname = "tkbuild-agent-" + agent.name
        print("Log name is :", logname )

        logging_handler = google.cloud.logging.handlers.CloudLoggingHandler(logging_client, name=logname )
        google.cloud.logging.handlers.setup_logging( logging_handler )

        # Also echo to stdout
        rootLogger = logging.getLogger()
        #rootLogger.setLevel(logging.DEBUG)

        stdoutHandler = logging.StreamHandler(sys.stdout)
        #stdoutHandler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        stdoutHandler.setFormatter(formatter)
        rootLogger.addHandler(stdoutHandler)

    else:
        print("Cloud logging is off")
        # Just run with stdout logging for testing
        logging.basicConfig( level=logging.INFO )

    # logging.debug("log debug")
    # logging.info("log info")
    # logging.warning("log warn")
    # logging.error("log error")


    logging.info ( f"Agent: {agent.name}: {agent.desc}" )
    testRepoProj = None
    for p in agent.projects.values():

        fetchRepoUrl = "(No Fetch Step Defined)"
        pfetch = p.getFetchWorkstep()
        if pfetch:
            fetchRepoUrl = pfetch.repoUrl
        logging.info( f"Project: {p.projectId} -- {fetchRepoUrl}" )

    return db


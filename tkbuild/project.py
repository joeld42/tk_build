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

class TKBuildProject(object):

    def __init__(self ):
        self.projectId = "noname"
        self.projectDir = os.path.join( "/opt/tkbuild/", self.projectId )
        self.workDir = None
        self.repoUrl = None

        # Now fill in some computed defaults if some things aren't specified
        if self.workDir is None:
            self.workDir = os.path.join(self.projectDir, "workdir_" + self.projectId)

        self.workstepDefs = []

    @classmethod
    def createFromConfig( cls, configData ):
        proj = cls()
        proj.projectId = configData.get( "projectId", proj.projectId )
        proj.projectDir = configData.get( "projectDir", proj.projectDir )
        proj.repoUrl = configData.get( "repoUrl", "MISSING-REPO-URL" )
        if 'workDir' in configData:
            proj.workDir = configData['workDir']
        else:
            proj.workDir = os.path.join( proj.projectDir, "workdir_" + proj.projectId)

        if 'worksteps' in configData:
            for stepdef in configData['worksteps']:
                step = TKWorkstepDef()
                step.stepname = stepdef['name']
                step.cmd = stepdef.get('cmd', '' )
                if step.stepname=='fetch':
                    step.repoUrl = stepdef.get( 'repoUrl', '' )

                proj.workstepDefs.append( step )

        # Make an ordered list of workstep names for easy checking
        wsnames = []
        for wsdef in proj.workstepDefs:
            wsnames.append( wsdef.stepname )
        proj.workstepNames = wsnames

        return proj

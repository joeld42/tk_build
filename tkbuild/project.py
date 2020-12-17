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

DEFAULT_BUILD_NUM = 100

class TKBuildProject(object):

    def __init__(self ):
        self.projectId = "noname"
        self.projectDir = os.path.join( "/opt/tkbuild/", self.projectId )
        self.workDir = None
        self.icon = None
        self.bucketName = None

        # Now fill in some computed defaults if some things aren't specified
        if self.workDir is None:
            self.workDir = os.path.join(self.projectDir, "workdir_" + self.projectId)

        self.workstepDefs = []

    @classmethod
    def createFromConfig( cls, configData ):
        proj = cls()
        proj.projectId = configData.get( "projectId", proj.projectId )
        proj.projectDir = configData.get( "projectDir", proj.projectDir )
        proj.icon = configData.get("icon" )
        proj.bucketName = configData.get( "bucketName" )
        proj.info_ref = None
        proj.info = None

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

                step.artifact = stepdef.get('artifact', None )

                step.peekVersion = stepdef.get('peekVersion', None )

                proj.workstepDefs.append( step )

        # Make an ordered list of workstep names for easy checking
        wsnames = []
        for wsdef in proj.workstepDefs:
            wsnames.append( wsdef.stepname )
        proj.workstepNames = wsnames

        return proj

    def getFetchWorkstep(self):

        for wsdef in self.workstepDefs:
            if wsdef.stepname=='fetch':
                return wsdef

        return None

    def getProjectInfo(self, db ):
        if self.info_ref is None:
            self.info_ref = db.collection(u'projects').document( self.projectId )

            infosnap = self.info_ref.get()
            if not infosnap.exists:
                self.info = { 'build_num' : DEFAULT_BUILD_NUM }
                self.info_ref.set( self.info )
            else:
                self.info = infosnap.to_dict()

        return self.info

    def getBuildNumber(self, db ):

        info = self.getProjectInfo( db )

        return info.get( 'build_num', DEFAULT_BUILD_NUM )



    def incrementBuildNumber(self, db ):

        buildNum = self.getBuildNumber( db ) + 1
        self.info_ref.update( { 'build_num' : buildNum  })
        self.info = self.info_ref.get().to_dict()

        return self.info['build_num']


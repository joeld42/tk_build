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
        self.sortKey = 1000

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
        proj.sortKey = int(configData.get( "sortKey", 1000 ))

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

    def getRepoUrl(self):

        wsfetch = self.getFetchWorkstep()
        if wsfetch:
            return wsfetch.repoUrl
        return None

    def getCommitUrl(self, commit ):

        wsfetch = self.getFetchWorkstep()
        if not wsfetch:
            return None

        repoBase = wsfetch.repoUrl
        if repoBase.endswith( ".git"):
            repoBase = repoBase[:-4]

        commitUrl = os.path.join( repoBase, "commit", commit )

        return commitUrl

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
                self.info = { 'build_num' : DEFAULT_BUILD_NUM, 'latest_job' : "" }
                self.info_ref.set( self.info )
            else:
                self.info = infosnap.to_dict()

        return self.info

    def getCachedBuildNumber(self):
        return self.info.get( 'build_num', DEFAULT_BUILD_NUM )

    def getCachedLatestJob(self):

        result =  self.info.get( 'latest_job', '????' )
        print(f"getCachedLatestJob ProjectID {self.projectId} info {self.info} result {result}")
        return result

    def getBuildNumberAndJob(self, db ):

        info = self.getProjectInfo( db )
        buildNum = info.get( 'build_num', DEFAULT_BUILD_NUM )
        lastJobKey = info.get( 'latest_job')

        return (buildNum, lastJobKey )

    def getBuildNumber(self, db ):

        info = self.getProjectInfo( db )
        return info.get( 'build_num', DEFAULT_BUILD_NUM )



    def incrementBuildNumber(self, jobKey, db ):

        buildNum = self.getBuildNumber( db ) + 1
        self.info_ref.update( { 'build_num' : buildNum , 'latest_job' : jobKey })
        self.info = self.info_ref.get().to_dict()

        return self.info['build_num']


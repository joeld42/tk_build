import os, sys
from enum import Enum
import logging

class TKArtifact(object ):

    def __init__(self, id = "0000000"):
        self.id = id
        self.project = None
        self.jobKey = None
        self.builtFile = None
        self.commitVer = None

    def shortFilename(self):

        return os.path.split( self.builtFile )[-1]

    def toFirebaseDict(self):
        return {
            "project" : self.project,
            "jobKey" : self.jobKey,
            "commitVer" : self.commitVer,
            "builtFile" : self.builtfile,
        }

    @classmethod
    def createFromFirebaseDict(cls, id, dataDict ):

        artifact = cls( id )
        artifact.jobKey = dataDict.get( 'jobKey'  )
        artifact.project = dataDict.get('project' )
        artifact.commitVer = dataDict.get( 'commitVer' )
        artifact.builtFile = dataDict.get( 'builtFile' )

        return artifact
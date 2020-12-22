import os, sys
import datetime
import pytz

from enum import Enum
import logging

from firebase_admin.firestore import SERVER_TIMESTAMP

DEFAULT_ARTIFACT_DATE = datetime.datetime(2020, 12, 1, tzinfo=pytz.UTC)

class TKArtifact(object ):

    def __init__(self, id = "0000000"):
        self.id = id
        self.project = None
        self.jobKey = None
        self.builtFile = None
        self.commitVer = None
        self.timestamp = None

    def shortFilename(self):

        return os.path.split( self.builtFile )[-1]

    def toFirebaseDict(self):
        return {
            "project" : self.project,
            "jobKey" : self.jobKey,
            "commitVer" : self.commitVer,
            "builtFile" : self.builtfile,
            "timestamp" : SERVER_TIMESTAMP if self.timestamp is None else self.timestamp
        }

    @classmethod
    def createFromFirebaseDict(cls, id, dataDict ):

        artifact = cls( id )
        artifact.jobKey = dataDict.get( 'jobKey'  )
        artifact.project = dataDict.get('project' )
        artifact.commitVer = dataDict.get( 'commitVer' )
        artifact.builtFile = dataDict.get( 'builtFile' )
        artifact.timestamp = dataDict.get( 'timestamp', DEFAULT_ARTIFACT_DATE )

        return artifact
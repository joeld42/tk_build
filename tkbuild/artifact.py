import os, sys
import datetime
import pytz

from enum import Enum
import logging

from firebase_admin.firestore import SERVER_TIMESTAMP

DEFAULT_ARTIFACT_DATE = datetime.datetime(2020, 12, 1, tzinfo=pytz.UTC)

MANIFEST_PLIST_TEMPLATE = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>items</key>
    <array>
        <dict>
            <key>assets</key>
            <array>
                <dict>
                    <key>kind</key>
                    <string>software-package</string>
                    <key>url</key>
                    <string>{ipaFileURL}</string>
                </dict>
            </array>
            <key>metadata</key>
            <dict>
                <key>bundle-identifier</key>
                <string>{bundleId}</string>
                <key>bundle-version</key>
                <string>{version} ({buildNum})</string>
                <key>kind</key>
                <string>software</string>
                <key>title</key>
                <string>{appTitle}</string>
            </dict>
        </dict>
    </array>
</dict>
</plist>
"""

class TKArtifact(object ):

    def __init__(self, id = "0000000"):
        self.id = id
        self.project = None
        self.jobKey = None
        self.builtFile = None
        self.commitVer = None
        self.timestamp = None
        self.manifest = None

    def shortFilename(self):

        return os.path.split( self.builtFile )[-1]

    # Adds a manifest for .ipa (ios ad hoc) apps
    # TODO support a custom icon that the web server can display
    def addManifestInfo(self, appTitle, bundleIdentifier, version, buildNum, ipaFileURL ):

        self.manifest = {
            "appTitle"  : appTitle,
            "bundleId" : bundleIdentifier,
            "version"  : version,
            "buildNum" : buildNum,
            "ipaFileURL" : ipaFileURL,
            "manifestURL" : "unknown"   # build agent has to set this after uploading the manifest
        }

    def toFirebaseDict(self):
        fireDict = {
            "project" : self.project,
            "jobKey" : self.jobKey,
            "commitVer" : self.commitVer,
            "builtFile" : self.builtfile,
            "timestamp" : SERVER_TIMESTAMP if self.timestamp is None else self.timestamp
        }

        if self.manifest:
            fireDict.update({ "manifest" : self.manifest })

        return fireDict

    def generateManifestFile(self ):
        """Returns a string containing a text plist manifest for this artifact"""

        if not self.manifest:
            return None

        print("Manifest is:")
        print( self.manifest )

        return MANIFEST_PLIST_TEMPLATE.format( **self.manifest )



    @classmethod
    def createFromFirebaseDict(cls, id, dataDict ):

        artifact = cls( id )
        artifact.jobKey = dataDict.get( 'jobKey'  )
        artifact.project = dataDict.get('project' )
        artifact.commitVer = dataDict.get( 'commitVer' )
        artifact.builtFile = dataDict.get( 'builtFile' )
        artifact.timestamp = dataDict.get( 'timestamp', DEFAULT_ARTIFACT_DATE )
        artifact.manifest = dataDict.get( 'manifest' )

        return artifact
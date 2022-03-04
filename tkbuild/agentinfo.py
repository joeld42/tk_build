import os, sys
import datetime
import pytz

from enum import Enum
import logging

from firebase_admin.firestore import SERVER_TIMESTAMP

DEFAULT_AGENT_TIMESTAMP = datetime.datetime(2020, 12, 1, tzinfo=pytz.UTC)

class AgentStatus( str, Enum ):
    IDLE = 'idle'  # Idle and ready for a job
    BUSY = 'busy'  # Busy running a job
    PAUSED = 'paused' # Paused (e.g. for schedule)
    OFFLINE = 'offline' # Agent has gone offline
    STALE = 'stale' # Agent has not set status to offline, but not been heard from in a while

class TKAgentInfo(object ):

    def __init__(self, name, desc, id = "0000000" ):
        self.id = id
        self.name = name
        self.desc = desc
        self.tags = []
        self.status = AgentStatus.IDLE


    def toFirebaseDict(self):
        return {
            "name" : self.name,
            "tags" : self.tags,
            "desc" : self.desc,
            "timestamp": SERVER_TIMESTAMP,
            "status" : self.status }

    @classmethod
    def createFromFirebaseDict(cls, id, dataRef ):

        dataDict = dataRef.to_dict()

        name = dataDict.get('name')
        desc = dataDict.get('desc', 'No description' )

        agentInfo = cls( name, desc, id )
        agentInfo.tags = dataDict.get('tags')
        agentInfo.status = dataDict.get('status')
        agentInfo.timestamp = dataDict.get('timestamp', DEFAULT_AGENT_TIMESTAMP )

        return agentInfo


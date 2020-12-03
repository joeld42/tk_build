from enum import Enum
import logging

class TKWorkstepDef(object):
    def __init__(self):
        self.stepname = "unknown"
        self.cmd = ""

class JobStatus( str, Enum ):
    TODO = 'todo'
    SKIP = 'skip'
    RUN = 'run'
    CANCEL = 'cancel'
    DONE = 'done'
    FAIL = 'fail'


class TKBuildJob(object ):

    def __init__(self, projectId, jobKey = "0000000"):
        self.platform = "Unknown"
        self.jobKey = jobKey
        self.projectId = projectId
        self.commitVer = "1234"
        self.errorCount = 0
        self.warnCount = 0
        self.logLink = ""
        self.githubJson = None
        self.jobDirShort = "nojobdir"
        self.worksteps = {
            "fetch" : JobStatus.TODO
        }

    def __repr__(self):

        return f'<TKBuildJob({self.jobKey},projectId={self.projectId},commitVer={self.commitVer})>'

    def hasWorkRemaining(self, worksteps ):
        for stepname in worksteps:
            if stepname in self.worksteps:
                status = self.worksteps[stepname]
                if status == JobStatus.TODO:
                    return True

        return False

    def setWorkstepStatus(self, workstep, status ):

        if not workstep in self.worksteps:
            logging.warning( f"setWorkstepStatus for unknown workstep {workstep}")
            return

        self.worksteps[workstep] = status




    def toFirebaseDict(self):
        return {
            "platform" : self.platform,
            "projectId" : self.projectId,
            "commitVer" : self.commitVer,
            "errorCount" : self.errorCount,
            "warnCount" : self.warnCount,
            "logLink" : self.logLink,
            "githubJson" : self.githubJson,
            "worksteps" : self.worksteps
        }

    @classmethod
    def createFromFirebaseDict(cls, jobKey, jobDict ):

        job = cls( jobDict.get( 'projectId' ), jobKey )
        job.platform = jobDict.get( 'platform'  )
        job.commitVer = jobDict.get( 'commitVer' )
        job.errorCount = jobDict.get( 'errorCount' )
        job.warnCount = jobDict.get( 'warnCount' )

        # FIXME: how to check if these optional fields exist? The
        # example if u'logLink' in jobDict doesn't work
        job.logLink = jobDict.get('logLink')
        job.githubJson = jobDict.get( 'githubJson' )

        # Worksteps is a string : string dict in both, no conversion needed
        job.worksteps =jobDict.get( 'worksteps' )

        job.jobDirShort = job.projectId + "_" + jobKey

        return job

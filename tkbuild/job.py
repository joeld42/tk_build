from enum import Enum
import logging

class TKWorkstepDef(object):
    def __init__(self):
        self.stepname = "unknown"
        self.cmd = ""
        self.artifact = None

class JobStatus( str, Enum ):
    TODO = 'todo'
    SKIP = 'skip'
    RUN = 'run'
    CANCEL = 'cancel'
    DONE = 'done'
    FAIL = 'fail'

class ActiveStatus( str, Enum ):
    ACTIVE = 'active'

    CANCEL = 'cancel'
    FAIL = 'fail'
    DONE = 'done'


class TKBuildJob(object ):

    def __init__(self, project, jobKey = "0000000"):
        self.platform = "Unknown"
        self.jobKey = jobKey
        self.projectId = project.projectId
        self.commitVer = "1234"
        self.errorCount = 0
        self.warnCount = 0
        self.logLink = ""
        self.githubJson = None
        self.jobDirShort = "nojobdir"
        self.worksteps = {
            "fetch" : JobStatus.TODO
        }
        self._updateWSNames( project )

    def __repr__(self):

        return f'<TKBuildJob({self.jobKey},projectId={self.projectId},commitVer={self.commitVer})>'

    def setWorkstepStatus(self, stepname, status ):

        assert( stepname in self.worksteps.keys() )
        self.worksteps[ stepname ] = str(status)

    def _updateWSNames(self, project ):

        assert( project.projectId == self.projectId )
        wsnames = []
        for wsdef in project.workstepDefs:
            wsnames.append( wsdef.stepname )

        self.wsnames = wsnames

    def countError(self):
        self.errorCount += 1
        logging.info( f"Errorcount bumped, is now {self.errorCount}")

    def countWarning(self):
        self.warnCount += 1
        logging.info(f"Warncount bumped, is now {self.warnCount}")

    def isActive(self):
        return self.activeStatus() == ActiveStatus.ACTIVE

    def activeStatus(self):
        statuses = list(self.worksteps.values())
        print("Statuses are ", statuses)

        print( JobStatus.TODO,  JobStatus.TODO in statuses )

        # First, check if there are any steps running or todo
        if ((JobStatus.TODO in statuses) or
            (JobStatus.RUN in statuses)):
            return ActiveStatus.ACTIVE

        # Ok, job is completed but did it succeed? If any
        # step failed, then it counts as failed
        if (JobStatus.FAIL in statuses):
            return ActiveStatus.FAIL

        # Maybe nothing failed but the user cancelled it
        if (JobStatus.CANCEL in statuses):
            return ActiveStatus.CANCEL

        # Didn't fail or cancel, must of succeeded
        return ActiveStatus.DONE

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
    def createFromFirebaseDict(cls, project, jobKey, jobDict ):

        job = cls( project, jobKey )
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

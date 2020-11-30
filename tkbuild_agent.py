#!/usr/bin/env python3
import os, sys, time
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


def RunCommandInternal(process):
    while True:
        line = process.stdout.readline().rstrip()
        if not line:
            break
        yield line

def EchoRunCommand( settings, command):
    print( " ".join(command), flush=True )

    if (settings.dryRun):
        return (0, [], datetime.timedelta(0) )

    startTime = datetime.datetime.now()

    result = []
    process = subprocess.Popen(command, stdout=subprocess.PIPE) #, shell=True)

    for line in RunCommandInternal( process ):
        print(line, flush=True)
        result.append( line )

    process.wait()

    endTime = datetime.datetime.now()

    return (process.returncode, result, endTime - startTime)

# TODO: Handle this from config somewhere
# # export GOOGLE_APPLICATION_CREDENTIALS=/Users/joeld/stuff/firebasetest/firestore-key.json
# cred = credentials.Certificate( os.environ.get( "GOOGLE_APPLICATION_CREDENTIALS") )
# firebase_admin.initialize_app(cred, {
#   'projectId': 'rising-environs-295900',
# })
# db = firestore.client()
#
# logging_client = logging.Client( )
# logger = logging_client.logger("tkbuild-agent")

class JobStatus( str, Enum ):
    TODO = 'todo'
    SKIP = 'skip'
    RUN = 'run'
    CANCEL = 'cancel'
    DONE = 'done'
    FAIL = 'fail'


class TKBuildJob(object ):

    def __init__(self, projectId):
        self.jobKey = "0000000"
        self.platform = "Unknown"
        self.projectId = projectId
        self.commitVer = "1234"
        self.errorCount = 0
        self.warnCount = 0
        self.logLink = ""
        self.githubJson = None
        self.worksteps = {
            "fetch" : JobStatus.TODO
        }

    def __repr__(self):

        return f'<TKBuildJob({self.jobKey},projectId={self.projectId},commitVer={self.commitVer})>'

    def hasWorkRemaining(self):
        for status in self.worksteps.values():
            print("hasWorkRemaing, status ", status, JobStatus.TODO)
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

        job = cls( jobKey )
        job.platform = jobDict.get( 'platform'  )
        job.projectId = jobDict.get( 'projectId' )
        job.commitVer = jobDict.get( 'commitVer' )
        job.errorCount = jobDict.get( 'errorCount' )
        job.warnCount = jobDict.get( 'warnCount' )

        # FIXME: how to check if these optional fields exist? The
        # example if u'logLink' in jobDict doesn't work
        job.logLink = jobDict.get('logLink')
        job.githubJson = jobDict.get( 'githubJson' )

        # Worksteps is a string : string dict in both, no conversion needed
        job.worksteps =jobDict.get( 'worksteps' )

        return job

class TKWorkstepDef(object):
    def __init__(self):
        self.stepname = "unknown"
        self.cmd = ""

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

        return proj


class TKBuildAgentConfig(object):

    def __init__(self, agentConfigFile):
        self.googleCredentialFile = "MISSING"
        self.googleProjectId = "my-projectid-00000"
        self.projectConfigs = []

        print("Initializing build agent from config ", agentConfigFile)
        if not os.path.exists(agentConfigFile):
            print("WARN: agent config file doesn't exist or can't be read:", agentConfigFile)
        else:
            with open(agentConfigFile) as fpconfig:
                docs = yaml.full_load(fpconfig)

                agentCfg = docs.get("build-agent")
                print( agentCfg['name'] )
                print( agentCfg['desc'] )

                for projectCfgDoc in docs['projects']:
                    projectCfgData = projectCfgDoc['project']

                    project = TKBuildProject.createFromConfig( projectCfgData )


# An agent is a script that runs builds on a worker machine. One agent
# may have multiple projects
class TKBuildAgent(object):

    def __init__(self ):
        self.name = "unnamed-build-agent"
        self.desc = "TkBuild Build Agent"
        self.googleCredentialFile = "MISSING"
        self.googleProjectId = "my-projectid-00000"
        self.projects = {}
        self.platform = platform.system() # e.g. "Darwin"
        self.serverDone = False
        self.updCount = 0 # mostly for debugging

        self.db = None
        self.jobList = [] # Will be populated from the jobs callback

        # Set when something has changed and the worker should
        # run an update
        self.changeEvent = threading.Event()

        # This is the currently running job.
        self.currentJob = None

    @classmethod
    def createFromConfig( cls, configData ):
        agentCfg = configData.get("build-agent")

        agentCfg = configData.get("build-agent")

        agent = cls()
        agent.name = agentCfg.get( 'name', agent.name )
        agent.desc = agentCfg.get( 'desc', agent.desc )

        gcloudConfig = agentCfg.get('gcloud', {} )
        agent.googleCredentialFile = gcloudConfig.get( 'credfile', agent.googleCredentialFile )
        agent.googleProjectId = gcloudConfig.get( 'project-id', agent.googleProjectId  )

        for projectCfgDoc in configData.get('projects'):
            projectCfgData = projectCfgDoc['project']
            project = TKBuildProject.createFromConfig( projectCfgData )

            if project:
                agent.projects[project.projectId] = project

        return agent

    def commitJobChanges( self, job):

        job_ref = self.jobs_ref.get( job.jobKey )
        job_ref.set( job.toFirebaseDict() )


    def updateJobsList(self, jobs_ref ):

        newJobsList = []
        for jobRef in jobs_ref:
            job = TKBuildJob.createFromFirebaseDict( jobRef.id, jobRef )
            newJobsList.append( job )

            # TODO; wrap log_struct with something that can log to console too
            #self.logger.log_struct({ 'jobkey' : job.jobKey, 'worksteps' : job.worksteps } )

        self.jobList = newJobsList
        logging.info( f"Updated jobs list (length {len(self.jobList)}).")


    def onJobsListChanged( self, jobs, changes, read_time):
        #print( "On jobslist changed: ", jobs )
        logging.info( "Job list changed:")
        self.updateJobsList( jobs )

        # alert the main build that we might need to do some work
        self.changeEvent.set()

    @classmethod
    def createFromConfigFile(cls, agentConfigFile ):

        if not os.path.exists(agentConfigFile):
            logging.warning("WARN: agent config file doesn't exist or can't be read:", agentConfigFile)
        else:
            with open(agentConfigFile) as fpconfig:
                configData = yaml.full_load(fpconfig)
                return cls.createFromConfig( configData )

    def serverMainloop(self, db ):

        self.db = db

        # Set the jobs changed callback
        self.jobs_ref = db.collection(u'jobs')
        query_watch = self.jobs_ref.on_snapshot( self.onJobsListChanged )

        #self.updateJobsList(jobs_ref.get() )
        # for doc in jobs_ref.get():
        #     print(f'{doc.id} => {doc.to_dict()}')

        # Make some test jobs
        # testJob = TKBuildJob("testrepo")
        # testJob.commitVer = "ZZBLAR"
        # testJob.worksteps = {"fetch": "todo",
        #                      "build": "todo",
        #                      "archive": "todo"}
        #
        # print(f"Testjob: {testJob}")

        # testJobRef = db.collection(u'jobs').document()
        # testJobRef.set(testJob.toFirebaseDict())

        # Run the mainloop
        while not self.serverDone:

            print("update ...")
            self.serverUpdate()

            self.changeEvent.wait( 1.0  ) # TODO: make timeout an option
            self.changeEvent.clear()

    def serverUpdate(self):

        logging.info( f"Agent update ... {self.updCount}")
        self.updCount += 1


        logging.info( f" {len(self.jobList)} avail jobs:")
        # Check if there are any jobdirs that do not exist in the job list. If so, clean up those job dirs.
        for job in self.jobList:
            logging.info( f"JOB: {job.jobKey} steps: {job.worksteps} ")

            # If the job has work left to do
            if job.hasWorkRemaining():
                print("job ", job, "has work left...")
                self.currentJob = job
                break
            else:
                print( "No work remains", job, job.worksteps )


        # Did we find a job to run?
        if self.currentJob == None:
            logging.info("No matching jobs found to run.")
        else:
            # run the job
            self.runNextJobStep( self.currentJob )

            # clear the current job
            self.currentJob = None

        # Check if there are any jobs with todo worksteps that match the project and platform for this agent.
        #  (todo: sort/priority for these) If so:
        #     - Change workstep status to “running”
        #     - Do the workstep (call $PROJECT_DIR/workdir/$REPO_NAME/tkbuild workstep)
        #     - Change the workstep status to “Completed” or “Failed”


    def runNextJobStep(self, job ):

        logging.info("Run next job step....")
        # Go through the worksteps defined for this project and
        # do the next one that needs to be done for this job
        proj = self.projects[ job.projectId ]
        for wsdef in proj.workstepDefs:
            if ((wsdef.stepname in job.worksteps) and
                    (job.worksteps[wsdef.stepname] == JobStatus.TODO)):

                logging.info( f"TODO: Will do job step {wsdef.stepname}" )
                # TODO: actually do the workstep
                #todo use EchoRunCommand to actually do the workstep
                break






if __name__=='__main__':

    # TODO get this from environment or args
    agentCfgFile = "/opt/tkbuild/tkbuild_agent.yml"
    agent = TKBuildAgent.createFromConfigFile( agentCfgFile )

    # Initialze google stuff
    credKey = "GOOGLE_APPLICATION_CREDENTIALS"
    if not credKey in os.environ:
        print ("Creds:", agent.googleCredentialFile )
        os.environ[credKey] = agent.googleCredentialFile

    cred = credentials.Certificate( os.environ.get( credKey ) )
    firebase_admin.initialize_app(cred, {
      #'projectId': 'rising-environs-295900',
        'projectId' : agent.googleProjectId
    })
    db = firestore.client()

    # Initialize logging
    do_cloud_logging = False
    if do_cloud_logging:
        # logger = logging_client.logger("tkbuild-agent-" + agent.name )
        logging_client = google.cloud.logging.Client( )
        logging_handler = google.cloud.logging.handlers.CloudLoggingHandler(logging_client, name="tkbuild-agent-" + agent.name )
        google.cloud.logging.handlers.setup_logging( logging_handler )
    else:
        logging.basicConfig( level=logging.INFO )

    logging.debug("log debug")
    logging.info("log info")
    logging.warning("log warn")
    logging.error("log error")


    logging.info ( f"Agent: {agent.name}: {agent.desc}" )
    testRepoProj = None
    for p in agent.projects.values():
        logging.info( f"Project: {p.projectId} -- {p.repoUrl}" )


    agent.serverMainloop( db )

    logging.info( "Tkbuild agent finished, exiting.")

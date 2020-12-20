#!/usr/bin/env python3
import os, sys, time, re

import logging

from tkbuild.agent import TKBuildAgent
from tkbuild.cloud import connectCloudStuff

# TODOs to work on with dave:
# - Use google org authentication for bucket files
# - Generate link to jump to log or bucket in cloud console easily from tkbuild_web
# - Embed log view (query log directly?)
# - Tag/search log entries by job/workstep as well as just agent
# - Use google's auth stuff or add a simple password

if __name__=='__main__':

    # TODO get this from environment or args
    agentCfgFile = "/opt/tkbuild/tkbuild_agent.yml"
    agent = TKBuildAgent.createFromConfigFile( agentCfgFile )

    db = connectCloudStuff( agent, True )
    if not db:
        logging.error("Connecting to cloud stuff failed.")
        sys.exit(1)

    # Run the agent mainloop
    agent.serverMainloop( db )
    logging.info( "Tkbuild agent finished, exiting.")

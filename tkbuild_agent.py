#!/usr/bin/env python3
import os, sys, time, re

import logging

from tkbuild.agent import TKBuildAgent
from tkbuild.cloud import connectCloudStuff

if __name__=='__main__':

    # TODO get this from environment or args
    agentCfgFile = "/opt/tkbuild/tkbuild_agent.yml"
    agent = TKBuildAgent.createFromConfigFile( agentCfgFile )

    db = connectCloudStuff( agent )
    if not db:
        logging.error("Connecting to cloud stuff failed.")
        sys.exit(1)

    # Run the agent mainloop
    agent.serverMainloop( db )
    logging.info( "Tkbuild agent finished, exiting.")

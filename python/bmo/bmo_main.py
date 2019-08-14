#!/usr/bin/env python
# encoding: utf-8
#
# bmo_actor.py
#
# Created by José Sánchez-Gallego on 16 Feb 2017.


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import json
import sys
import traceback

from click.testing import CliRunner

from RO.StringUtil import strFromException
from twistedActor import BaseActor, CommandError, UserCmd

from bmo import __version__
from bmo.cmds.cmd_parser import bmo_parser
from bmo.devices.tcc_device import TCCDevice
from bmo.devices.manta import MantaCameraSet
from bmo.logger import log


LCOTCC_HOST = '10.1.1.20'
LCOTCC_PORT = 25000


class BMOActor(BaseActor):

    def __init__(self, config, controller, autoconnect=True, **kwargs):

        assert controller is not None, 'cannot initiate BMO without a valid camera controller.'

        self.cmdParser = bmo_parser
        self.config = config

        self.ds9 = None
        self.stop_exposure = False
        self.save_exposure = True

        self.cameras = {'on': None, 'off': None}
        self.centroids = {'on': None, 'off': None}
        self.fwhm = {'on': None, 'off': None}

        self.controller = controller

        log.info('connecting to TCC host={!r}, port={}.'.format(LCOTCC_HOST, LCOTCC_PORT))
        self.tccActor = TCCDevice('tcc', LCOTCC_HOST, LCOTCC_PORT)
        self.tccActor.dev_state.plateid_callback = self._plateid_change
        self.tccActor.writeToUsers = self.writeToUsers
        self.tccActor.connect()

        log.info('starting BMO actor version={!r} in port={}'
                 .format(__version__, kwargs['userPort']))

        super(BMOActor, self).__init__(**kwargs)

        # Sets itself as the default actor to write to when logging.
        log.set_actor(self)

        self.manta_cameras = MantaCameraSet(self.controller, actor=self)

        if autoconnect is True:
            log.debug('starting DS9.')
            cmd_ds9 = UserCmd(cmdStr='ds9 connect')
            self.parseAndDispatchCmd(cmd_ds9)

    def parseAndDispatchCmd(self, cmd):
        """Dispatch the user command."""

        def test_cmd(args):

            result = CliRunner().invoke(bmo_parser, args)
            if result.exit_code > 0:
                # If code > 0, there was an error. We fail the command and inform the users.
                textMsg = result.output
                for line in textMsg.splitlines():
                    line = json.dumps(line).replace(';', '')
                    cmd.writeToUsers('w', 'text={0}'.format(line))
                cmd.setState(cmd.Failed)
                return False
            else:
                if '--help' in args:
                    # If help was in the args, we just want to print the usage to the users.
                    textMsg = result.output
                    for line in textMsg.splitlines():
                        line = json.dumps(line).replace(';', '')
                        cmd.writeToUsers('w', 'text={0}'.format(line))
                    cmd.setState(cmd.Done)
                    return False

                return True

        if not cmd.cmdBody:
            # echo to show alive
            self.writeToOneUser(":", "", cmd=cmd)
            return

        cmd.setState(cmd.Running)

        try:
            result = test_cmd(cmd.cmdBody.split())
            if result is False:
                return
            bmo_parser(cmd.cmdBody.split(), obj=dict(actor=self, cmd=cmd))
        except CommandError as ee:
            cmd.setState('failed', textMsg=strFromException(ee))
            return
        except Exception as ee:
            sys.stderr.write('command {0!r} failed\n'.format(cmd.cmdStr))
            traceback.print_exc(file=sys.stderr)
            textMsg = strFromException(ee)
            hubMsg = 'Exception={0}'.format(ee.__class__.__name__)
            cmd.setState("failed", textMsg=textMsg, hubMsg=hubMsg)
        except BaseException:
            # This catches the SystemExit that Click insists in returning.
            pass

    def _plateid_change(self, plate_id):
        """Callback to be executed if the instrumentNum changes."""

        if plate_id is None:
            return

        log.info('detected new plate {}. Showing charts.'.format(plate_id), self)

        cmd_chart = UserCmd(cmdStr='ds9 show_chart {0}'.format(plate_id))
        self.parseAndDispatchCmd(cmd_chart)

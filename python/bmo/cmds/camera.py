#!/usr/bin/env python
# encoding: utf-8
#
# camera.py
#
# Created by José Sánchez-Gallego on 17 Feb 2017.


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import glob
import os

import astropy.io.fits
import click

from twisted.internet import reactor

from bmo.cmds import bmo_context
from bmo.logger import log

from bmo.utils import show_in_ds9, get_sjd, get_camera_coordinates

__all__ = ['camera']


def display_image(image, camera_type, actor, cmd):
    """Displays image in DS9 and gets centroids."""

    frame = 1 if camera_type == 'on' else 3

    try:
        centroid = show_in_ds9(image, frame=frame, ds9=actor.ds9)
    except Exception as ee:
        log.warning('failed to show image in DS9: {0}'.format(ee), actor)
        return False

    if not centroid:
        actor.writeToUsers('i', 'text="no centroid detected for '
                                '{0}-axis camera."'.format(camera_type))
    else:
        xx, yy, __, fwhm = centroid
        actor.writeToUsers('d', 'text="{0}-axis camera centroid detected '
                                'at ({1:.1f}, {2:.1f}) with fwhm {3:.2f} arcsec"'
                                .format(camera_type, xx, yy, fwhm))
        actor.centroids[camera_type] = (xx, yy)
        actor.fwhm[camera_type] = fwhm

    return True


def create_exposure_path(actor):
    """Returns the dirname and basename of the next valid exposure path."""

    sjd = get_sjd()

    dirname = os.path.join(actor.config['cameras']['save_path'], str(sjd))
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    files = sorted(glob.glob(os.path.join(dirname, '*.fits*')))

    if len(files) == 0:
        last_no = 0
    else:
        last_no = int(files[-1].split('.')[0].split('-')[-1])

    return dirname, 'bimg-{0:04d}.fits'.format(last_no + 1)


def do_expose(actor, cmd, camera_type, one=False, subtract_background=True):
    """Does the actual exposing.

    We keep this function separated because reactor.callLater does not seem to
    work with click.

    """

    if one:
        actor.stop_exposure = True

    camera = actor.cameras[camera_type]
    if camera is None:
        cmd.setState(cmd.Failed, '{0}-axis camera not connected.'.format(camera_type))
        return

    if camera.state != 'exposing':
        camera.state = 'exposing'

    def _process_image(image):
        """Callback to be called when an exposure completes."""

        # If the image is False something went wrong. We reconnect the cameras to
        if image is False:
            log.warning('failed to expose {0} camera. Skipping frame and '
                        'reconnecting the camera.'.format(camera_type))
            camera.reconnect()
            reactor.callLater(0.1, do_expose, actor, cmd, camera_type, one=False,
                              subtract_background=subtract_background)
            return

        # Substracts the background. Stores it for the next iteration.
        if subtract_background is True:
            try:
                camera.background = image.subtract_background(camera.background)
            except Exception as error:
                log.warning('failed to subtract background: {}'.format(error))
                log.warning('stopping cameras now. Consider rerunning with --no-background')
                actor.stop_exposure = True
                return

            log.debug('background mean: {0:.3f}'.format(camera.background.background_median),
                      actor)

        # Tries to display the image.
        display_image(image.data, camera_type, actor, cmd)

        camera_ra = camera_dec = None

        if actor.tccActor.dev_state.plate_id is not None:
            camera_ra, camera_dec = get_camera_coordinates(
                actor.tccActor.dev_state.plate_id,
                camera='center' if camera_type == 'on' else 'offaxis')

        image.set_hole_radec(camera_ra, camera_dec)

        fwhm = actor.fwhm[camera_type]
        fwhm = float('{:.2f}'.format(fwhm)) if fwhm else -999.

        extra_header = astropy.io.fits.Header(
            [('ALT', actor.tccActor.dev_state.tcc_pos[1], 'Telescope ALT'),
             ('AZ', actor.tccActor.dev_state.tcc_pos[0], 'Telescope AZ'),
             ('ROT', actor.tccActor.dev_state.tcc_pos[2], 'Telescope ROT'),
             ('CARTID', actor.tccActor.dev_state.instrumentNum, 'Cartridge ID'),
             ('PLATEID', actor.tccActor.dev_state.plate_id, 'Currently loaded plate'),
             ('CAMTYPE', camera_type + '-axis', 'Camera position (on/off-axis)'),
             ('SECORIEN', actor.tccActor.dev_state.secOrient, 'Secondary orientation'),
             ('STARFWHM', fwhm, 'Star FWHM measurement [arcsec]')])

        image.header.extend(extra_header)

        dirname, basename = create_exposure_path(actor)
        fn = image.save(dirname=dirname, basename=basename, compress=True)

        log.debug('saved {0}-axis image {1}'.format(camera_type, fn))

        if not actor.stop_exposure:
            reactor.callLater(0.1, do_expose, actor, cmd, camera_type, one=False,
                              subtract_background=subtract_background)
        else:
            log.info('stopping {0}-axis camera.'.format(camera_type))
            camera.state = 'idle'
            if not cmd.isDone:
                cmd.setState(cmd.Done)

    camera.expose(_process_image)


@click.group()
@click.pass_context
def camera(ctx):
    """Handles the cameras."""
    pass


@camera.command()
@click.option('--camera_type', default='all', type=click.Choice(['all', 'on', 'off']),
              show_default=True,
              help='whether to show all cameras (default) or only on- or off-axis ones.')
@bmo_context
def list(actor, cmd, camera_type):
    """Lists available and connected cameras."""

    cmd.writeToUsers('i', 'text="Avaliable cameras: {0!r}"'
                          .format(actor.manta_cameras.get_camera_ids()))

    for camera_type in ['on', 'off']:
        camera = actor.cameras[camera_type]
        if camera is None:
            cmd.writeToUsers('i', 'text="no {0}-axis camera found"'.format(camera_type))
        else:
            cmd.writeToUsers('i', 'text="{0}-axis camera: {1}"'.format(camera_type,
                                                                       camera.camera_id))

    cmd.setState(cmd.Done)

    return False


@camera.command()
@bmo_context
def reconnect(actor, cmd):
    """Forces cameras to reconnect."""

    actor.cameras.connect_all(reconnect=True)
    cmd.setState(cmd.Done)

    return False


@camera.command()
@click.option('--camera_type', default='all', type=click.Choice(['all', 'on', 'off']),
              show_default=True,
              help='whether to expose all connected cameras (default) or only on- or off-axis.')
@click.option('--background/--no-background', default=True, show_default=True,
              help='if True (default), substract a median background from the image.')
@click.option('-o', '--one', is_flag=True, show_default=True,
              help='if set, exposes once with each camera and stops.')
@bmo_context
def expose(actor, cmd, camera_type, background, one=False):
    """Exposes the cameras, showing the result in DS9."""

    camera_types = ['on', 'off'] if camera_type == 'all' else [camera_type]

    actor.stop_exposure = False  # Resets the trigger

    for ct in camera_types:
        log.info('starting exposure in {0}-axis camera.'.format(ct))
        do_expose(actor, cmd, ct, one=one, subtract_background=background)

    return False


@camera.command()
@bmo_context
def stop(actor, cmd):
    """Stops all current exposures."""

    actor.stop_exposure = True
    cmd.setState(cmd.Done)

    return False


@camera.command()
@click.argument('exptime', default=1.0, type=float)
@click.option('--camera_type', default='all', type=click.Choice(['all', 'on', 'off']),
              show_default=True,
              help='whether the exposure time should be set for all cameras (default) '
                   'or only on- or off-axis.')
@bmo_context
def exptime(actor, cmd, exptime, camera_type):
    """Sets the exposure time."""

    camera_types = ['on', 'off'] if camera_type == 'all' else [camera_type]

    for camera_type in camera_types:

        camera = actor.cameras[camera_type]
        if camera is None:
            actor.writeToUsers('w', 'text="{0}-axis camera not connected."'.format(camera_type))
            continue

        camera.camera.ExposureTimeAbs = 1e6 * exptime
        camera.background = None  # Clears background since it now needs to be recalculated.

        log.info('{0}-axis camera exptime set to {1:.1f}'.format(camera_type, exptime))

    cmd.setState(cmd.Done)

    return False

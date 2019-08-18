#!/usr/bin/env python
# encoding: utf-8
#
# utils.py
#
# Created by José Sánchez-Gallego on 6 Jan 2017.


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import numpy as np
import os
import re
import warnings

from astropy.wcs import WCS
import astropy.time as time

from bmo import pathlib, config
from bmo.exceptions import BMOError, BMOUserWarning

try:
    from sdssdb.observatory import database, platedb
except ImportError:
    warnings.warn('cannot import database connection.', BMOUserWarning)
    database = platedb = None

try:
    import PyGuide
except ImportError:
    PyGuide = None

try:
    import pyds9
except ImportError:
    pyds9 = None


__all__ = ('FOCAL_SCALE', 'PIXEL_SIZE', 'get_centroid', 'get_plateid',
           'get_camera_focal', 'get_translation_offset', 'get_rotation_offset',
           'show_in_ds9', 'read_ds9_regions', 'get_camera_coordinates', 'get_sjd',
           'get_acquisition_dss_path')

FOCAL_SCALE = config['telescope']['focal_scale']
PIXEL_SIZE = config['cameras']['pixel_scale']

DEFAULT_IMAGE_SHAPE = config['cameras']['image_shape']


# Makes sure database points to the right DB profile
if database:
    database.connect_from_config(config['DB']['profile'])


def get_plateid(cartID):
    """Gets the plateID for a certain cartID."""

    if cartID == 0:
        return None

    if database.check_connection() is False:
        raise BMOError('no database is available.')

    return platedb.Plate.select(platedb.Plate.plate_id).join(platedb.Plugging).join(
        platedb.ActivePlugging).where(platedb.ActivePlugging.pk == cartID).scalar()


def get_acquisition_dss_path(plate_id, camera='center'):
    """Returns the path for the acquisition camera DSS image in platelist."""

    assert os.environ['PLATELIST_DIR'] != '', 'platelist is not set.'
    assert camera in ['center', 'offaxis'], 'invalid camera type.'

    plate6 = str(plate_id).zfill(6)
    plate6XX = plate6[0:4] + 'XX'

    dss_path = (pathlib.Path(os.environ['PLATELIST_DIR']) /
                'plates/{plate6XX}/{plate6}/acquisitionDSS-r2-{plate6}-p1-{camera}.fits'
                .format(plate6=plate6, plate6XX=plate6XX, camera=camera))

    return dss_path


def get_camera_coordinates(plate_id, camera='center'):
    """Returns the RA/Dec coordinates for a camera."""

    assert camera in ['center', 'offaxis'], 'invalid camera type.'

    if database.check_connection() is False:
        raise BMOError('no database is available.')

    if camera == 'center':

        plate = platedb.Plate.get(plate_id=plate_id)

        if plate is None:
            raise BMOError('plate {0} not found.'.format(plate_id))

        on_ra = plate.plate_pointings[0].pointing.center_ra
        on_dec = plate.plate_pointings[0].pointing.center_dec

        return (float(on_ra), float(on_dec))

    else:

        # TODO: a better way of doing this would be to use xyfocal from the DB
        # and convert it to RA/Dec, but that requires rewriting xy2ad in Python.

        off_path = get_acquisition_dss_path(plate_id, camera='offaxis')
        assert off_path.exists(), 'off axis acquisition camera DSS image does not exist.'

        wcs = WCS(str(off_path))
        footprint = wcs.calc_footprint()

        return (footprint[:, 0].mean(), footprint[:, 1].mean())


def get_camera_focal(plate_id, camera='center'):
    """Returns the xyfocal coordinates for a camera."""

    assert camera in ['center', 'offaxis'], 'invalid camera type.'

    hole_type = 'ACQUISITION_{0}'.format(camera.upper())

    query = platedb.PlateHole.select().join(platedb.PlateHoleType).switch(
        platedb.PlateHole).join(platedb.PlateHolesFile).join(platedb.Plate).where(
            (platedb.Plate.plate_id == plate_id) & (platedb.PlateHoleType.label == hole_type))

    assert query.count() == 1, 'incorrect number of returned holes.'

    hole = query.first()

    return (float(hole.xfocal), float(hole.yfocal))


def get_centroid(image, return_fwhm=False):
    """Uses PyGuide to return the brightest centroid in an array."""

    if PyGuide is None:
        raise BMOError('PyGuide cannot be imported.')

    mask = np.zeros(image.shape, dtype=np.bool)

    # Masking to the right part of the image until we understand the origin of
    # the weird illumination pattern.
    # mask[:, 1900:] = 1

    ccdInfo = PyGuide.CCDInfo(np.median(image), 5, 5)
    stars = PyGuide.findStars(image, mask, None, ccdInfo)

    centroids = stars[0]
    assert len(centroids) > 0, 'no centroids found.'

    if not return_fwhm:
        return centroids[0]

    shape = PyGuide.StarShape.starShape(image.astype(np.float32), mask,
                                        stars[0][0].xyCtr, 100)

    if shape.fwhm:
        fwhm = float(shape.fwhm) * PIXEL_SIZE * FOCAL_SCALE
    else:
        fwhm = -999.

    return (centroids[0], fwhm)


def get_translation_offset(centroid, shape=DEFAULT_IMAGE_SHAPE, img_centre=None):
    """Calculates the offset from the centre of the image to the centroid.

    The offset signs are selected so that the returned offset is the one the
    telescope needs to apply to centre the star.

    Parameters:
        centroid (tuple):
            A tuple containing the x and y coordinates of the centroid to
            be centred, in image pixels.
        shape (tuple):
            The width and height of the original image, to determine the centre
            of the field.
        img_centre (tuple or None):
            A tuple containing the x and y coordinates of the centre of the
            image. If None, the centre of the array with shape ``shape`` will
            be used.

    Returns:
        trans_ra, tans_dec:
            Returns a tuple with the translation in RA and Dec, respectively,
            that needs to be applied to centre the centroid/star.


    """

    if img_centre is None:
        on_centre = np.array([shape[0] / 2., shape[1] / 2.])
    else:
        on_centre = np.array(img_centre, dtype=np.float)

    on_centroid = np.array(centroid)

    trans_ra, trans_dec = (on_centroid - on_centre) * PIXEL_SIZE * FOCAL_SCALE

    return trans_ra, trans_dec


def get_rotation_offset(plate_id, centroid, shape=DEFAULT_IMAGE_SHAPE,
                        translation_offset=None, img_centre=None):
    """Calculates the rotation offset.

    The offset signs are selected so that the returned offset is the one the
    telescope needs to apply to centre the star.

    Parameters:
        plate_id (int):
            The plate_id, used to determine the position of the off-axis camera
            on the plate.
        centroid (tuple):
            A tuple containing the x and y coordinates of the centroid to be
            centred, in image pixels.
        shape (tuple):
            The width and height of the original image, to determine the centre
            of the field.
        translation_offset (tuple or None):
            The ``(RA, Dec)`` translation offset in arcsec, as calculated by
            ``get_translation_offset``, to be applied before calculating the
            rotation offset. If ``None``, no translation offset will be
            applied.
        img_centre (tuple or None):
            A tuple containing the x and y coordinates of the centre of the
            image. If None, the centre of the array with shape ``shape`` will
            be used.

    Returns:
        rotation:
            Returns the rotation, in arcsec, that needs to be applied to centre
            the centroid/star.


    """

    def get_angle(x_focal, y_focal):
        """Returns the angle from the centre of the plate."""

        x_focal_rad = np.deg2rad(x_focal * FOCAL_SCALE / 3600)
        y_focal_rad = np.deg2rad(y_focal * FOCAL_SCALE / 3600)

        cc = np.arccos(np.cos(x_focal_rad) * np.cos(y_focal_rad))
        theta = np.rad2deg(np.arccos(np.tan(np.pi / 2. - cc) * np.tan(y_focal_rad)))

        # arccos always returns 0 to 180. Depending on the quadrant we return the correct value.
        if x_focal >= 0:
            return theta
        else:
            return 360 - theta

    centroid = np.array(centroid)
    shape = np.array(shape)

    xy_focal = get_camera_focal(plate_id, camera='offaxis')
    if not xy_focal:
        raise ValueError('cannot determine the x/yFocal of the off-axis camera for this plate. '
                         'The rotation offset cannot be calculated.')
    else:
        x_focal_centre, y_focal_centre = xy_focal

    angle_centre = get_angle(x_focal_centre, y_focal_centre)

    if translation_offset:
        translation_offset_pix = np.array(translation_offset) / FOCAL_SCALE / PIXEL_SIZE
        centroid -= translation_offset_pix

    # Calculates the x/yFocal of the centroid.

    if img_centre is None:
        img_centre = shape / 2.
    else:
        img_centre = np.array(img_centre, dtype=np.float)

    x_pix, y_pix = centroid - img_centre

    x_focal_off = x_focal_centre - x_pix * PIXEL_SIZE
    y_focal_off = y_focal_centre - y_pix * PIXEL_SIZE

    angle_off = get_angle(x_focal_off, y_focal_off)

    rotation = (angle_off - angle_centre) * 3600

    return rotation


def show_in_ds9(image, frame=1, ds9=None, zoom=None):
    """Displays an image in DS9, calculating star centroids.

    Parameters:
        image (Numpy ndarray):
            A Numpy ndarray containing the image to display.
        frame (int):
            The frame in which the image will be displayed.
        ds9 (pyds9 object or None or str):
            Either a ``pyds9`` object used to communicate with DS9, a string to
            be used to create such a connection, or ``None``. In the latter
            case ``pyds9.DS9`` will be called without arguments.
        zoom (int or None):
            The zoom value to set. If ``zoom=None`` and the zoom of the frame
            is 1, the zoom will be set to fit. Otherwise it keep the same zoom.

    Returns:
        result (None or tuple):
            If no centroid has been found for the image, returns ``None``.
            Otherwise, returns a tuple with the x, y position of the centroid,
            and the radius, as detected by PyGuide.

    Example:
        Opens a FITS file and displays it
          >>> data = fits.getdata('image.fits')
          >>> centroid = show_in_ds9(data, 'on_axis')
          >>> print(centroid)
          >>> (19.2, 145.1, 5.1)

    """

    if not isinstance(ds9, pyds9.DS9):
        if ds9 is None:
            raise ValueError('no DS9 connection available. Have you run bmo ds9 connect?')
        elif isinstance(ds9, str):
            ds9 = pyds9.DS9(ds9)
        else:
            raise ValueError('incorrect value for ds9 keyword: {0!r}'.format(ds9))

    try:
        centroid, fwhm = get_centroid(image, return_fwhm=True)
        xx, yy = centroid.xyCtr
        rad = centroid.rad
    except AssertionError:
        centroid = None

    ds9.set('frame {0}'.format(frame))
    ds9.set_np2arr(image)

    current_zoom = float(ds9.get('zoom'))

    if zoom is not None:
        ds9.set('zoom {0:.4f}'.format(zoom))
    else:
        if current_zoom == 1:
            ds9.set('zoom to fit')

    ds9.set('regions command {{point({0}, {1}) # point=cross 20, color=blue}}'.format(
        image.shape[1] / 2., image.shape[0] / 2.))

    if centroid:
        ds9.set('regions command {{circle({0}, {1}, {2}) # color=green}}'.format(xx, yy, rad))
        ds9.set('regions command {{text({0}, {1}) # text="{2:.2f}" color=green}}'
                .format(xx, yy + rad + 30, fwhm if fwhm else 0.0))
        return (xx, yy, rad, fwhm)

    return None


def read_ds9_regions(ds9, frame=1):
    """Reads regions from DS9 and returns the region centre and image dimensions."""

    ds9.set('frame {0}'.format(frame))
    regions = ds9.get('regions -format ds9 -system image')

    n_circles = regions.count('circle')
    if n_circles == 0:
        return False, 'no circle regions detected in frame {0}'.format(frame)
    elif n_circles > 1:
        return False, 'multiple circle regions detected in frame {0}'.format(frame)

    circle_match = re.match('.*circle\((.*)\)', regions, re.DOTALL)

    if circle_match is None:
        return False, 'cannot parse region in frame {0}'.format(frame)

    try:
        xx, yy = map(float, circle_match.groups()[0].split(',')[0:2])
    except Exception as ee:
        return False, 'problem found while parsing region for frame {0}: {1!r}'.format(frame, ee)

    try:
        height = int(ds9.get('fits height'))
        width = int(ds9.get('fits width'))
    except Exception as ee:
        return False, 'problem found while getting shape for frame {0}: {1!r}'.format(frame, ee)

    return True, (xx, yy, width, height)


def get_sjd(datetime=None):
    """Returns the SDSS Julian Day for ``datetime``. If ``datetime=None`` uses the current time."""

    if datetime is None:
        mjd = time.Time.now().mjd
    else:
        assert isinstance(datetime, time.Time)
        mjd = datetime.mjd

    return int(mjd + 0.4)

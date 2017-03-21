#!/usr/bin/env python
# encoding: utf-8
#
# manta.py
#
# Created by José Sánchez-Gallego on 7 Jan 2017.


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import os
import tempfile
# import time

import astropy.io.fits as fits
import numpy as np
import pymba


class MantaExposure(object):

    def __init__(self, data, exposure_time, camera_id):

        self.data = data
        self.exposure_time = np.round(exposure_time, 3)
        self.camera_id = camera_id

        self.header = fits.Header({'EXPTIME': self.exposure_time,
                                   'DEVICE': self.camera_id})

    def save(self, fn, overwrite=False):

        hdulist = fits.HDUList([fits.PrimaryHDU(data=self.data, header=self.header)])

        if overwrite is False:
            assert not os.path.exists(fn), \
                'the path exists. If you want to overwrite it use overwrite=True.'

        hdulist.writeto(fn, overwrite=overwrite)

    @classmethod
    def from_fits(cls, fn):

        hdulist = fits.open(fn)
        new_object = MantaCamera.__new__(cls)

        new_object.data = hdulist[0].data
        new_object.header = hdulist[0].header
        new_object.camera_id = hdulist[0].header['DEVICE']
        new_object.exposure_time = float(hdulist[0].header['EXPTIME'])

        return new_object


class MantaCamera(object):

    vimba = None

    def __new__(cls, *args, **kwargs):

        me = object.__new__(cls)

        if cls.vimba is None:
            cls.vimba = pymba.Vimba()
            cls.vimba.startup()

        return me

    def __init__(self, camera_id=None):

        self.open = True

        self.camera_id = camera_id
        self._last_exposure = None
        self.system = self.vimba.getSystem()
        self.system.runFeatureCommand('GeVDiscoveryAllOnce')

        self.cameras = self.vimba.getCameraIds()

        if camera_id:
            self.init_camera(camera_id)

    @staticmethod
    def list_cameras():

        with pymba.Vimba() as vimba:
            vimba.startup()
            system = vimba.getSystem()
            system.runFeatureCommand('GeVDiscoveryAllOnce')

            cameras = vimba.getCameraIds()

        return cameras

    def init_camera(self, camera_id):

        if camera_id not in self.cameras:
            raise ValueError('camera_id {0} not found. Cameras found: {1}'
                             .format(camera_id, self.cameras))

        self.camera = self.vimba.getCamera(camera_id)

        self.camera.openCamera()
        self.set_default_config()

        self.frames = [self.camera.getFrame(), self.camera.getFrame()]
        for frame in self.frames:
            frame.announceFrame()

        self.current_frame = self.frames[0]

        self.camera.startCapture()

        # frames = [self.camera.getFrame(),
        #           self.camera.getFrame(),
        #           self.camera.getFrame()]
        #
        # def frameCB(frame):
        #
        #     img_buffer = frame.getBufferByteData()
        #     img_data_array = np.ndarray(buffer=img_buffer,
        #                                 dtype=np.uint16,
        #                                 shape=(frame.height, frame.width))
        #
        #     # tmp_file = tempfile.NamedTemporaryFile(delete=False)
        #     outfile = tempfile.TemporaryFile()
        #     # hdulist = fits.HDUList([fits.PrimaryHDU(data=img_data_array)])
        #     # hdulist.writeto(tmp_file.name)
        #     np.save(outfile, img_data_array)
        #     outfile.seek(0)
        #
        #     self._last_exposure = MantaExposure(np.load(outfile),
        #                                         self.camera.ExposureTimeAbs / 1e6,
        #                                         self.camera.cameraIdString)
        #
        #     # if os.path.exists(tmp_file.name):
        #     #     os.remove(tmp_file.name)
        #
        #     frame.queueFrameCapture(frameCB)
        #
        # for frame in frames:
        #     frame.announceFrame()
        #     frame.queueFrameCapture(frameCB)

    def get_other_frame(self, current_frame=None):

        for frame in self.frames:
            if frame is not current_frame:
                return frame

        return frame

    def set_default_config(self):

        self.camera.PixelFormat = 'Mono12'
        self.camera.ExposureTimeAbs = 1e6
        self.camera.AcquisionMode = 'SingleFrame'

    def expose(self):

        # self.camera.startCapture()

        # self.camera.AcquisionMode = 'SingleFrame'
        # if exp_time:
        #     self.camera.ExposureTimeAbs = exp_time * 1e6

        frame_for_exp = self.get_other_frame(self.current_frame)
        frame_for_exp.queueFrameCapture()

        self.camera.runFeatureCommand('AcquisitionStart')
        self.camera.runFeatureCommand('AcquisitionStop')

        frame_for_exp.waitFrameCapture()

        # time.sleep(self.camera.ExposureTimeAbs / 1e6 + 0.5)

        img_buffer = frame_for_exp.getBufferByteData()
        img_data_array = np.ndarray(buffer=img_buffer,
                                    dtype=np.uint16,
                                    shape=(frame_for_exp.height,
                                           frame_for_exp.width))

        outfile = tempfile.TemporaryFile()
        np.save(outfile, img_data_array)
        outfile.seek(0)

        self._last_exposure = MantaExposure(np.load(outfile),
                                            self.camera.ExposureTimeAbs / 1e6,
                                            self.camera.cameraIdString)

        # self.camera.endCapture()

        return self._last_exposure

    def save(self, fn, exposure=None, **kwargs):

        assert exposure is not None or self._last_exposure is not None, \
            'no exposure provided. Take an exposure before calling save.'

        exposure = exposure or self._last_exposure
        exposure.save(fn, **kwargs)

    def close(self):
        self.camera.endCapture()
        self.camera.revokeAllFrames()
        # self.vimba.shutdown()

        self.open = False

    def __del__(self):
        """Destructor."""

        if self.open:
            self.close()

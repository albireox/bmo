.. _bmo-changelog:

==========
Change Log
==========

This document records the main changes to the BMO code.


.. _changelog-0.2.6:

0.2.6 (unreleased)
------------------

Changed
^^^^^^^
* PyGuide now returns the FWHM, which is output and shown in DS9.


.. _changelog-0.2.5:

0.2.5 (2019-08-12)
------------------

Fixed
^^^^^
* Swap values for ALT and AZ from ``tccPos``.


.. _changelog-0.2.4:

0.2.4 (2019-08-11)
------------------

Changed
^^^^^^^
* Hole coordinates are now saved to the header as ``HOLERA`` and ``HOLEDEC``. ``ALT`` and ``AZ`` now refer to the telescope values from the TCC.


.. _changelog-0.2.3:

0.2.3 (2019-07-12)
------------------

Fixed
^^^^^
* Fixed ``CDELT`` in the Manta WCS which was being written in arcsec instead of degrees.


.. _changelog-0.2.2:

0.2.2 (2018-04-26)
------------------

Changed
^^^^^^^
* Pixel scale, focal scale, and image shape are now defined in the config.
* Changes to `~bmo.devices.manta.MantaExposure`:
    * Compression now uses fpack.
    * Background model parameters are saved in the header.
    * Modified to use ``photutils>=0.4`` and ``astropy>=2.0.4``
    * When loading an image from a FITS image using ``MantaExposure.from_fits``, the background model is applied to reconstruct the raw image.
    * Cleaned code.
* Explicitly closes the image after saving it to disk in case that causes a memory leak.


.. _changelog-0.2.1:

0.2.1 (2017-12-17)
------------------

Fixed
^^^^^
* Added a ``check_connection`` decorator to check the TCC connection before writing.


.. _changelog-0.2.0:

0.2.0 (2017-10-09)
------------------

Added
^^^^^
* BMO now provides a full logging system which also catches Twisted messages.
* A fake Vimba controller which provides at least some basic functionality like connecting a camera.
* Outputs actorkeys keywords for camera devices, exposure state, and controller.
* Finding charts are now, by default, grabbed from platelist.
* Acquisition camera positions on the plates are grabbed from the DB.
* Partially filled up documentation on how to use BMO.
* Last centroid positions are stored and used if ``centre_up`` fails getting centroid position from the DS9 regions.
* Logging now allows to redirect debug, info, and warning messages to the actor. This prevents you from having to do a ``log.debug`` and a ``actor.writeToUsers`` for the same message. Instead, just do ``log.debug('message', actor=actor)``.

Changed
^^^^^^^
* Exposing the cameras is now asynchronous. Both cameras can be exposed at the same time without blocking.
* Background estimation now only happens for the first image in the series. For any subsequent image, the first background is subtracted. If the exposure time changes, the background is recalculated.
* ``bmo ds9 clear`` is now an alias to ``bmo ds9 reset``.

Fixed
^^^^^
* Thanks to the asynchronous exposing, the problem with TCC status timing out during centring up should now be fixed.
* Better handling of TCC disconnections and reconnections.


.. _changelog-0.1.0:

0.1.0 (2017-09-15)
------------------

This is the first release of BMO so this list includes only the most notable features to date.

Added
^^^^^
* Base actor based on `twistedActor <https://github.com/ApachePointObservatory/twistedActor>`_ and TCC device.
* Basic camera control for Allied Vision Manta devices, with camera auto-discovery.
* Display of camera images using DS9 and XPA.
* Command parser based on `click <http://click.pocoo.org/5/>`_. Help commands are broadcasted as responses to the user.
* Basic set of camera control commands (``expose``, ``exptime``, ``reconnect``).
* Loaded cart auto-detection and finding chart display.
* Centroid detection based on `PyGuide <https://github.com/r-owen/PyGuide>`_.
* Centre-up in translation (RA/Dec) and rotation.
* Image background subtraction using `photutils <https://github.com/astropy/photutils>`_.
* Basic astrometry for images.
* Sphinx documentation. Uses `sphinx-click <https://github.com/click-contrib/sphinx-click>`_ to auto-generate available commands.


.. x.y.z (unreleased)
.. ------------------
..
.. A short description
..
.. Added
.. ^^^^^
.. * TBD
..
.. Changed
.. ^^^^^^^
.. * TBD
..
.. Fixed
.. ^^^^^
.. * TBD

# pyfdtd is a simple 2d fdtd using numpy
# Copyright (C) 2012  Patrik Gebhardt
# Contact: grosser.knuff@googlemail.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from types import FunctionType
from collections import defaultdict
from scipy import constants
import pyopencl as cl
import pyopencl.array as clarray
import numpy


class Material:
    """
    Container for material layer

        **Arguments:**

    size (required)
        Size of all layers

    delta (required)
        Discretization

    """
    def __init__(self, ctx, queue, size, delta):
        # save atributes
        self.size = size
        self.delta = delta
        self.ctx = ctx
        self.queue = queue

        # create meshgrid
        sizeX, sizeY = self.size
        deltaX, deltaY = self.delta
        X, Y = numpy.meshgrid(numpy.arange(0.0, sizeX, deltaX),
                numpy.arange(0.0, sizeY, deltaY))
        self.meshgrid = X.transpose(), Y.transpose()

        # create layer list
        self.layer = []

        # create programs
        self.create_programs()

    def create_programs(self):
        # open file
        f = open('./pyfdtd/material_kernel.cl', 'r')

        # read string
        programmString = f.read()

        # create program
        self.program = cl.Program(self.ctx, programmString)

        # build
        try:
            self.program.build()
        except:
            print("Error:")
            print(self.program.get_build_info(self.ctx.devices[0],
                cl.program_build_info.LOG))
            raise
        finally:
            # close file
            f.close()

    def __setitem__(self, key, value):
        """
        Creates a new material layer using key as mask
        and value as material function

            **Arguments:**

        key (required)
            Function or slice, which describes the layout of the new layer

        value (required)
            Function or value, which describes the field as a function of
            the flux desity
        """
        # get size and delta
        sizeX, sizeY = self.size
        deltaX, deltaY = self.delta

        # create mask
        shape = (sizeX / deltaX, sizeY / deltaY)
        mask = numpy.zeros(shape)

        # check if key is a numpy array
        if isinstance(key, numpy.ndarray):
            mask = numpy.float64(key)

        # check if key is a tuple
        elif isinstance(key, tuple):
            key = Material._scale_slice(key, deltaX, deltaY)

            # evaluate slice
            ones = numpy.ones(shape)
            mask[key] = ones[key]

        else:
            # evaluate mask function
            for x in range(0, int(sizeX / deltaX), 1):
                for y in range(0, int(sizeY / deltaY), 1):
                    mask[x, y] = key(x * deltaX, y * deltaY)

        # check if value is a function
        if not isinstance(value, FunctionType):
            # check if value is a tuple
            if isinstance(value, tuple):
                funcX, funcY = value
            else:
                funcX = lambda flux, dt, t, mem: value * flux
                funcY = funcX
        else:
            funcX = value
            funcY = value

        # add new layer
        mask = clarray.to_device(self.queue, mask)
        dictX = defaultdict(lambda: clarray.to_device(self.queue,
            numpy.zeros(shape)))
        dictY = defaultdict(lambda: clarray.to_device(self.queue,
            numpy.zeros(shape)))
        self.layer.append((funcX, funcY, dictX, dictY, mask))

    def apply(self, queue, flux, deltaT, t):
        """
        Calculates the field from the flux density

            **Argument:**

        flux (required)
            Given flux density

        deltaT (required)
            Time elapsed from last call
        """
        # get flux
        fluxX, fluxY = flux

        fieldX = clarray.to_device(queue, numpy.zeros(fluxX.shape))
        fieldY = clarray.to_device(queue, numpy.zeros(fluxX.shape))

        # apply all layer
        for layer in self.layer:
            funcX, funcY, dictX, dictY, mask = layer

            self.program.apply(self.queue, fieldX.shape, None,
                    fieldX.data, funcX(fluxX, deltaT, t, dictX).data,
                    mask.data)

            self.program.apply(self.queue, fieldY.shape, None,
                    fieldY.data, funcX(fluxY, deltaT, t, dictY).data,
                    mask.data)

        return fieldX, fieldY

    @staticmethod
    def epsilon(er=1.0, sigma=0.0):
        """
        Returns a material function, which calculates the electric
        field dependent from flux density and a complex epsilon

            **Arguments:**

        er
            Relative permittivity

        sigma
            Conductivity
        """
        # create epsilon function
        def res(flux, dt, t, mem):
            field = flux / constants.epsilon_0
            field = (1.0 / (constants.epsilon_0 * er + sigma * dt)) \
                    * (flux - mem['int'])
            mem['int'] += sigma * field * dt
            return field

        # return function
        return res

    @staticmethod
    def mu(mur=1.0, sigma=0.0):
        """
        Returns a material function, which calculates the magnetic field
        dependent from flux density and a real mu

            **Arguments:**

        mur
            Relative permeability
        """
        # create mu function
        def res(flux, dt, t, mem):
            field = flux / constants.mu_0
            field = (1.0 / (constants.mu_0 * mur + sigma * dt)) \
                    * (flux - mem['int'])
            mem['int'] += sigma * field * dt
            return field

        # return function
        return res

    """
    Helper functions for internal use
    """
    @staticmethod
    def _scale_slice(key, deltaX, deltaY):
        """
        Scales the given slices to be used by numpy
        """
        x, y = key

        # scale slices
        if x.start:
            x = slice(x.start / deltaX, x.stop)
        if x.stop:
            x = slice(x.start, x.stop / deltaX)
        if y.start:
            y = slice(y.start / deltaY, y.stop)
        if y.stop:
            y = slice(y.start, y.stop / deltaY)

        return x, y

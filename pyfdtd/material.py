from types import *
import copy
from collections import defaultdict
import numpy
from constants import constants
import field as fi

class material:
    """
    Container for material layer
    
        **Arguments:**
        
    xSize (required)
        Size of all layers in x direction
        
    ySize (required)
        Size of all layers in y direction
        
    deltaX (required)
        Discretization in x direction
        
    deltaY (required)
        discretization in y direction    
    """
    def __init__(self, xSize, ySize, deltaX, deltaY):
        # save atributes
        self.deltaX = deltaX
        self.deltaY = deltaY
        self.xSize = xSize
        self.ySize = ySize

        # create layer list
        self.layer = []

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
        # create mask
        shape = (self.xSize/self.deltaX, self.ySize/self.deltaY)
        mask = numpy.zeros(shape)

        # check if key is a numpy array
        if isinstance(key, numpy.ndarray):
            mask = key

        # check if key is a tuple
        elif isinstance(key, tuple):
            key = material._helper.scale_slice(key, self.deltaX, self.deltaY)

            # evaluate slice
            ones = numpy.ones(shape)
            mask[key] = ones[key]

        else:
            # evaluate mask function
            mask = numpy.zeros(shape)
            for x in range(0, int(self.xSize/self.deltaX), 1):
                for y in range(0, int(self.ySize/self.deltaY), 1):
                    mask[x, y] = key(x*self.deltaX, y*self.deltaY)
    
        # check if value is a function
        if not isinstance(value, FunctionType):
            # check if value is a tuple
            if isinstance(value, tuple):
                funcX, funcY = value
            else:
                v = copy.deepcopy(value)
                value = lambda flux, dt, t, mem: v*flux
        else:
            funcX = value
            funcY = value
             
        # add new layer
        dictX = defaultdict(lambda : numpy.zeros(shape))
        dictY = defaultdict(lambda : numpy.zeros(shape))
        self.layer.append((copy.deepcopy(funcX), copy.deepcopy(funcY), dictX, dictY, mask))

    def apply(self, flux, deltaT, t):
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

        # create field
        fieldX, fieldY = numpy.zeros(fluxX.shape), numpy.zeros(fluxY.shape)

        # apply all layer
        for layer in self.layer:
            funcX, funcY, dictX, dictY, mask = layer

            # calc field
            fieldX = mask*funcX(fluxX, deltaT, t, dictX) + (1.0-mask)*fieldX
            fieldY = mask*funcY(fluxY, deltaT, t, dictY) + (1.0-mask)*fieldY

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
            field = (1.0/(constants.e0*er + sigma*dt))*(flux - mem['int'])
            mem['int'] += sigma*field*dt
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
            field = (1.0/(constants.mu0*mur + sigma*dt))*(flux - mem['int'])
            mem['int'] += sigma*field*dt
            return field

        # return function
        return res

    class _helper:
        """
        Helper functions for internal use
        """
        @staticmethod
        def scale_slice(key, deltaX, deltaY):
            """
            Scales the given slices to be used by numpy
            """
            x, y = key

            # scale slices
            if x.start:
                x = slice(x.start/deltaX, x.stop)
            if x.stop:
                x = slice(x.start, x.stop/deltaX)
            if y.start:
                y = slice(y.start/deltaY, y.stop)
            if y.stop:
                y = slice(y.start, y.stop/deltaY)

            return x, y


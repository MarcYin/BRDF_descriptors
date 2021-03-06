#!/usr/bin/env python

"""Retrieve BRDF shape descriptors from MCD43A1 and MCD43A2 MODIS products.
BRDF descriptors are here assumed to be the weights to the linear kernel
model fit to the data. In this case, we assume that the MODIS set of 
kernels have been used.
"""

# KaFKA A fast Kalman filter implementation for raster based datasets.
# Copyright (c) 2017 J Gomez-Dans. All rights reserved.
#
# This file is part of KaFKA.
#
# KaFKA is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# KaFKA is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with KaFKA.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import os
import glob
import fnmatch


import numpy as np
import gdal

__author__ = "J Gomez-Dans"
__copyright__ = "Copyright 2017 J Gomez-Dans"
__version__ = "1.0 (13.07.2017)"
__license__ = "GPLv3"
__email__ = "j.gomez-dans@ucl.ac.uk"


def locate(root_dir, match_expr):
    files = []
    for root, _, filenames in os.walk(root_dir):
        for filename in fnmatch.filter(filenames, match_expr):
            files.append(filename)
    return files


def find_granules(dire, tile, product, start_time, end_time):
    """Find MCD43 granules based on folder, tile and product type (A1 
    or A2). Returns a dictionary of datetimes of the products and 
    granules, or raises an IOError exception if not files found."""
    
    times = []
    fnames = []
    granules = locate(dire, "MCD43%s.A*.%s.*.hdf" % (product, tile))
    if len(granules) == 0:
        raise IOError("Couldn't find any MCD43%s files in %s" % (product, dire))
    for granule in granules:
        fich = os.path.basename (granule)
        timex = datetime.datetime.strptime(fich.split(".")[1][1:], "%Y%j")
        if timex >= start_time and \
            ( end_time is None or timex <= end_time ):
            times.append (timex)
            fnames.append(os.path.join(dire,granule))
    return dict(zip(times, fnames))


def process_time_input(timestamp):
    """Processes a timestamp given either as (i) a string in 
    "%Y-%m-%d" format, (ii) a string in "%Y%j" format or
    (iii) a datetime.datetime object. Returns a datetime.datetime
    ojbect, and raises ValueError if none of the options fits."""
    if type(timestamp) == datetime.datetime:
        output_time = timestamp
    elif type(timestamp) == str:
        try: 
            output_time = datetime.datetime.strptime(timestamp, 
                                                    "%Y-%m-%d")
        except ValueError:
            try:
                output_time = datetime.datetime.strptime(timestamp, 
                                                    "%Y%j")
            except ValueError:
                raise ValueError("The passed timestamp wasn't either " +
                    'a "%Y-%m-%d" string, a "%Y%j" string')
    else:
        raise ValueError("You can only use a string or a datetime object")
    return output_time

def open_gdal_dataset(fname):
    g = gdal.Open(fname)
    if g is None:
        raise IOError("Can't open %s" % fname)
    data = g.ReadAsArray()
    return data
    

def process_masked_kernels(band_no, a1_granule, a2_granule):
    fname_a1 = 'HDF4_EOS:EOS_GRID:"%s":MOD_Grid_BRDF:' % (a1_granule)
    fname_a2 = 'HDF4_EOS:EOS_GRID:"%s":MOD_Grid_BRDF:' % (a2_granule)
    fdata = fname_a1  + 'BRDF_Albedo_Parameters_Band%d' % (fname_a1, band_no)
    fsnow = fname_a2 + 'Snow_BRDF_Albedo'
    fland = fname_a2 + 'BRDF_Albedo_LandWaterType'
    func = fname_a2 + 'BRDF_Albedo_Uncertainty' % a2_granule
    fqa = fname_a2 + 'BRDF_Albedo_Band_Quality_Band%d' %  band_no
    
    for fname in [fdata, fsnow, fland, func, fqa]:
        data = open_gdal_dataset(fname)
            
        if fname.find("Albedo_Parameters") >= 0:
            # Read kernels, post process
            kernels = process_kernels(data)
        elif fname.find("Snow") >= 0:
            # Read snow mask... post process
            snow = process_snow(data)
        elif fname.find("LandWaterType") >= 0:
            land = data == 1 # Only land
        elif fname.find("BRDF_Albedo_Uncertainty") >= 0:
            unc = process_unc (data)
        elif fname.find("BRDF_Albedo_Band_Quality_Band") >= 0:
            qa = np.where(data <= 1, True, False) # Best & good
            
    # Create mask:
    # 1. Ignore snow
    # 2. Only land
    # 3. Only good and best
    mask = snow * land * qa
    return kernels, mask
    
    
def process_unc(unc):
    """Process uncertainty. Fuck know what it means..."""
    unc = np.where(unc == 32767, np.nan, unc/1000.)
    
def process_snow(snow):
    """Returns True if snow free albedo retrieval"""
    return np.where(snow==0, False, True)

def process_kernels(kernels):
    """Scales the kernels, maybe does other things"""
    kernels = np.where ( kernels == 32767, np.nan, kernels/1000. )
    return kernels



class RetrieveBRDFDescriptors(object):
    """Retrieving BRDF descriptors."""
    def __init__ (self, tile, mcd43a1_dir, start_time, end_time=None, 
            mcd43a2_dir=None):
        """The class needs to locate the data granules. We assume that
        these are available somewhere in the filesystem and that we can
        index them by location (MODIS tile name e.g. "h19v10") and
        time. The user can give a folder for the MCD43A1 and A2 granules,
        and if the second is ignored, it will be assumed that they are
        in the same folder. We also need a starting date (either a
        datetime object, or a string in "%Y-%m-%d" or "%Y%j" format. If
        the end time is not specified, it will be set to the date of the
        latest granule found."""

        self.tile = tile
        self.start_time = process_time_input(start_time)
        if end_time is not None:
            self.end_time = process_time_input(end_time)
        else:
            self.end_time = None
        if os.path.exists(mcd43a1_dir):
            self.mcd43a1_dir = mcd43a1_dir
        else:
            raise IOError("mcd43a1_dir does not exist!")
        self.a1_granules = find_granules(self.mcd43a1_dir, tile, "A1",
                                         self.start_time, self.end_time)
        if mcd43a2_dir is None:
            self.mcd43a2_dir = mcd43a1_dir
        else:
            if os.path.exists(mcd43a2_dir):
                self.mcd43a2_dir = mcd43a2_dir
            else:
                raise IOError("mcd43a2_dir does not exist!")
        self.a2_granules = find_granules(self.mcd43a2_dir, tile, "A2",
                                         self.start_time, self.end_time)
        a1_dates = set(self.a1_granules.keys())
        a2_dates = set(self.a2_granules.keys())
        if a1_dates != a2_dates:
            raise ValueError("A1 and A2 product files do not overlap!")
            

    def get_brdf_descriptors(self, band_no, date):
        if 1 <= band_no <= 7:
            raise ValueError ("Bands can only go from 1 to 7!")
        the_date = process_time_input(date)
        a1_granule = self.a1_granules[the_date]
        a2_granule = self.a2_granules[the_date]
        kernels, mask = process_masked_kernels(a1_granule, a2_granule)
        return kernels, mask

    
if __name__ == "__main__":
    rr = RetrieveBRDFDescriptors("h20v11","/data/selene/ucfajlg/S2_AC/MCD43/Pretoria/","2016-01-01")
        
            
            
        
    
        

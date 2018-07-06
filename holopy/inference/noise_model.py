# Copyright 2011-2016, Vinothan N. Manoharan, Thomas G. Dimiduk,
# Rebecca W. Perry, Jerome Fung, Ryan McGorty, Anna Wang, Solomon Barkley
#
# This file is part of HoloPy.
#
# HoloPy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HoloPy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HoloPy.  If not, see <http://www.gnu.org/licenses/>.

from holopy.fitting.model import BaseModel
from holopy.scattering.errors import MultisphereFailure, InvalidScatterer

import numpy as np
import xarray as xr
from copy import copy
from holopy.scattering.calculations import calc_field, calc_holo
from holopy.fitting import make_subset_data
from holopy.core.metadata import dict_to_array
from holopy.core.utils import ensure_array

class NoiseModel(BaseModel):
    """Model probabilites of observing data

    Compute probabilities that observed data could be explained by a set of
    scatterer and observation parameters.
    """
    def __init__(self, scatterer, noise_sd, medium_index=None, illum_wavelen=None, illum_polarization=None, theory='auto', constraints=[]):
        super().__init__(scatterer, medium_index, illum_wavelen, illum_polarization, theory, constraints)
        self._use_parameter(ensure_array(noise_sd), 'noise_sd')
    def _pack(self, vals):
        return {par.name: val for par, val in zip(self.parameters, vals)}

    def lnprior(self, par_vals):

        for constraint in self.constraints:
            if not constraint.check(self.scatterer.make_from(self._pack(par_vals))):
                return -np.inf

        if isinstance(par_vals, dict):
            return sum([p.lnprob(par_vals[p.name]) for p in self.parameters])
        else:
            return sum([p.lnprob(v) for p, v in zip(self.parameters, par_vals)])

    def lnposterior(self, par_vals, data, pixels=None):
        lnprior = self.lnprior(par_vals)
        # prior is sometimes used to forbid thing like negative radius
        # which will fail if you attempt to compute a hologram of, so
        # don't try to compute likelihood where the prior already
        # forbids you to be
        if lnprior == -np.inf:
            return lnprior
        else:
            if pixels is not None:
                data = make_subset_data(data, pixels=pixels)
            return lnprior + self.lnlike(par_vals, data)

    def _fields(self, pars, schema):
        def get_par(name):
            return pars.pop(name, self.par(name, schema))
        optics, scatterer = self._optics_scatterer(pars, schema)
        try:
            return calc_field(schema, scatterer, theory=self.theory, **optics)
        except (MultisphereFailure, InvalidScatterer):
            return -np.inf

    def _lnlike(self, pars, data):
        """
        Compute the likelihood for pars given data

        Parameters
        -----------
        pars: dict(string, float)
            Dictionary containing values for each parameter
        data: xarray
            The data to compute likelihood against
        """
        noise_sd = dict_to_array(data,self.get_par('noise_sd', pars, data))
        forward = self._forward(pars, data)
        N = data.size
        return (-N/2*np.log(2*np.pi)-N*np.mean(np.log(ensure_array(noise_sd))) -
                ((forward-data)**2/(2*noise_sd**2)).values.sum())

    def lnlike(self, par_vals, data):
        return self._lnlike(self._pack(par_vals), data)

class AlphaModel(NoiseModel):
    def __init__(self, scatterer, noise_sd=None, alpha=1, medium_index=None, illum_wavelen=None, illum_polarization=None, theory='auto', constraints=[]):
        super().__init__(scatterer, noise_sd, medium_index, illum_wavelen, illum_polarization, theory, constraints)
        self._use_parameter(alpha, 'alpha')

    def _forward(self, pars, schema, alpha=None):
        if alpha is not None:
            alpha = alpha
        else:
            alpha = self.get_par('alpha', pars)
        optics, scatterer = self._optics_scatterer(pars, schema)
        try:
            return calc_holo(schema, scatterer, theory=self.theory, scaling=alpha, **optics)
        except (MultisphereFailure, InvalidScatterer):
            return -np.inf

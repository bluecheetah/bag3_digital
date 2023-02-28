# BSD 3-Clause License
#
# Copyright (c) 2018, Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from typing import Mapping, Any, Union, Tuple, Type

import math
import numpy as np
from pathlib import Path

from bag.io import read_yaml
from bag.design.module import Module
from bag.layout.template import TemplateBase
from bag.simulation.cache import SimulationDB
from bag.simulation.design import DesignInstance, DesignerBase
from bag.util.immutable import Param, to_immutable
from bag.util.search import BinaryIterator

from ....measurement.stdcells.inv import InvMeas


def parse_params_file(params: Union[Mapping[str, Any], str, Path]) -> Param:
    """Returns the parsed parameter file if a Pathlike argument is specified, otherwise passthrough is performed.

    Parameters
    ----------
    params : Union[Mapping[str, Any], str, Path]
        The parameters to parse. If a string or a Path, then it is assumed to be the path to a yaml file and
        its contents are returned.

    Returns
    -------
    new_params : Param
        the parsed parameters cast to an immutable dictionary.
    """
    if isinstance(params, (str, Path)):
        params = read_yaml(params)
    return Param(params)


# TODO: design script compatibility with layout generator
class InverterBetaDesigner(DesignerBase):
    """An inverter design script that sizes the PMOS to have equal pull-up and pull-down strengths.
    The NMOS size is specified directly by the user or the generator specs.
    The PMOS-to-NMOS ratio (beta) is returned.

    Parameters
    ----------
    dsn_specs : Mapping[str, Any]
        The design script specifications. The following entries should be specified:

        gen_specs : Union[Mapping[str, Any], Path, str]
            The base/default generator parameters. For each design iteration, new generator parameters
            will be computed by overriding only the transistor sizing.
            If a Path or str is specified, the argument will be treated as a path to a specs YAML file.

        meas_params : Mapping[str, Any]
            The InvMeas parameters.

        beta_min : float
            The minimum PMOS-to-NMOS ratio. Defaults to 0.25.

        beta_max : float
            The maximum PMOS-to-NMOS ratio. Defaults to 4.

        seg_n : int
            Optional. Specify to override the number of NMOS segments in gen_specs.
    """

    def __init__(self, root_dir: Path, sim_db: SimulationDB, dsn_specs: Mapping[str, Any]) -> None:
        self._is_lay: bool = True
        self._dut_class: Union[Type[TemplateBase], Type[Module]] = None
        self._base_gen_specs: Param = None
        super().__init__(root_dir, sim_db, dsn_specs)

    @classmethod
    def get_dut_gen_specs(cls, is_lay: bool, base_gen_specs: Param,
                          gen_params: Mapping[str, Any]) -> Param:
        """Compute the new generator parameters by modifying the base parameters.

        Parameters
        ----------
        is_lay : bool
            True if DUT generator is a layout generator, False if schematic generator.
        base_gen_specs : Param
            The base/default generator specs.
        gen_params : Mapping[str, Any]
            The variable names and values to override in base_gen_specs.

        Returns
        -------
        output : Param
            The new generator specs.
        """
        gen_specs = base_gen_specs.to_yaml()
        if is_lay:
            raise NotImplementedError
        else:
            if 'seg_p' in gen_params:
                gen_specs['seg_p'] = gen_params['seg_p']
            if 'seg_n' in gen_params:
                gen_specs['seg_n'] = gen_params['seg_n']
        return to_immutable(gen_specs)

    @classmethod
    def get_seg_n(cls, is_lay: bool, gen_specs: Param) -> int:
        """Return the number of NMOS segments specified in the generator parameters.

        Parameters
        ----------
        is_lay : bool
            True if DUT generator is a layout generator, False if schematic generator.
        gen_specs : Param
            The generator specs.

        Returns
        -------
        output : int
            The number of NMOS segments
        """
        if is_lay:
            raise NotImplementedError
        else:
            seg_n = gen_specs['seg_n']
            return seg_n if seg_n > 0 else gen_specs['seg']

    def commit(self):
        super().commit()
        base_gen_specs = parse_params_file(self.dsn_specs['gen_specs'])
        self._is_lay, self._dut_class = self.get_dut_class_info(base_gen_specs)
        base_gen_specs = self._dut_class.process_params(base_gen_specs['params'])[0]
        gen_params_override = {}
        if 'seg_n' in self.dsn_specs:
            gen_params_override['seg_n'] = self.dsn_specs['seg_n']
        self._base_gen_specs = self.get_dut_gen_specs(self._is_lay, base_gen_specs,
                                                      gen_params_override)

    @property
    def dut_class(self) -> Union[Type[TemplateBase], Type[Module]]:
        return self._dut_class

    async def async_design(self, beta_min: float = 0.25, beta_max: float = 4, **kwargs: Any) -> Mapping[str, Any]:
        """A coroutine that designs an inverter with equal pull-up and pull-down.
        This is done with a binary search on the PMOS sizing.

        Parameters
        ----------
        beta_min : float
            The minimum PMOS-to-NMOS ratio.
        beta_max : float
            The maximum PMOS-to-NMOS ratio.

        Returns
        -------
        output : Mapping[str, Union[np.ndarray, int]]
            The design results. Contains the following entries:

            seg_p : int
                The number of PMOS segments.
            seg_n : int
                The number of NMOS segments.
            beta : float
                The PMOS-to-NMOS ratio.
            delay_error_avg : float
                The delay mismatch.
        """

        seg_n = self.get_seg_n(self._is_lay, self._base_gen_specs)
        seg_p_iter = BinaryIterator(*self.get_seg_p_size_bounds(seg_n, beta_min, beta_max), 1)

        while seg_p_iter.has_next():
            seg_p = seg_p_iter.get_next()
            dut_gen_params = self.get_dut_gen_specs(self._is_lay, self._base_gen_specs, dict(seg_p=seg_p))
            sim_id = f'meas_seg_p_{seg_p}'
            dut = await self.async_new_dut('inv', self.dut_class, dut_gen_params)
            meas = await self.measure_dut(sim_id, dut)
            prev_meas = seg_p_iter.get_last_save_info()
            if prev_meas is not None:
                prev_err = prev_meas['delay_error_avg']
            else:
                prev_err = None
            err = meas['delay_error_avg']
            if prev_err is None or np.abs(prev_err) > np.abs(err):
                seg_p_iter.save_info(meas)
            if err > 0:
                seg_p_iter.up()
            else:
                seg_p_iter.down()

        seg_p_final = seg_p_iter.get_last_save()
        meas_final = seg_p_iter.get_last_save_info()

        beta = seg_p_final / seg_n

        return dict(
            seg_p=seg_p_final,
            seg_n=seg_n,
            beta=beta,
            delay_error_avg=meas_final['delay_error_avg']
        )

    @staticmethod
    def get_seg_p_size_bounds(seg_n: int, beta_min: float, beta_max: float) -> Tuple[int, int]:
        """Compute the bounds for number of PMOS segments.

        Parameters
        ----------
        seg_n : int
            The number of NMOS segments.
        beta_min : float
            The minimum PMOS-to-NMOS ratio.
        beta_max : float
            The maximum PMOS-to-NMOS ratio.

        Returns
        -------
        output : Tuple[int, int]
            The range of number of PMOS segments, specified as (min size, max size).
        """
        seg_p_min = int(math.ceil(beta_min * seg_n))
        seg_p_max = int(beta_max * seg_n)
        return seg_p_min, seg_p_max

    async def measure_dut(self, sim_id: str, dut: DesignInstance) -> Mapping[str, Any]:
        """A coroutine that measures the delay mismatch between the output rise and fall.

        Parameters
        ----------
        sim_id : str
            The simulation ID.
        dut : DesignInstance
            The DUT to measure.

        Returns
        -------
        output : Mapping[str, Any]
            The measurement results. Contains the following entries, in addition to the ones specified in InvMeas:

            delay_error : np.ndarray
                The error between pull-up delay and pull-down delay, normalized by the pull-down delay.
            delay_error_avg : float
                The average normalized delay error across all corners and simulation sweeps.
        """
        mm_specs = Param(self.dsn_specs['meas_params']).to_yaml()
        mm = self.make_mm(InvMeas, mm_specs)

        meas_results = await self.async_simulate_mm_obj(sim_id, dut, mm)
        data = meas_results.data

        err = (data['delay_rise'] - data['delay_fall']) / data['delay_fall']
        err_avg = np.mean(err)

        return dict(
            delay_error_avg=err_avg,
            delay_error=err,
            **data
        )

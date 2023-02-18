# BSD 3-Clause License

# Copyright (c) 2018, Regents of the University of California
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.

# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.

# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.

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

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence
from pathlib import Path

from bag.simulation.cache import SimulationDB, DesignInstance
from bag.simulation.measure import MeasurementManager
from bag.simulation.data import SimData
from bag.concurrent.util import GatherHelper

from bag3_testbenches.measurement.tran.digital import DigitalTranTB
from bag3_testbenches.measurement.digital.util import setup_digital_tran


class SerNto1Meas(MeasurementManager):
    async def async_measure_performance(self, name: str, sim_dir: Path, sim_db: SimulationDB,
                                        dut: Optional[DesignInstance],
                                        harnesses: Optional[Sequence[DesignInstance]] = None) -> Mapping[str, Any]:
        helper = GatherHelper()
        sim_envs = self.specs['sim_envs']
        for sim_env in sim_envs:
            helper.append(self.async_meas_pvt(name, sim_dir / sim_env, sim_db, dut, harnesses, sim_env))

        meas_results = await helper.gather_err()
        results = {}
        for idx, sim_env in enumerate(sim_envs):
            results[sim_env] = meas_results[idx]
        self.plot_results(results)
        return results

    async def async_meas_pvt(self, name: str, sim_dir: Path, sim_db: SimulationDB, dut: Optional[DesignInstance],
                             harnesses: Optional[Sequence[DesignInstance]], pvt: str) -> SimData:
        ser_ratio: int = self.specs['ser_ratio']
        _suf = f'<{ser_ratio - 1}:0>'
        out_pin: str = self.specs['out_pin']
        clkb_pin: bool = self.specs['clkb_pin']
        save_outputs_specs: Sequence[str] = self.specs['save_outputs']

        # harnesses
        if harnesses:
            raise NotImplementedError
        else:
            clk_i = 'clk'
            clkb_i = 'clkb'
            clk_div_i = 'clk_div'
            harnesses_list = []

        save_outputs = [clk_i, clk_div_i, 'rst', 'rstb_sync', out_pin]
        save_outputs.extend(save_outputs_specs)

        # create load
        load_list = [dict(pin=out_pin, type='cap', value='c_load')]

        # create inputs
        # seq = max_len_seq(7)[0]
        seq = [0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1]
        in_list = ['VDD' if seq[idx] == 1 else 'VSS' for idx in range(ser_ratio - 1, -1, -1)]
        print('---------------')
        print('Input sequence:')
        print(seq[:ser_ratio])
        print('---------------')

        # pulse clk_div
        pulse_list = [dict(pin=clk_div_i, tper=f't_per*{ser_ratio}', tpw=f't_per*{ser_ratio}/2', trf='t_rf')]
        # sinusoidal clk
        load_list.append(dict(pin=clk_i, type='vsin', value=dict(vo='v_VDD/2', va='v_VDD/2', freq='1/t_per')))
        if clkb_pin:
            # sinusoidal clkb
            load_list.append(dict(pin=clkb_i, type='vsin', value=dict(vo='v_VDD/2', va='v_VDD/2', freq='1/t_per',
                                                                      sinephase='-180')))
            save_outputs.append(clkb_i)

        # synchronous rst
        pulse_list.append(dict(pin='rst', tper='t_sim', tpw='t_pw', trf='t_rf'))

        tb_params = dict(
            pin_values={f'din{_suf}': ','.join(in_list)},
            pulse_list=pulse_list,
            load_list=load_list,
            harnesses_list=harnesses_list,
            sim_envs=[pvt],
            save_outputs=save_outputs
        )
        tbm_specs, tb_params = setup_digital_tran(self.specs, dut, **tb_params)
        tbm = self.make_tbm(DigitalTranTB, tbm_specs)
        sim_results = await sim_db.async_simulate_tbm_obj(name, sim_dir, dut, tbm, tb_params, harnesses=harnesses)
        return sim_results.data

    def plot_results(self, results: Mapping[str, SimData]) -> None:
        ser_ratio: int = self.specs['ser_ratio']
        for sim_env, data in results.items():
            time = data['time']
            ...
        # This is still incomplete

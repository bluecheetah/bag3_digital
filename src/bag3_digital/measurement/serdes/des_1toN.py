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
from scipy.signal import max_len_seq

from bag.simulation.cache import SimulationDB, DesignInstance
from bag.simulation.measure import MeasurementManager
from bag.simulation.data import SimData
from bag.concurrent.util import GatherHelper

from bag3_testbenches.measurement.tran.digital import DigitalTranTB
from bag3_testbenches.measurement.digital.util import setup_digital_tran


class Des1toNMeas(MeasurementManager):
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
        des_ratio: int = self.specs['des_ratio']
        tbm_specs: Mapping[str, Any] = self.specs['tbm_specs']

        save_outputs = ['din', 'clk', 'clk_div', f'dout<{des_ratio - 1}:0>', f'd<{des_ratio - 1}:0>', 'clkb',
                        'clk_divb', 'clk_div_buf', 'clk_divb_buf', 'clk_buf', 'clkb_buf', 'VDC0']

        # harnesses
        if harnesses:
            clk_i = 'clk_i'
            clk_div_i = 'clk_div_i'
            din_i = 'din_i'
            # make conns_dict for 3 buffers
            harnesses_list = [
                dict(harness_idx=0, conns=[('VDD', 'VDD'), ('VSS', 'VSS'), ('in', clk_i), ('out', 'clk')]),
                dict(harness_idx=0, conns=[('VDD', 'VDD'), ('VSS', 'VSS'), ('in', clk_div_i), ('out', 'clk_div')]),
                dict(harness_idx=0, conns=[('VDD', 'VDD'), ('VSS', 'VSS'), ('in', din_i), ('out', 'din')]),
            ]
            save_outputs.extend([clk_i, clk_div_i, din_i])
        else:
            clk_i = 'clk'
            clk_div_i = 'clk_div'
            din_i = 'din'
            harnesses_list = []

        # create clk and clk_div
        pulse_list = [dict(pin=clk_i, tper='t_per', tpw='t_per/2', trf='t_rf', td='t_d'),
                      dict(pin=clk_div_i, tper=f't_per*{des_ratio}', tpw=f't_per*{des_ratio}/2', trf='t_rf',
                           td='t_d_div')]

        # create load
        load_list = []
        for idx in range(des_ratio):
            load_list.append(dict(pin=f'dout<{idx}>', type='cap', value='c_load'))

        # create input
        vpwlf_file = create_pwlf(tbm_specs['sim_params'], sim_dir)
        load_list.append(dict(pin=din_i, type='vpwlf', value=vpwlf_file))

        tb_params = dict(
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
        des_ratio: int = self.specs['des_ratio']
        for sim_env, data in results.items():
            time = data['time']
            ...
        # This is still incomplete


def create_pwlf(sim_params: Mapping[str, Any], sim_dir: Path) -> str:
    seq = max_len_seq(7)[0]
    len_seq = len(seq)
    sim_dir.mkdir(parents=True, exist_ok=True)
    vpwlf_file = 'input.txt'
    t_cur = 0
    t_rf: float = sim_params['t_rf']
    t_per: float = sim_params['t_per']
    t_sim: float = sim_params['t_sim']
    idx = 0
    with open(sim_dir / vpwlf_file, 'w') as file1:
        file1.write(f"{t_cur} 0.0 \n")

        while t_cur < t_sim:
            idx %= len_seq
            cur_val = 'v_VDD' if seq[idx] else '0.0'
            file1.write(f"{t_cur + t_rf} {cur_val} \n")
            file1.write(f"{t_cur + t_per} {cur_val} \n")
            t_cur += t_per
            idx += 1
    return vpwlf_file

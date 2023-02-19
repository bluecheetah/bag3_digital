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
import matplotlib.pyplot as plt

from bag.simulation.cache import SimulationDB, DesignInstance
from bag.simulation.measure import MeasurementManager
from bag.simulation.data import SimData
from bag.concurrent.util import GatherHelper

from bag3_testbenches.measurement.tran.digital import DigitalTranTB
from bag3_testbenches.measurement.digital.util import setup_digital_tran


class ResetSyncMeas(MeasurementManager):
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
        # create load
        load_list = [dict(pin='rst_sync', type='cap', value='c_load'),
                     dict(pin='rstb_sync', type='cap', value='c_load')]

        # sinusoidal clk and clkb
        load_list.extend([dict(pin='clk', type='vsin', value=dict(vo='v_VDD/2', va='v_VDD/2', freq='1/t_per')),
                          dict(pin='clkb', type='vsin', value=dict(vo='v_VDD/2', va='v_VDD/2', freq='1/t_per',
                                                                   sinephase='-180'))])

        # asynchronous rst
        pulse_list = [dict(pin='rst_async', tper='3*t_per', tpw='t_per/2', trf='t_rf', td='t_per/4')]

        tb_params = dict(
            pulse_list=pulse_list,
            load_list=load_list,
            sim_envs=[pvt],
            save_outputs=['clk', 'clkb', 'rst_async', 'rst_sync', 'rstb_sync'],
        )
        tbm_specs, tb_params = setup_digital_tran(self.specs, dut, **tb_params)
        tbm = self.make_tbm(DigitalTranTB, tbm_specs)
        sim_results = await sim_db.async_simulate_tbm_obj(name, sim_dir, dut, tbm, tb_params, harnesses=harnesses)
        return sim_results.data

    @classmethod
    def plot_results(cls, results: Mapping[str, SimData]) -> None:
        fig, [ax0, ax1, ax2] = plt.subplots(3, 1)
        ax0.set(xlabel='Time (ns)', ylabel='rst_async (V)')
        ax1.set(xlabel='Time (ns)', ylabel='clk (V)')
        ax2.set(xlabel='Time (ns)', ylabel='rst_sync (V)')
        ax0.grid()
        ax1.grid()
        ax2.grid()
        for sim_env, data in results.items():
            ax0.plot(data['time'] * 1e9, data['rst_async'][0], label=sim_env)
            ax1.plot(data['time'] * 1e9, data['clk'][0], label=sim_env)
            ax2.plot(data['time'] * 1e9, data['rst_sync'][0], label=sim_env)
        ax0.legend()
        ax1.legend()
        ax2.legend()
        plt.tight_layout()
        plt.show()

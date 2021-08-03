from __future__ import annotations

from typing import Any, Mapping, Optional, Union, Sequence
from pathlib import Path
from scipy.signal import max_len_seq
import matplotlib.pyplot as plt

from bag.simulation.cache import SimulationDB, DesignInstance, SimResults, MeasureResult
from bag.simulation.measure import MeasurementManager, MeasInfo
from bag.simulation.data import SimData
from bag.concurrent.util import GatherHelper

from bag3_testbenches.measurement.tran.digital import DigitalTranTB
from bag3_testbenches.measurement.digital.util import setup_digital_tran


class SerNto1Meas(MeasurementManager):
    def get_sim_info(self, sim_db: SimulationDB, dut: DesignInstance, cur_info: MeasInfo,
                     harnesses: Optional[Sequence[DesignInstance]] = None):
        raise NotImplementedError

    def initialize(self, sim_db: SimulationDB, dut: DesignInstance,
                   harnesses: Optional[Sequence[DesignInstance]] = None):
        raise NotImplementedError

    def process_output(self, cur_info: MeasInfo, sim_results: Union[SimResults, MeasureResult]):
        raise NotImplementedError

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

        save_outputs = [f'din{_suf}', 'clk', 'clk_div', 'rst', out_pin, f'd{_suf}', f'p{_suf}', 'clk_buf',
                        'clkb_buf', 'clk_div_buf', 'clk_divb_buf', 'p0_buf']

        # harnesses
        if harnesses:
            raise NotImplementedError
        else:
            clk_i = 'clk'
            clk_div_i = 'clk_div'
            harnesses_list = []

        # create load
        load_list = [dict(pin=out_pin, type='cap', value='c_load')]

        # create inputs
        seq = max_len_seq(7)[0]
        for idx in range(ser_ratio):
            _val = 'v_VDD' if seq[idx] == 1 else 0
            load_list.append(dict(pin=f'din<{idx}>', type='vdc', value=_val))
        print('---------------')
        print('Input sequence:')
        print(seq[:ser_ratio])
        print('---------------')

        # pulse clk_div
        pulse_list = [dict(pin=clk_div_i, tper=f't_per*{ser_ratio}', tpw=f't_per*{ser_ratio}/2', trf='t_rf', td='t_d')]
        # sinusoidal clk
        load_list.append(dict(pin=clk_i, type='vsin', value=dict(vo='v_VDD/2', va='v_VDD/2', freq='1/t_per', td='t_d')))

        # synchronous rst
        pulse_list.append(dict(pin='rst', tper='t_sim', tpw='t_d', trf='t_rf', td=0))

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
        ser_ratio: int = self.specs['ser_ratio']
        for sim_env, data in results.items():
            time = data['time']
            ...
        # This is still incomplete

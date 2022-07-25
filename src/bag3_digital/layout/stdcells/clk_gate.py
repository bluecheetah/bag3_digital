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

from typing import Any, Dict, Optional, Union, Type

from pybag.enum import MinLenMode

from bag.util.math import HalfInt
from bag.util.immutable import Param, ImmutableSortedDict
from bag.layout.template import TemplateDB
from bag.design.database import Module

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from bag3_digital.layout.stdcells.gates import InvCore, InvChainCore, NAND2Core
from bag3_digital.layout.stdcells.memory import FlopCore

from ...schematic.clk_gate import bag3_digital__clk_gate


class ClkGate(MOSBase):

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        super().__init__(temp_db, params, **kwargs)
        self._clk_div_hm_tidx = None
        self._clk_divb_hm_tidx = None

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__clk_gate

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            dff_params='DFF parameters for en synchronization',
            num_dff='Number of cascaded DFFs for synchronization',
            nand_params='Nand parameters for clock gating.',
            gclk_inv_params='Inverter parameter to generate gclk',
            clkb_inv_params='Optional inverter parameters to generate clkb. If None, clkb is an input pin.'
                            ' Defaults to None.',
            en_buf_params='Optional inverter chain parameters to buffer en. If None, removed. Defaults to None.',
            export_nets='True to export intermediate nets. Defaults to False',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Signal track location dictionary.',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
            clkb_inv_params=None,
            en_buf_params=None,
            export_nets=False,
            sig_locs={},
            ridx_p=-1,
            ridx_n=0,
        )

    @property
    def ridx_p(self):
        return self.params['ridx_p']

    @property
    def ridx_n(self):
        return self.params['ridx_n']

    @property
    def clk_div_hm_tidx(self):
        return self._clk_div_hm_tidx

    @property
    def clk_divb_hm_tidx(self):
        return self._clk_divb_hm_tidx

    def get_default_clk_hm_tidx(self):
        return self.get_track_index(self.ridx_n, MOSWireType.G, wire_name='sig', wire_idx=0)

    def get_default_gclkb_hm_tidx(self):
        return self.get_track_index(self.ridx_n, MOSWireType.G, wire_name='sig', wire_idx=1)

    def get_default_clkb_hm_tidx(self):
        return self.get_track_index(self.ridx_p, MOSWireType.G, wire_name='sig', wire_idx=1)

    def get_default_en_sync_hm_tidx(self):
        return self.get_track_index(self.ridx_p, MOSWireType.G, wire_name='sig', wire_idx=1)

    def get_default_en_hm_tidx(self):
        return self.get_track_index(self.ridx_p, MOSWireType.G, wire_name='sig', wire_idx=0)

    @classmethod
    def update_subblock_sig_locs(cls, subblock_params: Param, updated_sig_locs: Dict[str, Union[HalfInt, int, float]]):
        sig_locs = subblock_params.get('sig_locs', ImmutableSortedDict()).to_yaml()
        sig_locs.update(updated_sig_locs)
        return subblock_params.copy(append=dict(sig_locs=sig_locs))

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        dff_params: Param = self.params['dff_params']
        nand_params: Param = self.params['nand_params']
        gclk_inv_params: Param = self.params['gclk_inv_params']
        clkb_inv_params: Optional[Param] = self.params['clkb_inv_params']
        en_buf_params: Optional[Param] = self.params['en_buf_params']
        num_dff: int = self.params['num_dff']
        export_nets: bool = self.params['export_nets']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']

        sig_locs = self.params['sig_locs']

        has_clkb_inv = clkb_inv_params is not None
        has_en_buf = en_buf_params is not None

        clk_hm_tidx = sig_locs.get('clk', self.get_default_clk_hm_tidx())
        clkb_hm_tidx = sig_locs.get('clkb', self.get_default_clkb_hm_tidx())
        gclkb_hm_tidx = sig_locs.get('gclkb', self.get_default_gclkb_hm_tidx())
        en_hm_tidx = sig_locs.get('en', self.get_default_en_hm_tidx())

        shared_params = dict(pinfo=pinfo, ridx_p=ridx_p, ridx_n=ridx_n)

        dff_params = dff_params.copy(append=shared_params)
        nand_params = nand_params.copy(append=shared_params)
        gclk_inv_params = gclk_inv_params.copy(append=shared_params)

        dff_params = self.update_subblock_sig_locs(dff_params, {'pclk': clkb_hm_tidx, 'nclkb': clk_hm_tidx,
                                                                'nin': en_hm_tidx})
        nand_params = self.update_subblock_sig_locs(nand_params, {'nin0': clk_hm_tidx, 'nin1': en_hm_tidx})
        gclk_inv_params = self.update_subblock_sig_locs(gclk_inv_params, {'nin': gclkb_hm_tidx})

        dff_master: FlopCore = self.new_template(FlopCore, params=dff_params)
        nand_master: NAND2Core = self.new_template(NAND2Core, params=nand_params)
        gclk_inv_master: InvCore = self.new_template(InvCore, params=gclk_inv_params)

        if has_clkb_inv:
            clkb_inv_params = clkb_inv_params.copy(append=shared_params)
            clkb_inv_params = self.update_subblock_sig_locs(clkb_inv_params, {'nin': clk_hm_tidx})
            clkb_inv_master: InvCore = self.new_template(InvCore, params=clkb_inv_params)
        else:
            clkb_inv_master = None

        if has_en_buf:
            en_buf_params = en_buf_params.copy(append=shared_params)
            en_buf_params = self.update_subblock_sig_locs(en_buf_params, {'nin': en_hm_tidx})
            en_buf_master: InvChainCore = self.new_template(InvChainCore, params=en_buf_params)
        else:
            en_buf_master = None

        cur_col = 0
        all_insts = []

        if has_en_buf:
            en_buf_inst = self.add_tile(en_buf_master, 0, cur_col)
            cur_col += en_buf_master.num_cols + self.min_sep_col
            all_insts.append(en_buf_inst)
        else:
            en_buf_inst = None

        if has_clkb_inv:
            clkb_inv_inst = self.add_tile(clkb_inv_master, 0, cur_col)
            cur_col += clkb_inv_master.num_cols + self.min_sep_col
            all_insts.append(clkb_inv_inst)
        else:
            clkb_inv_inst = None

        dff_insts = []
        for i in range(num_dff):
            inst = self.add_tile(dff_master, 0, cur_col)
            dff_insts.append(inst)
            cur_col += dff_master.num_cols + self.min_sep_col
        all_insts.extend(dff_insts)

        nand_inst = self.add_tile(nand_master, 0, cur_col)
        all_insts.append(nand_inst)
        cur_col += nand_master.num_cols + self.min_sep_col

        gclk_inv_inst = self.add_tile(gclk_inv_master, 0, cur_col)
        all_insts.append(gclk_inv_inst)
        cur_col += gclk_inv_master.num_cols + self.min_sep_col

        self.set_mos_size()

        if has_en_buf:
            self.connect_to_track_wires(dff_insts[0].get_pin('nin'), en_buf_inst.get_pin('out'))
            self.add_pin('en', self.extend_wires(en_buf_inst.get_pin('nin'), min_len_mode=MinLenMode.LOWER))
            self.reexport(dff_insts[0].get_port('nin'), net_name='en_buf', hide=not export_nets)
        else:
            self.reexport(dff_insts[0].get_port('nin'), net_name='en', hide=False)

        clk_hm_warrs = [dff_insts[0].get_pin('nclkb')]

        if has_clkb_inv:
            self.connect_to_track_wires(dff_insts[0].get_pin('pclk'), clkb_inv_inst.get_pin('out'))
            self.reexport(dff_insts[0].get_port('clk'), net_name='clkb', hide=not export_nets)
            clk_hm_warrs.append(clkb_inv_inst.get_pin('in'))
        else:
            self.reexport(dff_insts[0].get_port('clk'), net_name='clkb')
            self.reexport(dff_insts[0].get_port('nclk'), net_name='nclkb')
            self.reexport(dff_insts[0].get_port('pclk'), net_name='pclkb')

        clk_hm_warrs = self.connect_wires(clk_hm_warrs)
        self.add_pin('clk', clk_hm_warrs)
        self.reexport(dff_insts[0].get_port('clkb'), net_name='clk_vm', label='clk')

        for i in range(num_dff - 1):
            self.connect_wires([dff_insts[i].get_pin('nclkb_s'), dff_insts[i + 1].get_pin('nclkb')])
            self.connect_wires([dff_insts[i].get_pin('pclk_s'), dff_insts[i + 1].get_pin('pclk')])
            self.connect_to_track_wires(dff_insts[i].get_pin('out'), dff_insts[i + 1].get_pin('nin'))

        self.connect_wires([dff_insts[-1].get_pin('nclkb_s'), nand_inst.get_pin('nin<0>')])
        self.connect_wires([dff_insts[-1].get_pin('pout'), nand_inst.get_pin('nin<1>')])
        self.reexport(nand_inst.get_port('in<1>'), net_name='en_sync', hide=not export_nets)

        self.connect_to_track_wires(gclk_inv_inst.get_pin('nin'), nand_inst.get_pin('out'))
        self.reexport(gclk_inv_inst.get_port('in'), net_name='gclkb', hide=not export_nets)

        self.reexport(gclk_inv_inst.get_port('out'), net_name='gclk')

        vdd_hm = self.connect_wires([inst.get_pin('VDD') for inst in all_insts])
        vss_hm = self.connect_wires([inst.get_pin('VSS') for inst in all_insts])

        self.add_pin('VDD', vdd_hm)
        self.add_pin('VSS', vss_hm)

        self.sch_params = dict(
            dff_params=dff_master.sch_params,
            num_dff=num_dff,
            nand_params=nand_master.sch_params,
            gclk_inv_params=gclk_inv_master.sch_params,
            clkb_inv_params=clkb_inv_master and clkb_inv_master.sch_params,
            en_buf_params=en_buf_master and en_buf_master.sch_params,
            export_nets=export_nets,
        )

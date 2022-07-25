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

from typing import Any, Dict, Optional, Type

from bag.util.immutable import Param, ImmutableSortedDict
from bag.design.database import Module
from bag.layout.template import TemplateDB

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from bag3_digital.layout.stdcells.gates import InvCore
from bag3_digital.layout.stdcells.memory import FlopCore

from ...schematic.div2 import bag3_digital__div2


class Div2(MOSBase):

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        super().__init__(temp_db, params, **kwargs)
        self._clk_div_hm_tidx = None
        self._clk_divb_hm_tidx = None

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__div2

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            dff_params='DFF parameters',
            inv_params='Inverter parameters',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Signal track location dictionary.',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
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

    def get_default_clk_div_hm_tidx(self):
        return self.get_track_index(self.ridx_p, MOSWireType.G, 'sig', 0)

    def get_default_clk_divb_hm_tidx(self):
        return self.get_track_index(self.ridx_n, MOSWireType.G, wire_name='sig', wire_idx=2)

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        dff_params: Param = self.params['dff_params']
        inv_params: Param = self.params['inv_params']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']

        sig_locs = self.params['sig_locs']

        if 'clk_div' in sig_locs:
            clk_div_tidx = sig_locs['clk_div']
        else:
            clk_div_tidx = self.get_default_clk_div_hm_tidx()

        if 'clk_divb' in sig_locs:
            clk_divb_tidx = sig_locs['clk_divb']
        else:
            clk_divb_tidx = self.get_default_clk_divb_hm_tidx()

        self._clk_div_hm_tidx = clk_div_tidx
        self._clk_divb_hm_tidx = clk_divb_tidx

        inv_sig_locs = inv_params.get('sig_locs', ImmutableSortedDict())
        inv_sig_locs = inv_sig_locs.copy(append={'in': clk_div_tidx})
        dff_sig_locs = dff_params.get('sig_locs', ImmutableSortedDict())
        dff_sig_locs = dff_sig_locs.copy(append={'pout': clk_div_tidx, 'in': clk_divb_tidx})

        inv_params = inv_params.copy(append=dict(
            pinfo=pinfo,
            vertical_out=True,
            sig_locs=inv_sig_locs,
            ridx_p=ridx_p,
            ridx_n=ridx_n,
        ))
        dff_params = dff_params.copy(append=dict(
            pinfo=pinfo,
            resetable=True,
            sig_locs=dff_sig_locs,
            ridx_p=ridx_p,
            ridx_n=ridx_n,
        ))

        inv_master = self.new_template(InvCore, params=inv_params)
        dff_master = self.new_template(FlopCore, params=dff_params)

        cur_col = 0
        dff_inst = self.add_tile(dff_master, 0, cur_col)
        cur_col += dff_master.num_cols + self.min_sep_col
        inv_inst = self.add_tile(inv_master, 0, cur_col)

        inst_list = [dff_inst, inv_inst]

        self.set_mos_size()

        self.connect_wires([dff_inst.get_pin('pout'), inv_inst.get_pin('in')])
        self.connect_to_track_wires(dff_inst.get_pin('nin'), inv_inst.get_pin('out'))

        self.reexport(dff_inst.get_port('clk'))
        self.reexport(dff_inst.get_port('out'), net_name='clk_div')
        self.reexport(inv_inst.get_port('out'), net_name='clk_divb')
        self.reexport(dff_inst.get_port('nrst'), net_name='rst', hide=False)
        self.reexport(dff_inst.get_port('pout'), net_name='clk_div_hm', label='clk_div', hide=True)

        vdd_hm = self.connect_wires([inst.get_pin('VDD') for inst in inst_list])
        vss_hm = self.connect_wires([inst.get_pin('VSS') for inst in inst_list])

        self.add_pin('VDD', vdd_hm)
        self.add_pin('VSS', vss_hm)

        self.sch_params = dict(
            inv_params=inv_master.sch_params,
            dff_params=dff_master.sch_params,
        )

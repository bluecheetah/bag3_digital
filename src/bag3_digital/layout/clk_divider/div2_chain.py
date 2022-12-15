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

from typing import Any, Mapping, Sequence, Optional, Union, Type, Tuple

from pybag.enum import RoundMode, MinLenMode

from bag.util.math import HalfInt
from bag.util.immutable import Param, ImmutableSortedDict
from bag.layout.routing.base import TrackID, WireArray
from bag.design.database import Module

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .div2 import Div2
from ..stdcells.gates import InvChainCore
from ..stdcells.clk_gate import ClkGate

from ...schematic.div2_chain import bag3_digital__div2_chain


class Div2Chain(MOSBase):
    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__div2_chain

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            num_stages='Number of stages.',
            div_params='Div2 divider parameters. Same divider per stage',
            clk_div_buf_params_list='List of divided clock buffer parameters. If an entry is None, removed.'
                                    'If not a list, assumed to have same parameter per stage. Defaults to None.',
            inv_clk_div_list='List of booleans mapping whether each divider (after the first) should invert its input '
                             'clock. If a list, should have length num_stages - 1. If not a list, assumed to have the '
                             'same boolean per divider. Defaults to False.',
            clk_buf_params='Input clock buffer parameters. If None, removed. Defaults to None.',
            clk_gate_params='Clock gate parameters. If None, removed. Defaults to None.',
            export_nets='True to export intermediate nets. Defaults to False',
            clk_div_layer='Divided clock layer. Defaults to vm_layer',
            output_clk_divb='True to output clk_divb wires (i.e., bring up to clk_div_layer and export as pins). '
                            'Defaults to True',
            clk_wtype='Clock wire type. Defaults to sig',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Signal track location dictionary.',
            export_unit_sup='True to export unit supply pins. Defaults to False.',
            add_taps='True to add substrate columns in this cell; False if taps are added in higher hierarchy. '
                     'Defaults to True',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            clk_div_buf_params_list=None,
            inv_clk_div_list=False,
            clk_buf_params=None,
            clk_gate_params=None,
            export_nets=False,
            clk_div_layer=None,
            output_clk_divb=True,
            clk_wtype='sig',
            sig_locs={},
            ridx_p=-1,
            ridx_n=0,
            export_unit_sup=False,
            add_taps=True,
        )

    @property
    def clk_wtype(self):
        return self.params['clk_wtype']

    def connect_clk_div_warr_to_top(self, clk_div_layer: int, warr_vm: WireArray, nwarr_hm: WireArray,
                                    pwarr_hm: WireArray):
        clk_div_hor_layer = clk_div_layer - int(not self.grid.is_horizontal(clk_div_layer))
        clk_wtype = self.clk_wtype

        vm_layer = self.conn_layer + 2
        xm_layer = vm_layer + 1

        if clk_div_layer == vm_layer:
            return warr_vm

        # compute coord_list_o_override, avoiding the already drawn vm wire
        cur_vm_tid = warr_vm.track_id
        coord_list_o_override_r = []
        cur_vm_tid = self.tr_manager.get_next_track_obj(cur_vm_tid, 'sig', clk_wtype, 2)
        while cur_vm_tid.get_bounds(self.grid)[1] < nwarr_hm.upper:
            coord_list_o_override_r.append(self.grid.track_to_coord(vm_layer, cur_vm_tid.base_index))
            cur_vm_tid = self.tr_manager.get_next_track_obj(cur_vm_tid, clk_wtype, clk_wtype, 2)
        cur_vm_tid = warr_vm.track_id
        coord_list_o_override_l = []
        cur_vm_tid = self.tr_manager.get_next_track_obj(cur_vm_tid, 'sig', clk_wtype, -2)
        while cur_vm_tid.get_bounds(self.grid)[0] > nwarr_hm.lower:
            coord_list_o_override_l.append(self.grid.track_to_coord(vm_layer, cur_vm_tid.base_index))
            cur_vm_tid = self.tr_manager.get_next_track_obj(cur_vm_tid, clk_wtype, clk_wtype, -2)

        nwarr_vm = [warr_vm]
        pwarr_vm = [warr_vm]
        if coord_list_o_override_r:
            nrwarr_vm = self.connect_via_stack(self.tr_manager, nwarr_hm, vm_layer, clk_wtype,
                                               coord_list_o_override=coord_list_o_override_r)
            prwarr_vm = self.connect_via_stack(self.tr_manager, pwarr_hm, vm_layer, clk_wtype,
                                               coord_list_o_override=coord_list_o_override_r)
            nwarr_vm.append(nrwarr_vm)
            pwarr_vm.append(prwarr_vm)
        if coord_list_o_override_l:
            nlwarr_vm = self.connect_via_stack(self.tr_manager, nwarr_hm, vm_layer, clk_wtype,
                                               coord_list_o_override=coord_list_o_override_l)
            plwarr_vm = self.connect_via_stack(self.tr_manager, pwarr_hm, vm_layer, clk_wtype,
                                               coord_list_o_override=coord_list_o_override_l)
            nwarr_vm.append(nlwarr_vm)
            pwarr_vm.append(plwarr_vm)

        xm_w_sig = self.tr_manager.get_width(xm_layer, 'sig')
        xm_tidx_n = self.grid.coord_to_track(xm_layer, nwarr_hm.bound_box.ym, RoundMode.NEAREST)
        xm_tidx_p = self.grid.coord_to_track(xm_layer, pwarr_hm.bound_box.ym, RoundMode.NEAREST)
        nwarr_hor = self.connect_to_tracks(nwarr_vm, TrackID(xm_layer, xm_tidx_n, width=xm_w_sig),
                                           min_len_mode=MinLenMode.MIDDLE)
        pwarr_hor = self.connect_to_tracks(pwarr_vm, TrackID(xm_layer, xm_tidx_p, width=xm_w_sig),
                                           min_len_mode=MinLenMode.MIDDLE)

        if clk_div_hor_layer > xm_layer:
            nwarr_hor = self.connect_via_stack(self.tr_manager, nwarr_hor, clk_div_hor_layer, 'sig')
            pwarr_hor = self.connect_via_stack(self.tr_manager, pwarr_hor, clk_div_hor_layer, 'sig')

        warr_top = self.connect_wires([nwarr_hor, pwarr_hor])
        if not self.grid.is_horizontal(clk_div_hor_layer):
            tidx_top = self.grid.coord_to_track(clk_div_layer, warr_top[0].bound_box.xm, RoundMode.NEAREST)
            warr_top = self.connect_to_tracks(warr_top, TrackID(clk_div_layer, tidx_top,
                                                                width=self.tr_manager.get_width(clk_div_layer, 'sig')))
        return warr_top

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        num_stages: int = self.params['num_stages']
        div_params: Param = self.params['div_params']
        clk_div_buf_params_list: Optional[Union[Param, Sequence[Param]]] = self.params['clk_div_buf_params_list']
        inv_clk_div_list: Union[bool, Sequence[bool]] = self.params['inv_clk_div_list']
        clk_buf_params: Optional[Param] = self.params['clk_buf_params']
        clk_gate_params: Optional[Param] = self.params['clk_gate_params']
        export_nets: bool = self.params['export_nets']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        export_unit_sup: bool = self.params['export_unit_sup']
        sig_locs: Mapping[str, Tuple[HalfInt, int, float]] = self.params['sig_locs']  # TODO: implement
        clk_div_layer: int = self.params['clk_div_layer']
        output_clk_divb: bool = self.params['output_clk_divb']
        add_taps: bool = self.params['add_taps']

        has_clk_buf = clk_buf_params is not None
        has_clk_gate = clk_gate_params is not None

        if clk_div_buf_params_list is None:
            clk_div_buf_params_list = [None] * num_stages
        elif isinstance(clk_div_buf_params_list, ImmutableSortedDict):
            clk_div_buf_params_list = [clk_div_buf_params_list] * num_stages
        elif len(clk_div_buf_params_list) != num_stages:
            raise ValueError(f"clk_div_buf_params_list does not have length num_stages = {num_stages}")
        if isinstance(inv_clk_div_list, bool):
            inv_clk_div_list = [inv_clk_div_list] * (num_stages - 1)
        elif len(inv_clk_div_list) != num_stages - 1:
            raise ValueError(f"inv_clk_div_list does not have length num_stages - 1 = {num_stages - 1}")

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        if not clk_div_layer:
            clk_div_layer = vm_layer
        elif clk_div_layer < vm_layer:
            raise ValueError(f"clk_div_layer = {clk_div_layer} must be at least vm_layer = {vm_layer}")

        shared_params = dict(pinfo=pinfo, ridx_p=ridx_p, ridx_n=ridx_n)
        div_params = div_params.copy(append=shared_params)
        div_master: Div2 = self.new_template(Div2, params=div_params)
        div_clk_in_hm_tidx = self.get_track_index(ridx_p, MOSWireType.G, wire_name='sig', wire_idx=1)
        div_clk_in_hm_tid = TrackID(hm_layer, div_clk_in_hm_tidx, width=self.tr_manager.get_width(hm_layer, 'sig'))
        div_clk_out_hm_tidx = div_master.clk_div_hm_tidx
        div_clk_outb_hm_tidx = div_master.clk_divb_hm_tidx
        div_ncols = div_master.num_cols

        blk_sp = self.min_sep_col
        sub_sep = self.sub_sep_col
        tap_ncols = self.get_tap_ncol()

        cur_col = 0

        # left tap
        vdd_conn_list, vss_conn_list = [], []
        if add_taps:
            self.add_tap(cur_col, vdd_conn_list, vss_conn_list)
            cur_col += tap_ncols + sub_sep

        next_div_in = None
        all_insts = []
        if has_clk_buf:
            clk_buf_sig_locs = clk_buf_params.get('sig_locs', ImmutableSortedDict())
            if has_clk_gate:
                clk_buf_sig_locs = clk_buf_sig_locs.copy(append=dict(
                    nin0=div_clk_in_hm_tidx, nin1=div_clk_outb_hm_tidx))
            else:
                clk_buf_sig_locs = clk_buf_sig_locs.copy(append=dict(
                    nin0=div_clk_out_hm_tidx, nin1=div_clk_outb_hm_tidx))
            clk_buf_master: InvChainCore = self.new_template(InvChainCore,
                                                             params=clk_buf_params.copy(append=dict(
                                                                 **shared_params, dual_output=False,
                                                                 sig_locs=clk_buf_sig_locs)))
            clk_buf_inst = self.add_tile(clk_buf_master, 0, cur_col)
            cur_col += clk_buf_master.num_cols + blk_sp

            clk_hm = clk_buf_inst.get_pin('in')
            self.add_pin('clk', self.extend_wires(clk_hm, min_len_mode=MinLenMode.LOWER))
            should_inv_stg_0 = clk_buf_master.out_invert
            clk_buf_pname = 'outb' if should_inv_stg_0 else 'out'
            next_div_in = clk_buf_inst.get_pin(clk_buf_pname)
            self.reexport(clk_buf_inst.get_port(clk_buf_pname), net_name='clk_bufb' if should_inv_stg_0 else 'clk_buf',
                          hide=not export_nets)

            all_insts.append(clk_buf_inst)
        else:
            clk_buf_master = None

        if has_clk_gate:
            clk_gate_sig_locs = clk_gate_params.get('sig_locs', ImmutableSortedDict())
            clk_gate_master: ClkGate = self.new_template(ClkGate,
                                                         params=clk_gate_params.copy(append=dict(
                                                             **shared_params, sig_locs=clk_gate_sig_locs)))
            clk_gate_inst = self.add_tile(clk_gate_master, 0, cur_col)
            # cur_col += clk_gate_master.num_cols + self.min_sep_col
            cur_col += clk_gate_master.num_cols

            if add_taps:
                cur_col += sub_sep
                self.add_tap(cur_col, vdd_conn_list, vss_conn_list)
                cur_col += tap_ncols + sub_sep
            else:
                cur_col += blk_sp

            for port_name in clk_gate_inst.port_names_iter():
                if port_name in ('VDD', 'VSS', 'gclk', 'clk', 'clk_vm', 'en'):
                    continue
                self.reexport(clk_gate_inst.get_port(port_name), net_name=f'clk_gate_{port_name}')

            if next_div_in is not None:
                self.connect_to_track_wires(clk_gate_inst.get_pin('clk'), next_div_in)
            else:
                self.reexport(clk_gate_inst.get_port('clk'))
            next_div_in = clk_gate_inst.get_pin('gclk')

            self.reexport(clk_gate_inst.get_port('gclk'), hide=not export_nets)
            self.reexport(clk_gate_inst.get_port('en'))

            all_insts.append(clk_gate_inst)
        else:
            clk_gate_master = None

        inv_clk_div_list = list(inv_clk_div_list) + [False]

        div_insts = []
        clk_div_buf_insts = []
        clk_div_buf_masters = []
        for i, (clk_div_buf_params, inv_clk_next) in enumerate(zip(clk_div_buf_params_list, inv_clk_div_list)):
            if i > 0:
                if add_taps:
                    cur_col += sub_sep
                    self.add_tap(cur_col, vdd_conn_list, vss_conn_list)
                    cur_col += tap_ncols + sub_sep
                else:
                    cur_col += blk_sp
            div_inst = self.add_tile(div_master, 0, cur_col)
            cur_col += div_ncols
            div_insts.append(div_inst)

            if next_div_in is None:
                self.reexport(div_inst.get_port('clk'))
                self.reexport(div_inst.get_port('pclk'))
            else:
                self.connect_to_tracks([next_div_in, div_inst.get_pin('clk')], div_clk_in_hm_tid)

            clk_divb_top_warr = None

            if clk_div_buf_params:
                clk_div_buf_sig_locs = clk_div_buf_params.get('sig_locs', ImmutableSortedDict())
                clk_div_buf_sig_locs = clk_div_buf_sig_locs.copy(append=dict(
                    nin0=div_clk_out_hm_tidx, nin1=div_clk_outb_hm_tidx))
                clk_div_buf_params = clk_div_buf_params.copy(append=dict(**shared_params, dual_output=True,
                                                                         sig_locs=clk_div_buf_sig_locs))
                clk_div_buf_master: InvChainCore = self.new_template(InvChainCore, params=clk_div_buf_params)
                cur_col += blk_sp
                clk_div_buf_inst = self.add_tile(clk_div_buf_master, 0, cur_col)
                # cur_col += clk_div_buf_master.num_cols + self.min_sep_col
                cur_col += clk_div_buf_master.num_cols
                clk_div_buf_masters.append(clk_div_buf_master)
                clk_div_buf_insts.append(clk_div_buf_inst)

                self.connect_wires([div_inst.get_pin('clk_div_hm'), clk_div_buf_inst.get_pin('in')])
                self.reexport(div_inst.get_port('clk_div'), net_name=f'div_out_{i}', hide=not export_nets)
                self.reexport(div_inst.get_port('clk_divb'), net_name=f'div_outb_{i}', hide=not export_nets)

                clk_div_vm = clk_div_buf_inst.get_pin('out')
                clk_divb_vm = clk_div_buf_inst.get_pin('outb')

                stg_out_warr = clk_div_vm
                stg_outb_warr = clk_divb_vm

                clk_div_top_warr = self.connect_clk_div_warr_to_top(clk_div_layer, clk_div_vm,
                                                                    clk_div_buf_inst.get_pin('nout'),
                                                                    clk_div_buf_inst.get_pin('pout'))
                if output_clk_divb:
                    clk_divb_top_warr = self.connect_clk_div_warr_to_top(clk_div_layer, clk_divb_vm,
                                                                         clk_div_buf_inst.get_pin('noutb'),
                                                                         clk_div_buf_inst.get_pin('poutb'))
            else:
                clk_div_buf_masters.append(None)
                stg_out_warr = div_inst.get_pin('clk_div')
                stg_outb_warr = div_inst.get_pin('clk_divb')

                clk_div_top_warr = self.connect_via_stack(self.tr_manager, stg_out_warr, clk_div_layer, self.clk_wtype)

                if output_clk_divb:
                    clk_divb_top_warr = self.connect_via_stack(self.tr_manager, stg_outb_warr, clk_div_layer,
                                                               self.clk_wtype)

            # self.add_pin(f'clk_div_{i}', stg_out_warr)
            # self.add_pin(f'clk_divb_{i}', stg_outb_warr)
            self.add_pin(f'clk_div_{i}', clk_div_top_warr)
            self.add_pin(f'clk_div_vm_{i}', stg_out_warr, hide=True)
            if output_clk_divb:
                self.add_pin(f'clk_divb_{i}', clk_divb_top_warr)
            else:
                self.add_pin(f'clk_divb_{i}', stg_outb_warr, hide=not export_nets)

            next_div_in = stg_outb_warr if inv_clk_next else stg_out_warr

        if add_taps:
            cur_col += sub_sep
            self.add_tap(cur_col, vdd_conn_list, vss_conn_list)
            cur_col += tap_ncols

        self.set_mos_size()

        rst_hm = self.connect_wires([inst.get_pin('rst') for inst in div_insts])[0]
        self.add_pin('rst', rst_hm)

        all_insts += div_insts + clk_div_buf_insts
        vdd_hm = self.connect_wires([inst.get_pin('VDD') for inst in all_insts],
                                    lower=self.bound_box.xl, upper=self.bound_box.xh)[0]
        vss_hm = self.connect_wires([inst.get_pin('VSS') for inst in all_insts],
                                    lower=self.bound_box.xl, upper=self.bound_box.xh)[0]
        if add_taps:
            self.connect_to_track_wires(vdd_conn_list, vdd_hm)
            self.connect_to_track_wires(vss_conn_list, vss_hm)

        if export_unit_sup:
            for inst in all_insts:
                if inst is None:
                    continue
                self.reexport(inst.get_port('VDD'))
                self.reexport(inst.get_port('VSS'))

        self.add_pin('VDD', vdd_hm)
        self.add_pin('VSS', vss_hm)

        self.sch_params = dict(
            num_stages=num_stages,
            div_params_list=div_master.sch_params,
            clk_div_buf_params_list=[None if master is None else master.sch_params for master in clk_div_buf_masters],
            inv_clk_div_list=self.params['inv_clk_div_list'],
            clk_buf_params=clk_buf_master and clk_buf_master.sch_params,
            clk_gate_params=clk_gate_master and clk_gate_master.sch_params,
            output_clk_divb=output_clk_divb,
            export_nets=export_nets,
        )

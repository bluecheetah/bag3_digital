# SPDX-License-Identifier: Apache-2.0
# Copyright 2019 Blue Cheetah Analog Design Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""This module contains layout generators for a classic StrongArm latch."""

from typing import Any, Dict, Optional, Union, Tuple, Mapping, Type

from itertools import chain

from pybag.enum import MinLenMode, RoundMode

from bag.util.math import HalfInt
from bag.util.immutable import Param
from bag.design.database import ModuleDB
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from ...schematic.inv import bag3_digital__inv


class InvCore(MOSBase):
    """A single inverter.
    """

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg='segments of transistors',
            seg_p='segments of pmos',
            seg_n='segments of nmos',
            stack_p='number of transistors in a stack.',
            stack_n='number of transistors in a stack.',
            w_p='pmos width, can be list or integer if all widths are the same.',
            w_n='pmos width, can be list or integer if all widths are the same.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            is_guarded='True if it there should be guard ring around the cell',
            sig_locs='Optional dictionary of user defined signal locations',
            vertical_out='True to draw output on vertical metal layer.',
            vertical_sup='True to have supply unconnected on conn_layer.',
            vertical_in='False to not draw the vertical input wire when is_guarded = True.',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
            seg=-1,
            seg_p=-1,
            seg_n=-1,
            stack_p=1,
            stack_n=1,
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            is_guarded=False,
            sig_locs={},
            vertical_out=True,
            vertical_sup=False,
            vertical_in=True,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        grid = self.grid

        seg: int = self.params['seg']
        seg_p: int = self.params['seg_p']
        seg_n: int = self.params['seg_n']
        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        stack_p: int = self.params['stack_p']
        stack_n: int = self.params['stack_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        is_guarded: bool = self.params['is_guarded']
        sig_locs: Mapping[str, Union[float, HalfInt]] = self.params['sig_locs']
        vertical_out: bool = self.params['vertical_out']
        vertical_sup: bool = self.params['vertical_sup']
        vertical_in: bool = self.params['vertical_in']

        if seg_p <= 0:
            seg_p = seg
        if seg_n <= 0:
            seg_n = seg
        if seg_p <= 0 or seg_n <= 0:
            raise ValueError('Invalid segments.')

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        if self.top_layer < vm_layer:
            raise ValueError(f'MOSBasePlaceInfo top layer must be at least {vm_layer}')

        # set is_guarded = True if both rows has same orientation
        rpinfo_n = self.get_row_info(ridx_n)
        rpinfo_p = self.get_row_info(ridx_p)
        is_guarded = is_guarded or rpinfo_n.flip == rpinfo_p.flip

        # Placement
        nports = self.add_mos(ridx_n, 0, seg_n, w=w_n, stack=stack_n)
        pports = self.add_mos(ridx_p, 0, seg_p, w=w_p, stack=stack_p)

        self.set_mos_size()

        # get wire_indices from sig_locs
        tr_manager = self.tr_manager
        tr_w_h = tr_manager.get_width(hm_layer, 'sig')
        tr_w_v = tr_manager.get_width(vm_layer, 'sig')
        nout_tidx = sig_locs.get('nout', self.get_track_index(ridx_n, MOSWireType.DS_GATE,
                                                              wire_name='sig', wire_idx=0))
        pout_tidx = sig_locs.get('pout', self.get_track_index(ridx_p, MOSWireType.DS_GATE,
                                                              wire_name='sig', wire_idx=-1))
        nout_tid = TrackID(hm_layer, nout_tidx, tr_w_h)
        pout_tid = TrackID(hm_layer, pout_tidx, tr_w_h)

        pout = self.connect_to_tracks(pports.d, pout_tid, min_len_mode=MinLenMode.NONE)
        nout = self.connect_to_tracks(nports.d, nout_tid, min_len_mode=MinLenMode.NONE)

        if vertical_out:
            vm_tidx = sig_locs.get('out', grid.coord_to_track(vm_layer, pout.middle,
                                                              mode=RoundMode.NEAREST))
            vm_tid = TrackID(vm_layer, vm_tidx, width=tr_w_v)
            self.add_pin('out', self.connect_to_tracks([pout, nout], vm_tid))
        else:
            self.add_pin('out', [pout, nout], connect=True)
            vm_tidx = None

        if is_guarded:
            nin_tidx = sig_locs.get('nin', self.get_track_index(ridx_n, MOSWireType.G,
                                                                wire_name='sig', wire_idx=0))
            pin_tidx = sig_locs.get('pin', self.get_track_index(ridx_p, MOSWireType.G,
                                                                wire_name='sig', wire_idx=-1))

            nin = self.connect_to_tracks(nports.g, TrackID(hm_layer, nin_tidx, width=tr_w_h))
            pin = self.connect_to_tracks(pports.g, TrackID(hm_layer, pin_tidx, width=tr_w_h))
            self.add_pin('pin', pin, hide=True)
            self.add_pin('nin', nin, hide=True)
            if vertical_in:
                in_tidx = self.grid.find_next_track(vm_layer, nin.lower,
                                                    tr_width=tr_w_v, mode=RoundMode.GREATER_EQ)
                if vm_tidx is not None:
                    in_tidx = min(in_tidx,
                                  self.tr_manager.get_next_track(vm_layer, vm_tidx, 'sig', 'sig',
                                                                 up=False))

                in_tidx = sig_locs.get('in', in_tidx)
                self.add_pin('in', self.connect_to_tracks([pin, nin],
                                                          TrackID(vm_layer, in_tidx, width=tr_w_v)))
            else:
                self.add_pin('in', [pin, nin], connect=True)
        else:
            in_tidx = sig_locs.get('in', None)
            if in_tidx is None:
                in_tidx = sig_locs.get('nin', None)
                if in_tidx is None:
                    default_tidx = self.get_track_index(ridx_n, MOSWireType.G,
                                                        wire_name='sig', wire_idx=0)
                    in_tidx = sig_locs.get('pin', default_tidx)

            in_warr = self.connect_to_tracks([nports.g, pports.g],
                                             TrackID(hm_layer, in_tidx, width=tr_w_h))
            self.add_pin('in', in_warr)
            self.add_pin('pin', in_warr, hide=True)
            self.add_pin('nin', in_warr, hide=True)

        self.add_pin(f'pout', pout, hide=True)
        self.add_pin(f'nout', nout, hide=True)

        xr = self.bound_box.xh
        if vertical_sup:
            self.add_pin('VDD', pports.s, connect=True)
            self.add_pin('VSS', nports.s, connect=True)
        else:
            ns_tid = self.get_track_id(ridx_n, False, wire_name='sup')
            ps_tid = self.get_track_id(ridx_p, True, wire_name='sup')
            vss = self.connect_to_tracks(nports.s, ns_tid, track_lower=0, track_upper=xr)
            vdd = self.connect_to_tracks(pports.s, ps_tid, track_lower=0, track_upper=xr)
            self.add_pin('VDD', vdd)
            self.add_pin('VSS', vss)

        default_wp = self.place_info.get_row_place_info(ridx_p).row_info.width
        default_wn = self.place_info.get_row_place_info(ridx_n).row_info.width
        thp = self.place_info.get_row_place_info(ridx_p).row_info.threshold
        thn = self.place_info.get_row_place_info(ridx_n).row_info.threshold
        lch = self.place_info.lch
        self.sch_params = dict(
            seg_p=seg_p,
            seg_n=seg_n,
            lch=lch,
            w_p=default_wp if w_p == 0 else w_p,
            w_n=default_wn if w_n == 0 else w_n,
            th_n=thn,
            th_p=thp,
            stack_p=stack_p,
            stack_n=stack_n,
        )


class InvTristateCore(MOSBase):
    """A gated inverter with two enable signals.
    """

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        # noinspection PyTypeChecker
        return ModuleDB.get_schematic_class('bag3_digital', 'inv_tristate')

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg='Number of segments.',
            seg_p='Number of segments of pmos.',
            seg_n='Number of segments of nmos.',
            stack_p='number of transistors in a stack.',
            stack_n='number of transistors in a stack.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Signal track location dictionary.',
            vertical_out='True to draw output on vertical metal layer.',
            vertical_sup='True to have supply unconnected on conn_layer.',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            seg=-1,
            seg_p=-1,
            seg_n=-1,
            stack_p=1,
            stack_n=1,
            sig_locs=None,
            vertical_out=True,
            vertical_sup=False,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg: int = self.params['seg']
        seg_p: int = self.params['seg_p']
        seg_n: int = self.params['seg_n']

        if seg_p <= 0:
            seg_p = seg
        if seg_n <= 0:
            seg_n = seg
        if seg_p <= 0 or seg_n <= 0:
            raise ValueError('Invalid segments.')

        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        stack_p: int = self.params['stack_p']
        stack_n: int = self.params['stack_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        sig_locs: Optional[Dict[str, float]] = self.params['sig_locs']
        vertical_out: bool = self.params['vertical_out']
        vertical_sup: bool = self.params['vertical_sup']

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        if vertical_out and self.top_layer < vm_layer:
            raise ValueError(f'MOSBasePlaceInfo top layer must be at least {vm_layer}')

        if stack_p != stack_n:
            raise ValueError(f'The layout generator does not support stack_n = {stack_n} != '
                             f'stack_p = {stack_p}')

        # place instances and set size
        self.set_mos_size(2 * max(seg_p * stack_p, seg_n * stack_n))
        nports = self.add_nand2(ridx_n, 0, seg_n, w=w_n, stack=stack_n)
        pports = self.add_nand2(ridx_p, 0, seg_p, w=w_p, stack=stack_p)

        # get track information
        tr_manager = pinfo.tr_manager
        tr_w_h = tr_manager.get_width(hm_layer, 'sig')
        if sig_locs is None:
            sig_locs = {}
        en_tidx = sig_locs.get('nen', self.get_track_index(ridx_n, MOSWireType.G,
                                                           wire_name='sig', wire_idx=0))
        in_key = 'nin' if 'nin' in sig_locs else 'pin'
        in_tidx = sig_locs.get(in_key, self.get_track_index(ridx_n, MOSWireType.G,
                                                            wire_name='sig', wire_idx=1))
        enb_tidx = sig_locs.get('pen', self.get_track_index(ridx_p, MOSWireType.G,
                                                            wire_name='sig', wire_idx=-1))
        pout_tidx = sig_locs.get('pout', self.get_track_index(ridx_p, MOSWireType.DS_GATE,
                                                              wire_name='sig', wire_idx=0))
        nout_tidx = sig_locs.get('nout', self.get_track_index(ridx_n, MOSWireType.DS_GATE,
                                                              wire_name='sig', wire_idx=-1))

        # connect wires
        tid = TrackID(hm_layer, in_tidx, width=tr_w_h)
        in_warr_list = []

        hm_in = self.connect_to_tracks(list(chain(nports.g0, pports.g0)), tid,
                                       ret_wire_list=in_warr_list)
        self.add_pin('nin', hm_in, hide=True)
        self.add_pin('pin', hm_in, hide=True)
        self.add_pin('in', in_warr_list)
        tid = TrackID(hm_layer, en_tidx, width=tr_w_h)
        self.add_pin('en', self.connect_to_tracks(nports.g1, tid))
        tid = TrackID(hm_layer, enb_tidx, width=tr_w_h)
        self.add_pin('enb', self.connect_to_tracks(pports.g1, tid))
        tid = TrackID(hm_layer, nout_tidx, width=tr_w_h)
        nout = self.connect_to_tracks(nports.d, tid)
        tid = TrackID(hm_layer, pout_tidx, width=tr_w_h)
        pout = self.connect_to_tracks(pports.d, tid)

        # connect output
        if vertical_out:
            tr_w_v = tr_manager.get_width(vm_layer, 'sig')
            out_tidx = sig_locs.get('out', self.grid.coord_to_track(vm_layer, pout.middle,
                                                                    mode=RoundMode.NEAREST))
            tid = TrackID(vm_layer, out_tidx, width=tr_w_v)
            self.add_pin('out', self.connect_to_tracks([pout, nout], tid))

        # connect supplies
        xr = self.bound_box.xh
        if vertical_sup:
            self.add_pin('VDD', pports.s, connect=True)
            self.add_pin('VSS', nports.s, connect=True)
        else:
            ns_tid = self.get_track_id(ridx_n, MOSWireType.DS_GATE, wire_name='sup')
            ps_tid = self.get_track_id(ridx_p, MOSWireType.DS_GATE, wire_name='sup')
            vdd = self.connect_to_tracks(pports.s, ps_tid, track_lower=0, track_upper=xr)
            vss = self.connect_to_tracks(nports.s, ns_tid, track_lower=0, track_upper=xr)
            self.add_pin('VDD', vdd)
            self.add_pin('VSS', vss)

        self.add_pin('pout', pout, label='out:', hide=vertical_out)
        self.add_pin('nout', nout, label='out:', hide=vertical_out)

        # set properties
        self.sch_params = dict(
            seg_p=seg_p,
            seg_n=seg_n,
            lch=self.place_info.lch,
            w_n=self.place_info.get_row_place_info(ridx_n).row_info.width if w_n == 0 else w_n,
            w_p=self.place_info.get_row_place_info(ridx_p).row_info.width if w_p == 0 else w_p,
            th_n=self.place_info.get_row_place_info(ridx_n).row_info.threshold,
            th_p=self.place_info.get_row_place_info(ridx_p).row_info.threshold,
            stack_p=stack_p,
            stack_n=stack_n,
        )


class NAND2Core(MOSBase):
    """
    A 2-input NAND gate.

    'out' and 'in' pin direction is determined by vertical_out and vertical_in flags, respectively
    but regardless, in0_vm, in1_vm, out_vm, and out_hm are always available, and also if
    connect_inputs is True in0_hm, in1_hm will also be available.

    Assumes:

        1. PMOS row above NMOS row.
        2. PMOS gate connections on bottom, NMOS gate connections on top.
    """

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        # noinspection PyTypeChecker
        return ModuleDB.get_schematic_class('bag3_digital', 'nand')

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg='Number of segments.',
            seg_p='Number of segments of pmos.',
            seg_n='Number of segments of nmos.',
            stack_p='number of transistors in a stack.',
            stack_n='number of transistors in a stack.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Optional dictionary of user defined signal locations',
            is_guarded='True if it there should be guard ring around the cell',
            min_len_mode='A Dictionary specfiying min_len_mode for connections',
            vertical_out='True to have output pin on vertical layer',
            vertical_in='True to have input pins on vertical layer.  Only used if is_guarded=True',
            vertical_sup='True to have supply unconnected on conn_layer.',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            seg=-1,
            seg_p=-1,
            seg_n=-1,
            stack_p=1,
            stack_n=1,
            sig_locs={},
            is_guarded=False,
            min_len_mode=dict(
                in0=MinLenMode.NONE,
                in1=MinLenMode.NONE,
                out=MinLenMode.MIDDLE,
            ),
            vertical_out=True,
            vertical_in=True,
            vertical_sup=False,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg: int = self.params['seg']
        seg_p: int = self.params['seg_p']
        seg_n: int = self.params['seg_n']

        if seg_p <= 0:
            seg_p = seg
        if seg_n <= 0:
            seg_n = seg
        if seg_p <= 0 or seg_n <= 0:
            raise ValueError('Invalid segments.')

        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        stack_p: int = self.params['stack_p']
        stack_n: int = self.params['stack_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        sig_locs: Mapping[str, Union[float, HalfInt]] = self.params['sig_locs']
        is_guarded: bool = self.params['is_guarded']
        mlm: Dict[str, MinLenMode] = self.params['min_len_mode']
        vertical_out: bool = self.params['vertical_out']
        vertical_in: bool = self.params['vertical_in']
        vertical_sup: bool = self.params['vertical_sup']

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        if self.top_layer < vm_layer:
            raise ValueError(f'MOSBasePlaceInfo top layer must be at least {vm_layer}')

        tot_col = 2 * max(seg_p * stack_p, seg_n * stack_n)
        self.set_mos_size(tot_col)

        if is_guarded is False and stack_n != stack_p:
            raise ValueError(f'If is_guarded is False, then the layout generator requires that '
                             f'stack_n = {stack_n} == stack_p = {stack_p}.')

        # if guard ring is true ridx_p is automatically mapped to the new row indices
        pports = self.add_nand2(ridx_p, 0, seg_p, w=w_p, stack=stack_p, other=True)
        nports = self.add_nand2(ridx_n, 0, seg_n, w=w_n, stack=stack_n)

        xr = self.bound_box.xh
        if vertical_sup:
            self.add_pin('VDD', pports.s, connect=True)
            self.add_pin('VSS', nports.s, connect=True)
        else:
            ns_tid = self.get_track_id(ridx_n, MOSWireType.DS_GATE, wire_name='sup')
            ps_tid = self.get_track_id(ridx_p, MOSWireType.DS_GATE, wire_name='sup')
            vdd = self.connect_to_tracks(pports.s, ps_tid, track_lower=0, track_upper=xr)
            vss = self.connect_to_tracks(nports.s, ns_tid, track_lower=0, track_upper=xr)
            self.add_pin('VDD', vdd)
            self.add_pin('VSS', vss)

        tr_manager = self.tr_manager
        tr_w_h = tr_manager.get_width(hm_layer, 'sig')
        tr_w_v = tr_manager.get_width(vm_layer, 'sig')
        mlm_in0 = mlm.get('in0', None)
        mlm_in1 = mlm.get('in1', None)
        nin_tid = get_adj_tid_list(self, ridx_n, sig_locs, MOSWireType.G, 'nin', True, tr_w_h)
        pin_tid = get_adj_tid_list(self, ridx_p, sig_locs, MOSWireType.G, 'pin', False, tr_w_h)

        if is_guarded:
            n_in0 = self.connect_to_tracks(nports.g0, nin_tid[0], min_len_mode=mlm_in0)
            n_in1 = self.connect_to_tracks(nports.g1, nin_tid[1], min_len_mode=mlm_in1)
            p_in0 = self.connect_to_tracks(pports.g0, pin_tid[0], min_len_mode=mlm_in0)
            p_in1 = self.connect_to_tracks(pports.g1, pin_tid[1], min_len_mode=mlm_in1)
            in0_tidx = sig_locs.get('in0', self.grid.coord_to_track(vm_layer, self.bound_box.xl,
                                                                    RoundMode.GREATER_EQ))
            in1_tidx = sig_locs.get('in1', self.grid.coord_to_track(vm_layer, self.bound_box.xh,
                                                                    RoundMode.LESS_EQ))
            if vertical_in:
                in0_vm = self.connect_to_tracks([n_in0, p_in0],
                                                TrackID(vm_layer, in0_tidx, width=tr_w_v))
                in1_vm = self.connect_to_tracks([n_in1, p_in1],
                                                TrackID(vm_layer, in1_tidx, width=tr_w_v))
                self.add_pin('in<0>', in0_vm)
                self.add_pin('in<1>', in1_vm)
                self.add_pin('nin<0>', n_in0, hide=True)
                self.add_pin('nin<1>', n_in1, hide=True)
                self.add_pin('pin<0>', p_in0, hide=True)
                self.add_pin('pin<1>', p_in1, hide=True)
            else:
                self.add_pin('nin<0>', n_in0, label='in<0>:')
                self.add_pin('nin<1>', n_in1, label='in<1>:')
                self.add_pin('pin<0>', p_in0, label='in<0>:')
                self.add_pin('pin<1>', p_in1, label='in<1>:')
        else:
            key_name = 'nin' if any(k in sig_locs for k in ['nin', 'nin0']) else 'pin'
            in_tid = get_adj_tid_list(self, ridx_n, sig_locs, MOSWireType.G, key_name, True, tr_w_h)
            in0_vm, in1_vm = [], []
            in0 = self.connect_to_tracks(list(chain(nports.g0, pports.g0)), in_tid[0],
                                         min_len_mode=mlm_in0, ret_wire_list=in0_vm)
            in1 = self.connect_to_tracks(list(chain(nports.g1, pports.g1)), in_tid[1],
                                         min_len_mode=mlm_in0, ret_wire_list=in1_vm)

            self.add_pin('nin<0>', in0, hide=True)
            self.add_pin('pin<0>', in0, hide=True)
            self.add_pin('nin<1>', in1, hide=True)
            self.add_pin('pin<1>', in1, hide=True)
            self.add_pin('in<0>', in0_vm)
            self.add_pin('in<1>', in1_vm)

        nd_tidx = sig_locs.get('nout',
                               self.get_track_index(ridx_n, MOSWireType.DS_GATE,
                                                    wire_name='sig', wire_idx=-1))
        nd_tid = TrackID(hm_layer, nd_tidx, width=tr_w_h)
        mlm_out = mlm.get('out', MinLenMode.MIDDLE)
        if self.can_short_adj_tracks and not is_guarded:
            # we can short adjacent source/drain tracks together, so we can avoid going to vm_layer
            out = self.connect_to_tracks([pports.d, nports.d], nd_tid, min_len_mode=mlm_out)
            self.add_pin('nout', out, hide=True)
            self.add_pin('out', pports.d)
        else:
            # need to use vm_layer to short adjacent tracks.
            pd_tidx = sig_locs.get('pout',
                                   self.get_track_index(ridx_p, MOSWireType.DS_GATE,
                                                        wire_name='sig'))
            pd_tid = TrackID(hm_layer, pd_tidx, width=tr_w_h)
            pout = self.connect_to_tracks(pports.d, pd_tid, min_len_mode=mlm_out)
            nout = self.connect_to_tracks(nports.d, nd_tid, min_len_mode=mlm_out)
            vm_tidx = sig_locs.get('out', self.grid.coord_to_track(vm_layer, pout.middle,
                                                                   mode=RoundMode.GREATER_EQ))
            if vertical_out:
                out = self.connect_to_tracks([pout, nout], TrackID(vm_layer, vm_tidx))
                self.add_pin('pout', pout, hide=True)
                self.add_pin('nout', nout, hide=True)
                self.add_pin('out', out)
            else:
                self.add_pin('pout', pout, label='out:')
                self.add_pin('nout', nout, label='out:')

        self.sch_params = dict(
            seg_p=seg_p,
            seg_n=seg_n,
            lch=self.place_info.lch,
            w_p=self.place_info.get_row_place_info(ridx_p).row_info.width if w_p == 0 else w_p,
            w_n=self.place_info.get_row_place_info(ridx_n).row_info.width if w_n == 0 else w_n,
            th_n=self.place_info.get_row_place_info(ridx_n).row_info.threshold,
            th_p=self.place_info.get_row_place_info(ridx_p).row_info.threshold,
            stack_p=stack_p,
            stack_n=stack_n,
        )


class NOR2Core(MOSBase):
    """
    A 2-input NOR gate.

    'out' and 'in' pin direction is determined by vertical_out and vertical_in flags, respectively
    but regardless, in0_vm, in1_vm, out_vm, and out_hm are always available, and also if
    connect_inputs is True in0_hm, in1_hm will also be available.

    Assumes:

        1. PMOS row above NMOS row.
        2. PMOS gate connections on bottom, NMOS gate connections on top.
    """

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        # noinspection PyTypeChecker
        return ModuleDB.get_schematic_class('bag3_digital', 'nor')

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg='Number of segments.',
            seg_p='Number of segments of pmos.',
            seg_n='Number of segments of nmos.',
            stack_p='number of transistors in a stack.',
            stack_n='number of transistors in a stack.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Optional dictionary of user defined signal locations',
            is_guarded='True if it there should be guard ring around the cell',
            min_len_mode='A Dictionary specfiying min_len_mode for connections',
            vertical_out='True to have output pin on vertical layer',
            vertical_in='True to have input pins on vertical layer.  Only used if is_guarded=True',
            vertical_sup='True to have supply unconnected on conn_layer.',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            seg=-1,
            seg_p=-1,
            seg_n=-1,
            stack_p=1,
            stack_n=1,
            sig_locs={},
            is_guarded=False,
            min_len_mode=dict(
                in0=MinLenMode.NONE,
                in1=MinLenMode.NONE,
                out=MinLenMode.MIDDLE,
            ),
            vertical_out=True,
            vertical_in=True,
            vertical_sup=False,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg: int = self.params['seg']
        seg_p: int = self.params['seg_p']
        seg_n: int = self.params['seg_n']

        if seg_p <= 0:
            seg_p = seg
        if seg_n <= 0:
            seg_n = seg
        if seg_p <= 0 or seg_n <= 0:
            raise ValueError('Invalid segments.')

        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        stack_p: int = self.params['stack_p']
        stack_n: int = self.params['stack_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        sig_locs: Dict[str, float] = self.params['sig_locs']
        is_guarded: bool = self.params['is_guarded']
        mlm: Dict[str, MinLenMode] = self.params['min_len_mode']
        vertical_out: bool = self.params['vertical_out']
        vertical_in: bool = self.params['vertical_in']
        vertical_sup: bool = self.params['vertical_sup']

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        if self.top_layer < vm_layer:
            raise ValueError(f'MOSBasePlaceInfo top layer must be at least {vm_layer}')

        tot_col = 2 * max(seg_p * stack_p, seg_n * stack_n)
        self.set_mos_size(tot_col)

        if is_guarded is False and stack_n != stack_p:
            raise ValueError(f'If is_guarded is False, then the layout generator requires that '
                             f'stack_n = {stack_n} == stack_p = {stack_p}.')

        pports = self.add_nand2(ridx_p, 0, seg_p, w=w_p, stack=stack_p)
        nports = self.add_nand2(ridx_n, 0, seg_n, w=w_n, stack=stack_n, other=True)

        xr = self.bound_box.xh
        if vertical_sup:
            self.add_pin('VDD', pports.s, connect=True)
            self.add_pin('VSS', nports.s, connect=True)
        else:
            ns_tid = self.get_track_id(ridx_n, MOSWireType.DS_GATE, wire_name='sup')
            ps_tid = self.get_track_id(ridx_p, MOSWireType.DS_GATE, wire_name='sup')
            vdd = self.connect_to_tracks(pports.s, ps_tid, track_lower=0, track_upper=xr)
            vss = self.connect_to_tracks(nports.s, ns_tid, track_lower=0, track_upper=xr)
            self.add_pin('VDD', vdd)
            self.add_pin('VSS', vss)

        tr_manager = self.tr_manager
        tr_w_h = tr_manager.get_width(hm_layer, 'sig')
        tr_w_v = tr_manager.get_width(vm_layer, 'sig')
        mlm_in0 = mlm.get('in0', None)
        mlm_in1 = mlm.get('in1', None)
        nin_tid = get_adj_tid_list(self, ridx_n, sig_locs, MOSWireType.G, 'nin', True, tr_w_h)
        pin_tid = get_adj_tid_list(self, ridx_p, sig_locs, MOSWireType.G, 'pin', False, tr_w_h)

        if is_guarded:
            n_in0 = self.connect_to_tracks(nports.g0, nin_tid[0], min_len_mode=mlm_in0)
            n_in1 = self.connect_to_tracks(nports.g1, nin_tid[1], min_len_mode=mlm_in1)
            p_in0 = self.connect_to_tracks(pports.g0, pin_tid[0], min_len_mode=mlm_in0)
            p_in1 = self.connect_to_tracks(pports.g1, pin_tid[1], min_len_mode=mlm_in1)
            in0_tidx = sig_locs.get('in0', self.grid.coord_to_track(vm_layer, self.bound_box.xl,
                                                                    RoundMode.GREATER_EQ))
            in1_tidx = sig_locs.get('in1', self.grid.coord_to_track(vm_layer, self.bound_box.xh,
                                                                    RoundMode.LESS_EQ))
            if vertical_in:
                in0_vm = self.connect_to_tracks([n_in0, p_in0],
                                                TrackID(vm_layer, in0_tidx, width=tr_w_v))
                in1_vm = self.connect_to_tracks([n_in1, p_in1],
                                                TrackID(vm_layer, in1_tidx, width=tr_w_v))
                self.add_pin('in<0>', in0_vm)
                self.add_pin('in<1>', in1_vm)
                self.add_pin('nin<0>', n_in0, hide=True)
                self.add_pin('nin<1>', n_in1, hide=True)
                self.add_pin('pin<0>', p_in0, hide=True)
                self.add_pin('pin<1>', p_in1, hide=True)
            else:
                self.add_pin('nin<0>', n_in0, label='in<0>:')
                self.add_pin('nin<1>', n_in1, label='in<1>:')
                self.add_pin('pin<0>', p_in0, label='in<0>:')
                self.add_pin('pin<1>', p_in1, label='in<1>:')
        else:
            key_name = 'nin' if any(k in sig_locs for k in ['nin', 'nin0']) else 'pin'
            in_tid = get_adj_tid_list(self, ridx_n, sig_locs, MOSWireType.G, key_name, True, tr_w_h)
            in0_vm, in1_vm = [], []
            in0 = self.connect_to_tracks(list(chain(nports.g0, pports.g0)), in_tid[0],
                                         min_len_mode=mlm_in0, ret_wire_list=in0_vm)
            in1 = self.connect_to_tracks(list(chain(nports.g1, pports.g1)), in_tid[1],
                                         min_len_mode=mlm_in0, ret_wire_list=in1_vm)
            self.add_pin('nin<0>', in0, hide=True)
            self.add_pin('pin<0>', in0, hide=True)
            self.add_pin('nin<1>', in1, hide=True)
            self.add_pin('pin<1>', in1, hide=True)
            self.add_pin('in<0>', in0_vm)
            self.add_pin('in<1>', in1_vm)

        pd_tidx = sig_locs.get('pout',
                               self.get_track_index(ridx_p, MOSWireType.DS_GATE,
                                                    wire_name='sig', wire_idx=0))
        pd_tid = TrackID(hm_layer, pd_tidx, width=tr_w_h)
        mlm_out = mlm.get('out', MinLenMode.MIDDLE)
        if self.can_short_adj_tracks and not is_guarded:
            # we can short adjacent source/drain tracks together, so we can avoid going to vm_layer
            out = self.connect_to_tracks([pports.d, nports.d], pd_tid, min_len_mode=mlm_out)
            self.add_pin('pout', out, hide=True)
            self.add_pin('out', nports.d)
        else:
            # need to use vm_layer to short adjacent tracks.
            nd_tidx = sig_locs.get('nout',
                                   self.get_track_index(ridx_n, MOSWireType.DS_GATE,
                                                        wire_name='sig', wire_idx=-1))
            nd_tid = TrackID(hm_layer, nd_tidx, width=tr_w_h)
            nout = self.connect_to_tracks(nports.d, nd_tid, min_len_mode=mlm_out)
            pout = self.connect_to_tracks(pports.d, pd_tid, min_len_mode=mlm_out)
            vm_tidx = sig_locs.get('out', self.grid.coord_to_track(vm_layer, nout.middle,
                                                                   mode=RoundMode.GREATER_EQ))
            if vertical_out:
                out = self.connect_to_tracks([pout, nout], TrackID(vm_layer, vm_tidx))
                self.add_pin('pout', pout, hide=True)
                self.add_pin('nout', nout, hide=True)
                self.add_pin('out', out)
            else:
                self.add_pin('pout', pout, label='out:')
                self.add_pin('nout', nout, label='out:')

        self.sch_params = dict(
            seg_p=seg_p,
            seg_n=seg_n,
            lch=self.place_info.lch,
            w_p=self.place_info.get_row_place_info(ridx_p).row_info.width if w_p == 0 else w_p,
            w_n=self.place_info.get_row_place_info(ridx_n).row_info.width if w_n == 0 else w_n,
            th_n=self.place_info.get_row_place_info(ridx_n).row_info.threshold,
            th_p=self.place_info.get_row_place_info(ridx_p).row_info.threshold,
            stack_p=stack_p,
            stack_n=stack_n,
        )


def get_adj_tidx_list(layout: MOSBase, ridx: int, sig_locs: Mapping[str, Union[float, HalfInt]],
                      wtype: MOSWireType, prefix: str, up: bool) -> Tuple[HalfInt, HalfInt]:
    """Helper method that gives two adjacent signal wires, with sig_locs override."""
    hm_layer = layout.conn_layer + 1

    out0 = sig_locs.get(prefix + '0', None)
    if out0 is not None:
        # user specify output track index for both parities
        out1 = sig_locs[prefix + '1']
    else:
        out0 = sig_locs.get(prefix, None)
        if out0 is not None:
            # user only specify one index.
            out1 = layout.tr_manager.get_next_track(hm_layer, out0, 'sig', 'sig', up=up)
        else:
            # use default track indices
            widx = 0 if up else -1
            out0 = layout.get_track_index(ridx, wtype, wire_name='sig', wire_idx=widx)
            out1 = layout.tr_manager.get_next_track(hm_layer, out0, 'sig', 'sig', up=up)

    if out0 == out1:
        raise ValueError(f'{prefix}0 and {prefix}1 must be on different tracks.')

    return out0, out1


def get_adj_tid_list(layout: MOSBase, ridx: int, sig_locs: Mapping[str, Union[float, HalfInt]],
                     wtype: MOSWireType, prefix: str, up: bool, tr_w_h: int
                     ) -> Tuple[TrackID, TrackID]:
    hm_layer = layout.conn_layer + 1
    out0, out1 = get_adj_tidx_list(layout, ridx, sig_locs, wtype, prefix, up)
    return TrackID(hm_layer, out0, width=tr_w_h), TrackID(hm_layer, out1, width=tr_w_h)

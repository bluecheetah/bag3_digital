from typing import Any, Optional, Mapping, Type
from itertools import chain

from pybag.enum import MinLenMode, RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from ..stdcells.gates import InvCore
from ..stdcells.memory import FlopCore
from ...schematic.des_1toN import bag3_digital__des_1toN


class Des1toN(MOSBase):
    """
    This deserializer cell requires both clock and divided clock as input.
    """
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__des_1toN

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_dict='Dictionary of segments',
            des_ratio='Number of deserialized outputs',
            export_nets='True to export intermediate nets',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            export_nets=False,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg_dict: Mapping[str, int] = self.params['seg_dict']
        des_ratio: int = self.params['des_ratio']
        export_nets: bool = self.params['export_nets']

        # make masters
        ff_params = dict(pinfo=pinfo, seg=seg_dict['flop_fast'])
        ff_master = self.new_template(FlopCore, params=ff_params)

        fs_params = dict(pinfo=pinfo, seg=seg_dict['flop_slow'])
        fs_master = self.new_template(FlopCore, params=fs_params)

        f_ncols = max(ff_master.num_cols, fs_master.num_cols)

        invf_params = dict(pinfo=pinfo, seg=seg_dict['inv_fast'], vertical_out=False)
        invf_master = self.new_template(InvCore, params=invf_params)

        invs_params = dict(pinfo=pinfo, seg=seg_dict['inv_slow'], vertical_out=False)
        invs_master = self.new_template(InvCore, params=invs_params)

        inv_ncols = max(invf_master.num_cols, invs_master.num_cols)

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1

        # --- Placement --- #
        blk_sp = self.min_sep_col
        sub_sep = self.min_sep_col
        tap_ncols = self.get_tap_ncol()

        # left tap
        vdd_list, vss_list = [], []
        self.add_tap(0, vdd_list, vss_list, tile_idx=0)
        self.add_tap(0, vdd_list, vss_list, tile_idx=1)
        _coord = self.grid.track_to_coord(self.conn_layer, tap_ncols >> 1)
        sup_vm_idx = [self.grid.coord_to_track(vm_layer, _coord, RoundMode.NEAREST)]

        # clock inverters
        cur_col = tap_ncols + sub_sep
        invf = self.add_tile(invf_master, 0, cur_col)
        invs = self.add_tile(invs_master, 1, cur_col)

        # flops
        cur_col += inv_ncols
        ff_list, fs_list = [], []
        clk_list, clkb_list = [], []
        clk_div_list, clk_divb_list = [], []
        for idx in range(des_ratio):
            if idx == (des_ratio >> 1):
                # mid tap
                cur_col += sub_sep
                self.add_tap(cur_col, vdd_list, vss_list, tile_idx=0)
                self.add_tap(cur_col, vdd_list, vss_list, tile_idx=1)
                _coord = self.grid.track_to_coord(self.conn_layer, cur_col + (tap_ncols >> 1))
                sup_vm_idx.append(self.grid.coord_to_track(vm_layer, _coord, RoundMode.NEAREST))
                cur_col += tap_ncols + sub_sep
            else:
                cur_col += blk_sp
            ff = self.add_tile(ff_master, 0, cur_col)
            ff_list.append(ff)
            cur_col += f_ncols
            fs = self.add_tile(fs_master, 1, cur_col, flip_lr=True)
            fs_list.append(fs)

            # local routing
            clk_list.append(ff.get_pin('clk'))
            clkb_list.append(ff.get_pin('clkb'))
            clk_div_list.append(fs.get_pin('clk'))
            clk_divb_list.append(fs.get_pin('clkb'))

            self.reexport(fs.get_port('out'), net_name=f'dout<{idx}>')

            d_int = self.connect_to_track_wires(fs.get_pin('pin'), ff.get_pin('out'))
            if export_nets:
                self.add_pin(f'd<{idx}>', d_int)

            if idx == 0:
                self.reexport(ff.get_port('pin'), net_name='din', hide=False)
            else:
                self.connect_wires([ff.get_pin('pin'), ff_list[-2].get_pin('pout')])

        # right tap
        cur_col += sub_sep
        self.add_tap(cur_col, vdd_list, vss_list, tile_idx=0)
        self.add_tap(cur_col, vdd_list, vss_list, tile_idx=1)
        _coord = self.grid.track_to_coord(self.conn_layer, cur_col + (tap_ncols >> 1))
        sup_vm_idx.append(self.grid.coord_to_track(vm_layer, _coord, RoundMode.NEAREST))

        self.set_mos_size()
        xh = self.bound_box.xh

        # --- Routing --- #
        # supplies
        vss_hm_list, vdd_hm_list = [], []
        for inst in chain([invf, invs], ff_list, fs_list):
            vss_hm_list.append(inst.get_pin('VSS'))
            vdd_hm_list.append(inst.get_pin('VDD'))
        vss_hm = self.connect_to_track_wires(vss_list, self.connect_wires(vss_hm_list, lower=0, upper=xh))
        vss0_xm_idx = self.grid.coord_to_track(xm_layer, vss_hm[0][0].bound_box.ym, RoundMode.NEAREST)
        vss1_xm_idx = self.grid.coord_to_track(xm_layer, vss_hm[0][1].bound_box.ym, RoundMode.NEAREST)

        vdd_hm = self.connect_to_track_wires(vdd_list, self.connect_wires(vdd_hm_list, lower=0, upper=xh))
        vdd_xm_idx = self.grid.coord_to_track(xm_layer, vdd_hm[0].bound_box.ym, RoundMode.NEAREST)

        w_vm_sup = self.tr_manager.get_width(vm_layer, 'sup')
        w_xm_sup = self.tr_manager.get_width(xm_layer, 'sup')
        vss0_vm_list, vss1_vm_list, vdd_vm_list = [], [], []
        for vm_idx in sup_vm_idx:
            vm_tid = TrackID(vm_layer, vm_idx, w_vm_sup)
            vss0_vm_list.append(self.connect_to_tracks(vss_hm[0][0], vm_tid, min_len_mode=MinLenMode.UPPER))
            vss1_vm_list.append(self.connect_to_tracks(vss_hm[0][1], vm_tid, min_len_mode=MinLenMode.LOWER))
            vdd_vm_list.append(self.connect_to_tracks(vdd_hm[0], vm_tid, min_len_mode=MinLenMode.MIDDLE))

        vss0_xm = self.connect_to_tracks(vss0_vm_list, TrackID(xm_layer, vss0_xm_idx, w_xm_sup))
        vss1_xm = self.connect_to_tracks(vss1_vm_list, TrackID(xm_layer, vss1_xm_idx, w_xm_sup))
        vdd_xm = self.connect_to_tracks(vdd_vm_list, TrackID(xm_layer, vdd_xm_idx, w_xm_sup))
        self.add_pin('VSS', [vss_hm[0], vss0_xm, vss1_xm])
        self.add_pin('VDD', [vdd_hm[0], vdd_xm])

        # clkb
        clkb_pout = invf.get_pin('pout')
        clkb_nout = invf.get_pin('nout')
        clkb_vm_idx = self.grid.coord_to_track(vm_layer, clkb_pout.upper, RoundMode.NEAREST)
        w_vm_clk = self.tr_manager.get_width(vm_layer, 'clk')
        clkb_vm = TrackID(vm_layer, clkb_vm_idx, w_vm_clk)
        clkb_vm = self.connect_to_tracks([clkb_pout, clkb_nout], clkb_vm)
        clkb_list.append(clkb_vm)
        clkb_xm_idx = self.tr_manager.get_next_track(xm_layer, vss0_xm_idx, 'sup', 'clk', 1)
        w_xm_clk = self.tr_manager.get_width(xm_layer, 'clk')
        clkb_xm = self.connect_to_tracks(clkb_list, TrackID(xm_layer, clkb_xm_idx, w_xm_clk))
        if export_nets:
            self.add_pin('clkb', [clkb_vm, clkb_xm])

        # clk
        clk_vm = self.tr_manager.get_next_track_obj(clkb_vm, 'clk', 'clk', -1)
        clk_vm = self.connect_to_tracks(invf.get_pin('in'), clk_vm)
        clk_list.append(clk_vm)
        clk_xm_idx = self.tr_manager.get_next_track(xm_layer, vdd_xm_idx, 'sup', 'clk', -1)
        next_xm_idx = self.tr_manager.get_next_track(xm_layer, clk_xm_idx, 'clk', 'clk', -1)
        if clkb_xm_idx > next_xm_idx:
            raise ValueError(f'Not enough space for clk routing on xm_layer={xm_layer}.')
        clk_xm = self.connect_to_tracks(clk_list, TrackID(xm_layer, clk_xm_idx, w_xm_clk))
        self.add_pin('clk', [clk_vm, clk_xm])

        # clk_divb
        clk_divb_pout = invs.get_pin('pout')
        clk_divb_nout = invs.get_pin('nout')
        clk_divb_vm_idx = self.grid.coord_to_track(vm_layer, clk_divb_pout.upper, RoundMode.NEAREST)
        clk_divb_vm = TrackID(vm_layer, clk_divb_vm_idx, w_vm_clk)
        clk_divb_vm = self.connect_to_tracks([clk_divb_pout, clk_divb_nout], clk_divb_vm)
        clk_divb_list.append(clk_divb_vm)
        clk_divb_xm_idx = self.tr_manager.get_next_track(xm_layer, vss1_xm_idx, 'sup', 'clk', -1)
        clk_divb_xm = self.connect_to_tracks(clk_divb_list, TrackID(xm_layer, clk_divb_xm_idx, w_xm_clk))
        if export_nets:
            self.add_pin('clk_divb', [clk_divb_vm, clk_divb_xm])

        # clk_div
        clk_div_vm = self.tr_manager.get_next_track_obj(clk_divb_vm, 'clk', 'clk', -1)
        clk_div_vm = self.connect_to_tracks(invs.get_pin('in'), clk_div_vm)
        clk_div_list.append(clk_div_vm)
        clk_div_xm_idx = self.tr_manager.get_next_track(xm_layer, vdd_xm_idx, 'sup', 'clk', 1)
        next_xm_idx = self.tr_manager.get_next_track(xm_layer, clk_div_xm_idx, 'clk', 'clk', 1)
        if clk_divb_xm_idx < next_xm_idx:
            raise ValueError(f'Not enough space for clk_div routing on xm_layer={xm_layer}.')
        clk_div_xm = self.connect_to_tracks(clk_div_list, TrackID(xm_layer, clk_div_xm_idx, w_xm_clk))
        self.add_pin('clk_div', [clk_div_vm, clk_div_xm])

        # get schematic parameters
        self.sch_params = dict(
            flop_fast=ff_master.sch_params,
            flop_slow=fs_master.sch_params,
            inv_fast=invf_master.sch_params,
            inv_slow=invs_master.sch_params,
            des_ratio=des_ratio,
            export_nets=export_nets,
        )

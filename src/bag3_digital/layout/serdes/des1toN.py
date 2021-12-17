from typing import Any, Optional, Mapping, Type, Union, Tuple
from itertools import chain

from pybag.enum import MinLenMode, RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.enum import MOSWireType

from ..stdcells.gates import InvCore
from ..stdcells.memory import FlopCore
from ...schematic.des1toN import bag3_digital__des1toN


class Des1toN(MOSBase):
    """
    2 rows of FF
    This cell requires both clock and divided clock as inputs.
    """
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__des1toN

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            ridx_p='pch row index',
            ridx_n='nch row index',
            seg_dict='Dictionary of segments',
            ratio='Number of serialized inputs/deserialized outputs',
            horz_slow='True to have serialized inputs/deserialized outputs on horizontal layer',
            export_nets='True to export intermediate nets',
            tap_sep_flop='Horizontal separation between column taps in number of flops. Default is ratio // 2.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            ridx_p=-1,
            ridx_n=0,
            horz_slow=True,
            export_nets=False,
            tap_sep_flop=-1,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        seg_dict: Mapping[str, int] = self.params['seg_dict']
        ratio: int = self.params['ratio']
        horz_slow: bool = self.params['horz_slow']
        export_nets: bool = self.params['export_nets']
        tap_sep_flop: int = self.params['tap_sep_flop']
        if tap_sep_flop <= 0:
            tap_sep_flop = ratio >> 1

        # make masters
        ff_params = dict(pinfo=pinfo, seg=seg_dict['flop_fast'])
        ff_master = self.new_template(FlopCore, params=ff_params)

        fs_params = dict(pinfo=pinfo, seg=seg_dict['flop_slow'])
        fs_master = self.new_template(FlopCore, params=fs_params)

        f_ncols = max(ff_master.num_cols, fs_master.num_cols)

        # sig_locs for inverters in inverter chain
        pd1_tidx = self.get_track_index(ridx_p, MOSWireType.DS, 'sig', 1)
        pd0_tidx = self.get_track_index(ridx_p, MOSWireType.DS, 'sig', 0)
        pg_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -2)
        ng_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 1)
        nd1_tidx = self.get_track_index(ridx_n, MOSWireType.DS, 'sig', -1)
        nd0_tidx = self.get_track_index(ridx_n, MOSWireType.DS, 'sig', -2)
        seg_fast: Union[int, Tuple[int, int]] = seg_dict['inv_fast']
        if isinstance(seg_fast, int):
            assert seg_fast & 1 == 0, f'seg_dict["inv_fast"]={seg_fast} has to be even.'
            seg_fast0, seg_fast1 = seg_fast, seg_fast
        else:
            seg_fast0, seg_fast1 = seg_fast
            assert seg_fast0 & 1 == 0, f'seg_dict["inv_fast"][0]={seg_fast0} has to be even.'
            assert seg_fast1 & 1 == 0, f'seg_dict["inv_fast"][1]={seg_fast1} has to be even.'
        invf_0_params = dict(pinfo=pinfo, seg=seg_fast0, vertical_out=False,
                             sig_locs={'in': ng_tidx, 'pout': pd0_tidx, 'nout': nd1_tidx})
        invf_0_master = self.new_template(InvCore, params=invf_0_params)
        invf_1_params = dict(pinfo=pinfo, seg=seg_fast1, vertical_out=False,
                             sig_locs={'in': pg_tidx, 'pout': pd1_tidx, 'nout': nd0_tidx})
        invf_1_master = self.new_template(InvCore, params=invf_1_params)

        seg_slow: Union[int, Tuple[int, int]] = seg_dict['inv_slow']
        if isinstance(seg_slow, int):
            assert seg_slow & 1 == 0, f'seg_dict["inv_slow"]={seg_slow} has to be even.'
            seg_slow0, seg_slow1 = seg_slow, seg_slow
        else:
            seg_slow0, seg_slow1 = seg_slow
            assert seg_slow0 & 1 == 0, f'seg_dict["inv_slow"][0]={seg_slow0} has to be even.'
            assert seg_slow1 & 1 == 0, f'seg_dict["inv_slow"][1]={seg_slow1} has to be even.'
        invs_0_params = dict(pinfo=pinfo, seg=seg_slow0, vertical_out=False,
                             sig_locs={'in': ng_tidx, 'pout': pd0_tidx, 'nout': nd1_tidx})
        invs_0_master = self.new_template(InvCore, params=invs_0_params)
        invs_1_params = dict(pinfo=pinfo, seg=seg_slow1, vertical_out=False,
                             sig_locs={'in': pg_tidx, 'pout': pd1_tidx, 'nout': nd0_tidx})
        invs_1_master = self.new_template(InvCore, params=invs_1_params)

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1

        # --- Placement --- #
        blk_sp = self.min_sep_col
        sub_sep = self.sub_sep_col
        tap_ncols = self.get_tap_ncol()

        # left tap
        vdd_list, vss_list = [], []
        self.add_tap(0, vdd_list, vss_list, tile_idx=0)
        self.add_tap(0, vdd_list, vss_list, tile_idx=1)
        sup_coords = [self.grid.track_to_coord(self.conn_layer, tap_ncols >> 1)]
        cur_col = tap_ncols + sub_sep

        # clock inverters at beginning for deserializer
        invf_0 = self.add_tile(invf_0_master, 0, cur_col)
        invs_0 = self.add_tile(invs_0_master, 1, cur_col)
        cur_col += max(invf_0_master.num_cols, invs_0_master.num_cols)
        _, clk_vm_locs = self.tr_manager.place_wires(vm_layer, ['clk', 'clk', 'clk'],
                                                     center_coord=cur_col * self.sd_pitch)
        invf_1 = self.add_tile(invf_1_master, 0, cur_col)
        invs_1 = self.add_tile(invs_1_master, 1, cur_col)
        inv_list = [invf_0, invf_1, invs_0, invs_1]
        cur_col += max(invf_1_master.num_cols, invs_1_master.num_cols)
        clk_in_idx, clk_out_idx = 0, -1

        # flops
        ff_list, fs_list = [], []
        clk_list, clkb_list = [], []
        clk_div_list, clk_divb_list = [], []
        dslow_list = []
        for idx in range(ratio):
            if idx > 0 and idx % tap_sep_flop == 0:
                # mid tap
                cur_col += sub_sep
                self.add_tap(cur_col, vdd_list, vss_list, tile_idx=0)
                self.add_tap(cur_col, vdd_list, vss_list, tile_idx=1)
                sup_coords.append(self.grid.track_to_coord(self.conn_layer, cur_col + (tap_ncols >> 1)))
                cur_col += tap_ncols + sub_sep
            else:
                cur_col += blk_sp
            ff = self.add_tile(ff_master, 0, cur_col)
            ff_list.append(ff)
            cur_col += f_ncols
            fs = self.add_tile(fs_master, 1, cur_col, flip_lr=True)
            fs_list.append(fs)

            # local routing
            clk_vm = ff.get_pin('clk')
            clk_list.append(clk_vm)
            clkb_list.append(ff.get_pin('clkb'))
            clk_div_vm = fs.get_pin('clk')
            clk_div_list.append(clk_div_vm)
            clk_divb_list.append(fs.get_pin('clkb'))

            dslow = fs.get_pin('out')

            # check if dslow can be routed down to row 0 for connecting to xm_layer
            if horz_slow:
                avail_vm_idx = self.tr_manager.get_next_track(vm_layer, clk_vm.track_id.base_index, 'sig', 'sig', up=-1)
                if dslow.track_id.base_index > avail_vm_idx:
                    raise ValueError(f'dslow on vm_layer={vm_layer} cannot be routed down to row 0 for connecting to '
                                     f'xm_layer={xm_layer} because of collision / spacing error on vm_layer={vm_layer}')
                dslow_list.append(dslow)
            else:
                prefix = 'dout'
                self.add_pin(f'{prefix}<{idx}>', dslow)

            d_int = self.connect_to_track_wires(fs.get_pin('pin'), ff.get_pin('out'))
            self.add_pin(f'd<{idx}>', d_int, hide=not export_nets)

            if idx == 0:
                self.reexport(ff.get_port('pin'), net_name='din', hide=False)
            else:
                self.connect_wires([ff.get_pin('pin'), ff_list[-2].get_pin('pout')])

        # right tap
        cur_col += sub_sep
        self.add_tap(cur_col, vdd_list, vss_list, tile_idx=0)
        self.add_tap(cur_col, vdd_list, vss_list, tile_idx=1)
        sup_coords.append(self.grid.track_to_coord(self.conn_layer, cur_col + (tap_ncols >> 1)))

        self.set_mos_size()
        xh = self.bound_box.xh
        yh = self.bound_box.yh

        # --- Routing --- #
        # supplies
        vss_hm_list, vdd_hm_list = [], []
        for inst in chain(inv_list, ff_list, fs_list):
            vss_hm_list.append(inst.get_pin('VSS'))
            vdd_hm_list.append(inst.get_pin('VDD'))
        vss_hm = self.connect_to_track_wires(vss_list, self.connect_wires(vss_hm_list, lower=0, upper=xh))[0]
        vss0_xm_idx = self.grid.coord_to_track(xm_layer, vss_hm[0].bound_box.ym, RoundMode.NEAREST)
        vss1_xm_idx = self.grid.coord_to_track(xm_layer, vss_hm[1].bound_box.ym, RoundMode.NEAREST)

        vdd_hm = self.connect_to_track_wires(vdd_list, self.connect_wires(vdd_hm_list, lower=0, upper=xh))[0]
        vdd_xm_idx = self.grid.coord_to_track(xm_layer, vdd_hm.bound_box.ym, RoundMode.NEAREST)

        w_vm_sup = self.tr_manager.get_width(vm_layer, 'sup')
        w_xm_sup = self.tr_manager.get_width(xm_layer, 'sup')
        vss_vm_list, vdd_vm_list = [], []
        for _coord in sup_coords:
            _, _locs = self.tr_manager.place_wires(vm_layer, ['sup', 'sup'], center_coord=_coord)
            vss_tid = TrackID(vm_layer, _locs[0], w_vm_sup)
            vss_vm_list.append(self.connect_to_tracks(vss_hm, vss_tid, track_lower=0, track_upper=yh))
            vdd_tid = TrackID(vm_layer, _locs[-1], w_vm_sup)
            vdd_vm_list.append(self.connect_to_tracks(vdd_hm, vdd_tid, track_lower=0, track_upper=yh))

        vss0_xm = self.connect_to_tracks(vss_vm_list, TrackID(xm_layer, vss0_xm_idx, w_xm_sup))
        vss1_xm = self.connect_to_tracks(vss_vm_list, TrackID(xm_layer, vss1_xm_idx, w_xm_sup))
        vdd_xm = self.connect_to_tracks(vdd_vm_list, TrackID(xm_layer, vdd_xm_idx, w_xm_sup))
        self.add_pin('VSS', [vss_hm, self.connect_wires([vss0_xm, vss1_xm])[0]])
        self.add_pin('VDD', [vdd_hm, vdd_xm])
        self.add_pin('VSS_vm', vss_vm_list, hide=True)
        self.add_pin('VDD_vm', vdd_vm_list, hide=True)

        # find xm_layer tracks using supply tracks as reference
        xm_order = ['sup', 'clk', 'clk', 'sup']
        if horz_slow:
            num_out = - (- ratio // 2)
            xm_order[2:2] = ['sig'] * num_out
        try:
            xm_locs0 = self.tr_manager.spread_wires(xm_layer, xm_order, lower=vss0_xm_idx, upper=vdd_xm_idx,
                                                    sp_type=('clk', 'clk'))
            xm_locs1 = self.tr_manager.spread_wires(xm_layer, xm_order, lower=vdd_xm_idx, upper=vss1_xm_idx,
                                                    sp_type=('clk', 'clk'))
        except ValueError:
            raise ValueError(f'Not enough space to route slow speed signals on horizontal layer={xm_layer}. '
                             f'Use horz_slow=False.')

        # get slow serializer inputs / deserializer outputs on xm_layer
        w_xm_sig = self.tr_manager.get_width(xm_layer, 'sig')
        if horz_slow:
            # row 1
            num_slow1 = - (- ratio // 2)
            for idx in range(num_slow1):
                xm_tid = TrackID(xm_layer, xm_locs1[-3 - idx], w_xm_sig)
                dout_xm = self.connect_to_tracks(dslow_list[idx], xm_tid, track_upper=xh)
                self.add_pin(f'dout<{idx}>', dout_xm)

            # row 0
            num_slow0 = ratio - num_slow1
            for idx in range(num_slow0):
                xm_tid = TrackID(xm_layer, xm_locs0[-3 - idx], w_xm_sig)
                widx = idx + num_slow1
                dout_xm = self.connect_to_tracks(dslow_list[widx], xm_tid, track_upper=xh)
                self.add_pin(f'dout<{widx}>', dout_xm)

        # clkb_buf
        w_vm_clk = self.tr_manager.get_width(vm_layer, 'clk')
        clkb_vm = self.connect_to_tracks([invf_0.get_pin('pout'), invf_0.get_pin('nout'), invf_1.get_pin('nin')],
                                         TrackID(vm_layer, clk_vm_locs[1], w_vm_clk))
        clkb_list.append(clkb_vm)
        w_xm_clk = self.tr_manager.get_width(xm_layer, 'clk')
        clkb_xm = self.connect_to_tracks(clkb_list, TrackID(xm_layer, xm_locs0[1], w_xm_clk))
        self.add_pin('clkb_buf', [clkb_vm, clkb_xm], hide=not export_nets)

        # clk_buf
        clk_vm = self.connect_to_tracks([invf_1.get_pin('pout'), invf_1.get_pin('nout')],
                                        TrackID(vm_layer, clk_vm_locs[clk_out_idx], w_vm_clk))
        clk_list.append(clk_vm)
        clk_xm = self.connect_to_tracks(clk_list, TrackID(xm_layer, xm_locs0[-2], w_xm_clk))
        self.add_pin('clk_buf', [clk_vm, clk_xm], hide=not export_nets)

        # clk
        clk_in = self.connect_to_tracks(invf_0.get_pin('nin'), TrackID(vm_layer, clk_vm_locs[clk_in_idx], w_vm_clk),
                                        min_len_mode=MinLenMode.MIDDLE)
        self.add_pin('clk', clk_in)

        # clk_divb_buf
        clk_divb_vm = self.connect_to_tracks([invs_0.get_pin('pout'), invs_0.get_pin('nout'), invs_1.get_pin('nin')],
                                             TrackID(vm_layer, clk_vm_locs[1], w_vm_clk))
        clk_divb_list.append(clk_divb_vm)
        clk_divb_xm = self.connect_to_tracks(clk_divb_list, TrackID(xm_layer, xm_locs1[-2], w_xm_clk))
        self.add_pin('clk_divb_buf', [clk_divb_vm, clk_divb_xm], hide=not export_nets)

        # clk_div_buf
        clk_div_vm = self.connect_to_tracks([invs_1.get_pin('pout'), invs_1.get_pin('nout')],
                                            TrackID(vm_layer, clk_vm_locs[clk_out_idx], w_vm_clk))
        clk_div_list.append(clk_div_vm)
        clk_div_xm = self.connect_to_tracks(clk_div_list, TrackID(xm_layer, xm_locs1[1], w_xm_clk))
        self.add_pin('clk_div_buf', [clk_div_vm, clk_div_xm], hide=not export_nets)

        # clk_div
        clk_div = self.connect_to_tracks(invs_0.get_pin('nin'), TrackID(vm_layer, clk_vm_locs[clk_in_idx], w_vm_clk),
                                         min_len_mode=MinLenMode.MIDDLE)
        self.add_pin('clk_div', clk_div)

        # get schematic parameters
        self.sch_params = dict(
            flop_fast=ff_master.sch_params,
            flop_slow=fs_master.sch_params,
            inv_fast=dict(inv_params=[invf_0_master.sch_params, invf_1_master.sch_params], dual_output=True),
            inv_slow=dict(inv_params=[invs_0_master.sch_params, invs_1_master.sch_params], dual_output=True),
            ratio=ratio,
            export_nets=export_nets,
        )

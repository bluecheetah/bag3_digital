from typing import Any, Optional, Mapping, Type
from itertools import chain

from pybag.enum import MinLenMode, RoundMode, PinMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.enum import MOSWireType

from ..stdcells.gates import InvCore, InvTristateCore
from ..stdcells.memory import FlopCore
from ...schematic.serNto1 import bag3_digital__serNto1


class SerNto1(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__serNto1

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            ridx_p='pch row index',
            ridx_n='nch row index',
            seg_dict='Dictionary of segments',
            ratio='Number of serialized inputs',
            export_nets='True to export intermediate nets',
            tap_sep_flop='Horizontal separation between column taps in number of flops. Default is ratio // 2.'
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            ridx_p=-1,
            ridx_n=0,
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
        export_nets: bool = self.params['export_nets']
        tap_sep_flop: int = self.params['tap_sep_flop']
        if tap_sep_flop <= 0:
            tap_sep_flop = ratio >> 1

        # make masters
        ff_params = dict(pinfo=pinfo, seg=seg_dict['ff'])
        ff_master = self.new_template(FlopCore, params=ff_params)
        ff_ncols = ff_master.num_cols

        ff_rst_params = dict(pinfo=pinfo, seg=seg_dict['ff'], resetable=True, rst_type='RESET')
        ff_rst_master = self.new_template(FlopCore, params=ff_rst_params)
        ff_rst_ncols = ff_rst_master.num_cols

        ff_set_params = dict(pinfo=pinfo, seg=seg_dict['ff'], resetable=True, rst_type='SET')
        ff_set_master = self.new_template(FlopCore, params=ff_set_params)

        # sig_locs for inverters in clock inverter chain
        pd1_tidx = self.get_track_index(ridx_p, MOSWireType.DS, 'sig', 1)
        pd0_tidx = self.get_track_index(ridx_p, MOSWireType.DS, 'sig', 0)
        pg1_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -2)
        pg0_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -3)
        ng_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 1)
        nd1_tidx = self.get_track_index(ridx_n, MOSWireType.DS, 'sig', -1)
        nd0_tidx = self.get_track_index(ridx_n, MOSWireType.DS, 'sig', -2)
        seg_clk: int = seg_dict['inv_clk']
        assert seg_clk & 1 == 0, f'seg_dict["inv_clk"]={seg_clk} has to be even.'
        inv_0_params = dict(pinfo=pinfo, seg=seg_clk, vertical_out=False,
                            sig_locs={'in': ng_tidx, 'pout': pd0_tidx, 'nout': nd1_tidx})
        inv_0_master = self.new_template(InvCore, params=inv_0_params)
        inv_1_params = dict(pinfo=pinfo, seg=seg_clk, vertical_out=False,
                            sig_locs={'in': pg1_tidx, 'pout': pd1_tidx, 'nout': nd0_tidx})
        inv_1_master = self.new_template(InvCore, params=inv_1_params)
        inv_clk_ncols = inv_0_master.num_cols

        inv_en_params = dict(pinfo=pinfo, seg=seg_dict['inv_en'], vertical_out=False,
                             sig_locs={'in': pg0_tidx, 'pout': pd0_tidx, 'nout': nd0_tidx})
        inv_en_master = self.new_template(InvCore, params=inv_en_params)
        inv_en_ncols = inv_en_master.num_cols

        inv_r_params = dict(pinfo=pinfo, seg=seg_dict['inv_rst'], vertical_out=False,
                            sig_locs={'in': ng_tidx, 'pout': pd1_tidx, 'nout': nd1_tidx})
        inv_r_master = self.new_template(InvCore, params=inv_r_params)
        inv_r_ncols = inv_r_master.num_cols

        tinv_params = dict(pinfo=pinfo, seg=seg_dict['tinv'], vertical_out=False,
                           sig_locs={'nin': pg0_tidx, 'pout': pd1_tidx, 'nout': nd0_tidx})
        tinv_master = self.new_template(InvTristateCore, params=tinv_params)
        tinv_ncols = tinv_master.num_cols

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
        cur_col = tap_ncols + sub_sep - blk_sp

        # flops
        ff_list, ff_rst_list = [], []
        clk_list, clkb_list = [], []
        clk_div_list, clk_divb_list = [], []
        inv_en_list, tinv_list = [], []
        inv_r = None
        _p_prev = None
        _p_ini = None
        rst_vm = None
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')
        out_list = []
        rst_list = []
        in_list = []
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

            # tile 0
            cur_col0 = cur_col
            ff_rst = self.add_tile(ff_rst_master if idx > 0 else ff_set_master, 0, cur_col0)
            ff_rst_list.append(ff_rst)
            cur_col0 += ff_rst_ncols
            clk_list.append(ff_rst.get_pin('clk'))
            clkb_list.append(ff_rst.get_pin('clkb'))

            cur_col0 += blk_sp
            inv_en = self.add_tile(inv_en_master, 0, cur_col0)
            inv_en_list.append(inv_en)
            cur_col0 += inv_en_ncols

            if idx == 0:
                cur_col0 += blk_sp + inv_r_ncols
                inv_r = self.add_tile(inv_r_master, 0, cur_col0, flip_lr=True)
                _, rst_vm_locs = self.tr_manager.place_wires(vm_layer, ['sig', 'sig', 'sig'],
                                                             center_coord=(cur_col0 - inv_r_ncols // 2) * self.sd_pitch)
                # rstb
                self.connect_to_tracks([ff_rst.get_pin('psetb'), inv_r.get_pin('pout'), inv_r.get_pin('nout')],
                                       TrackID(vm_layer, rst_vm_locs[0], w_sig_vm))
                rst_vm = self.connect_to_tracks(inv_r.get_pin('nin'), TrackID(vm_layer, rst_vm_locs[-1], w_sig_vm),
                                                min_len_mode=MinLenMode.UPPER)
            else:
                rst_list.append(ff_rst.get_pin('prst'))

            # tile 1
            cur_col1 = cur_col
            ff = self.add_tile(ff_master, 1, cur_col1)
            ff_list.append(ff)
            cur_col1 += ff_ncols
            clk_div_vm = ff.get_pin('clk')
            clk_div_list.append(clk_div_vm)
            clk_divb_list.append(ff.get_pin('clkb'))

            cur_col1 += blk_sp
            tinv = self.add_tile(tinv_master, 1, cur_col1)
            tinv_list.append(tinv)
            cur_col1 += tinv_ncols

            cur_col = max(cur_col0, cur_col1)

            # local routing
            # ff output to tinv input
            _d = self.connect_to_track_wires(tinv.get_pin('nin'), ff.get_pin('out'))
            self.add_pin(f'd<{idx}>', _d, hide=not export_nets)

            # ff input
            in_vm_tid = self.tr_manager.get_next_track_obj(clk_div_vm, 'sig', 'sig', count_rel_tracks=-1)
            in_vm = self.connect_to_tracks(ff.get_pin('pin'), in_vm_tid, min_len_mode=MinLenMode.MIDDLE)
            in_list.append(in_vm)

            # ff_rst output to inv_en input to tinv en
            _p0 = ff_rst.get_pin('out')
            _, en_vm_locs = self.tr_manager.place_wires(vm_layer, ['sig', 'sig', 'sig', 'sig', 'sig'],
                                                        _p0.track_id.base_index)
            _avail_vm_tidx = self.tr_manager.get_next_track(vm_layer, _d.track_id.base_index, 'sig', 'sig', 1)
            if _p0.track_id.base_index >= _avail_vm_tidx:
                en_tidx = _p0.track_id.base_index
            else:
                en_tidx = en_vm_locs[-3]
            _p = self.connect_to_tracks([ff_rst.get_pin('pout'), ff_rst.get_pin('nout'), inv_en.get_pin('nin'),
                                         tinv.get_pin('en')], TrackID(vm_layer, en_tidx, w_sig_vm))
            self.add_pin(f'p<{idx}>', _p, hide=not export_nets)

            # inv_en output to tinv enb
            _pb = self.connect_to_tracks([inv_en.get_pin('pout'), inv_en.get_pin('nout'), tinv.get_pin('enb')],
                                         TrackID(vm_layer, en_vm_locs[-2], w_sig_vm))

            # output
            _out = self.connect_to_tracks([tinv.get_pin('pout'), tinv.get_pin('nout')],
                                          TrackID(vm_layer, en_vm_locs[-1], w_sig_vm))
            out_list.append(_out)

            # ff_rst input to previous ff_rst output
            if idx == 0:
                _p_ini = self.connect_to_tracks(ff_rst.get_pin('pin'), in_vm_tid, min_len_mode=MinLenMode.MIDDLE)
            else:
                self.connect_to_track_wires(ff_rst.get_pin('nin'), _p_prev)

            # setup for next iteration
            _p_prev = _p

        # clock inverters chains
        cur_col += blk_sp + inv_clk_ncols
        invf_1 = self.add_tile(inv_1_master, 0, cur_col, flip_lr=True)
        invs_1 = self.add_tile(inv_1_master, 1, cur_col, flip_lr=True)
        _, clk_vm_locs = self.tr_manager.place_wires(vm_layer, ['clk', 'clk', 'clk'],
                                                     center_coord=cur_col * self.sd_pitch)
        cur_col += inv_clk_ncols
        invf_0 = self.add_tile(inv_0_master, 0, cur_col, flip_lr=True)
        invs_0 = self.add_tile(inv_0_master, 1, cur_col, flip_lr=True)
        inv_clk_list = [invf_0, invf_1, invs_0, invs_1]

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
        for inst in chain(ff_rst_list, inv_en_list, ff_list, tinv_list, [inv_r], inv_clk_list):
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
        xm_locs0 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'clk', 'clk', 'sup'], lower=vss0_xm_idx,
                                                upper=vdd_xm_idx, sp_type=('clk', 'clk'))
        xm_locs1 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'sig', 'clk', 'clk', 'sup'], lower=vdd_xm_idx,
                                                upper=vss1_xm_idx, sp_type=('clk', 'clk'))

        # clkb_buf
        w_vm_clk = self.tr_manager.get_width(vm_layer, 'clk')
        clkb_vm = self.connect_to_tracks([invf_0.get_pin('pout'), invf_0.get_pin('nout'), invf_1.get_pin('nin')],
                                         TrackID(vm_layer, clk_vm_locs[1], w_vm_clk))
        clkb_list.append(clkb_vm)
        w_xm_clk = self.tr_manager.get_width(xm_layer, 'clk')
        clkb_xm = self.connect_to_tracks(clkb_list, TrackID(xm_layer, xm_locs0[1], w_xm_clk))
        self.add_pin('clkb_buf', clkb_xm, hide=not export_nets, mode=PinMode.LOWER)

        # clk_buf
        clk_vm = self.connect_to_tracks([invf_1.get_pin('pout'), invf_1.get_pin('nout')],
                                        TrackID(vm_layer, clk_vm_locs[0], w_vm_clk))
        clk_list.append(clk_vm)
        clk_xm = self.connect_to_tracks(clk_list, TrackID(xm_layer, xm_locs0[-2], w_xm_clk))
        self.add_pin('clk_buf', clk_xm, hide=not export_nets, mode=PinMode.LOWER)

        # clk
        clk_in_vm = self.connect_to_tracks(invf_0.get_pin('nin'), TrackID(vm_layer, clk_vm_locs[-1], w_vm_clk),
                                        min_len_mode=MinLenMode.MIDDLE)
        clk_in_xm = self.connect_to_tracks(clk_in_vm, TrackID(xm_layer, xm_locs0[2], w_xm_clk),
                                           min_len_mode=MinLenMode.UPPER)
        self.add_pin('clk', clk_in_xm)

        # clk_divb_buf
        clk_divb_vm = self.connect_to_tracks([invs_0.get_pin('pout'), invs_0.get_pin('nout'), invs_1.get_pin('nin')],
                                             TrackID(vm_layer, clk_vm_locs[1], w_vm_clk))
        clk_divb_list.append(clk_divb_vm)
        clk_divb_xm = self.connect_to_tracks(clk_divb_list, TrackID(xm_layer, xm_locs1[-2], w_xm_clk))
        self.add_pin('clk_divb_buf', clk_divb_xm, hide=not export_nets, mode=PinMode.LOWER)

        # clk_div_buf
        clk_div_vm = self.connect_to_tracks([invs_1.get_pin('pout'), invs_1.get_pin('nout')],
                                            TrackID(vm_layer, clk_vm_locs[0], w_vm_clk))
        clk_div_list.append(clk_div_vm)
        clk_div_xm = self.connect_to_tracks(clk_div_list, TrackID(xm_layer, xm_locs1[1], w_xm_clk))
        self.add_pin('clk_div_buf', clk_div_xm, hide=not export_nets, mode=PinMode.LOWER)

        # clk_div
        clk_div_vm = self.connect_to_tracks(invs_0.get_pin('nin'), TrackID(vm_layer, clk_vm_locs[-1], w_vm_clk),
                                            min_len_mode=MinLenMode.MIDDLE)
        w_sig_xm = self.tr_manager.get_width(xm_layer, 'sig')
        clk_div_xm = self.connect_to_tracks(clk_div_vm, TrackID(xm_layer, xm_locs1[2], w_sig_xm),
                                           min_len_mode=MinLenMode.UPPER)
        self.add_pin('clk_div', [clk_div_vm, clk_div_xm])

        # connect last p<> to complete shift register
        self.connect_to_tracks([_p_ini, _p_prev], TrackID(xm_layer, xm_locs0[2], w_xm_clk))

        # reset
        rst_vm = self.connect_to_track_wires(rst_list, rst_vm)
        self.add_pin('rst', rst_vm)

        # output
        doutb = self.connect_to_tracks(out_list, TrackID(xm_layer, xm_locs1[-3], w_xm_clk))
        self.add_pin('doutb', doutb, mode=PinMode.UPPER)

        # inputs on xm_layer
        in_xm_tid = TrackID(xm_layer, xm_locs1[2], w_sig_xm)
        for idx, in_vm in enumerate(in_list):
            in_xm = self.connect_to_tracks(in_vm, in_xm_tid, min_len_mode=MinLenMode.MIDDLE)
            self.add_pin(f'din<{idx}>', in_xm)

        # get schematic parameters
        self.sch_params = dict(
            ff_rst=ff_rst_master.sch_params,
            ff_set=ff_set_master.sch_params,
            inv_r=inv_r_master.sch_params,
            inv_en=inv_en_master.sch_params,
            ff=ff_master.sch_params,
            tinv=tinv_master.sch_params,
            inv_clk=dict(inv_params=[inv_0_master.sch_params, inv_1_master.sch_params], dual_output=True),
            ratio=ratio,
            export_nets=export_nets,
        )

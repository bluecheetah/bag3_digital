from typing import Any, Optional, Mapping, Type, Sequence, Union, Tuple
from itertools import chain

from pybag.enum import MinLenMode, RoundMode, PinMode

from bag.util.immutable import Param
from bag.util.math import HalfInt
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID, WireArray

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.enum import MOSWireType

from ..stdcells.gates import InvCore, InvTristateCore, InvChainCore
from ..stdcells.memory import FlopCore
from ...schematic.serNto1_fast import bag3_digital__serNto1_fast


class SerNto1Fast(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__serNto1_fast

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            ridx_p='pch row index',
            ridx_n='nch row index',
            seg_dict='Dictionary of segments',
            ratio='Number of serialized inputs',
            export_nets='True to export intermediate nets',
            tap_sep_flop='Horizontal separation between column taps in number of flops. Default is ratio // 2.',
            is_rst_async='True if asynchronous rst input; False if synchronous rstb input. True by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            ridx_p=-1,
            ridx_n=0,
            export_nets=False,
            tap_sep_flop=-1,
            is_rst_async=True
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
        is_rst_async: bool = self.params['is_rst_async']

        # --- Make masters --- #
        # flops
        ff_params = dict(pinfo=pinfo, seg=seg_dict['ff'])
        ff_master = self.new_template(FlopCore, params=ff_params)
        ff_ncols = ff_master.num_cols

        ff_rst_params = dict(pinfo=pinfo, seg=seg_dict['ff'], resetable=True, rst_type='RESET')
        ff_rst_master = self.new_template(FlopCore, params=ff_rst_params)
        ff_rst_ncols = ff_rst_master.num_cols

        ff_set_params = dict(pinfo=pinfo, seg=seg_dict['ff'], resetable=True, rst_type='SET')
        ff_set_master = self.new_template(FlopCore, params=ff_set_params)

        # sig_locs for inverters in clk_div inverter chain
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

        # inverter for fast clk and clkb
        seg_clk_fast = 2 * seg_clk
        inv_clk_params = dict(pinfo=pinfo, seg=seg_clk_fast, vertical_out=False, sig_locs={'in': pg1_tidx})
        inv_clk_master = self.new_template(InvCore, params=inv_clk_params)

        # inverter chain for p0
        inv_en_params = dict(pinfo=pinfo, seg_list=seg_dict['inv_en'], dual_output=True,
                             sig_locs={'nin0': pg0_tidx, 'nin1': ng_tidx})
        inv_en_master = self.new_template(InvChainCore, params=inv_en_params)
        inv_en_ncols = inv_en_master.num_cols

        # inverter chain for rst
        inv_r_params = dict(pinfo=pinfo, seg_list=seg_dict['inv_rst'], dual_output=True,
                            sig_locs={'nin0': pg0_tidx, 'nin1': ng_tidx})
        inv_r_master = self.new_template(InvChainCore, params=inv_r_params)
        inv_r_ncols = inv_r_master.num_cols

        # tristate inverters
        tinv_params = dict(pinfo=pinfo, seg=seg_dict['tinv'], vertical_out=False,
                           sig_locs={'nin': pg0_tidx, 'pout': pd1_tidx, 'nout': nd0_tidx})
        tinv_master = self.new_template(InvTristateCore, params=tinv_params)
        tinv_ncols = tinv_master.num_cols

        # data inverters
        seg_data: int = seg_dict['inv_data']
        assert seg_data & 1 == 0, f'seg_dict["inv_data"]={seg_data} has to be even.'
        inv_d_params = dict(pinfo=pinfo, seg=seg_data // 2, vertical_out=False,
                            sig_locs={'in': ng_tidx, 'pout': pd0_tidx, 'nout': nd1_tidx})
        inv_d_master = self.new_template(InvCore, params=inv_d_params)
        inv_d_sch = dict(**inv_d_master.sch_params)
        inv_d_sch['seg_p'] = inv_d_sch['seg_n'] = seg_data
        inv_d_ncols = inv_d_master.num_cols

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1
        ym_layer = xm_layer + 1
        xxm_layer = ym_layer + 1

        # --- Placement --- #
        blk_sp = self.min_sep_col
        sub_sep = self.sub_sep_col
        seg_tap = 4
        tap_ncols = self.get_tap_ncol(seg_tap)
        num_tiles = 3

        # left tap
        vdd_list = [[] for _ in range(num_tiles)]
        vss_list = [[] for _ in range(num_tiles)]
        for idx in range(num_tiles):
            self.add_tap(0, vdd_list[idx], vss_list[idx], tile_idx=idx, seg=seg_tap)
        sup_coords = [self.grid.track_to_coord(self.conn_layer, tap_ncols >> 1)]
        cur_col = tap_ncols + sub_sep - blk_sp

        # flops
        ff_f_list, ff_s_list, ff_rst_list = [], [], []
        clk_list0, clkb_list0 = [], []
        clk_list1, clkb_list1 = [], []
        clk_div_list, clk_divb_list = [], []
        tinv_f_list, tinv_s_list = [], []
        en_list, enb_list = [], []
        inv_r = None
        inv_en = None
        p0_list = []
        _d = None
        dout_vm = None
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')
        rst_hm_list, rst_vm_list = [], []
        in_list = []
        for idx in range(ratio + 1):
            if idx > 0 and idx % tap_sep_flop == 0:
                # mid tap
                cur_col += sub_sep
                for tidx in range(num_tiles):
                    self.add_tap(cur_col, vdd_list[tidx], vss_list[tidx], tile_idx=tidx, seg=seg_tap)
                sup_coords.append(self.grid.track_to_coord(self.conn_layer, cur_col + (tap_ncols >> 1)))
                cur_col += tap_ncols + sub_sep
            else:
                cur_col += blk_sp

            # tile 0: p0 counter
            cur_col0 = cur_col
            if idx == ratio:
                inv_en = self.add_tile(inv_en_master, 0, cur_col0)
                cur_col0 += inv_en_ncols
                # inv_en input
                p0_list.append(self.connect_to_track_wires(inv_en.get_pin('nin'), ff_rst_list[-1].get_pin('out')))
                self.add_pin('p<0>', p0_list[-1], hide=not export_nets)

                # inv_en out and outb
                en_list.append(inv_en.get_pin('out'))
                enb_list.append(inv_en.get_pin('outb'))

                cur_col0 += blk_sp + inv_r_ncols
                inv_r = self.add_tile(inv_r_master, 0, cur_col0, flip_lr=True)

                # rstb_sync
                ff_set = ff_rst_list[-1]
                self.connect_to_track_wires(ff_set.get_pin('psetb'), inv_r.get_pin('out'))
                rst_vm_list.append(inv_r.get_pin('outb'))
            else:
                ff_rst = self.add_tile(ff_rst_master if idx < ratio - 1 else ff_set_master, 0, cur_col0)
                ff_rst_list.append(ff_rst)
                cur_col0 += ff_rst_ncols
                # ff_rst is on clkb
                clk_vm = ff_rst.get_pin('clk')
                clkb_list0.append(clk_vm)
                clk_list0.append(ff_rst.get_pin('clkb'))

                # ff_rst input
                if idx == 0:
                    in_vm_tid = self.tr_manager.get_next_track_obj(clk_vm, 'sig', 'sig', count_rel_tracks=-1)
                    p0_list.append(self.connect_to_tracks(ff_rst.get_pin('pin'), in_vm_tid,
                                                          min_len_mode=MinLenMode.MIDDLE))
                else:
                    _p = self.connect_to_track_wires(ff_rst.get_pin('pin'), ff_rst_list[-2].get_pin('out'))
                    self.add_pin(f'p<{idx}>', _p, hide=not export_nets)

                # ff_rst rst
                if idx < ratio - 1:
                    rst_hm = ff_rst.get_pin('prst')
                    rst_hm_list.append(rst_hm)
                    rst_vm_tid = self.tr_manager.get_next_track_obj(ff_rst.get_pin('out'), 'sig', 'sig', 1)
                    rst_vm_list.append(self.connect_to_tracks(rst_hm, rst_vm_tid, min_len_mode=MinLenMode.LOWER))

            # tile 1: fast flops and tinv and data inverter
            tinv_out_list, inv_out_list = [], []
            en_hm_list, enb_hm_list = [], []
            cur_col1 = cur_col
            if idx > 0:
                ff_f = self.add_tile(ff_master, 1, cur_col1)
                ff_f_list.append(ff_f)
                cur_col1 += ff_ncols
                clk_list1.append(ff_f.get_pin('clk'))
                clkb_list1.append(ff_f.get_pin('clkb'))

                # ff_f input
                self.connect_to_track_wires(ff_f.get_pin('nin'), _d)

                if idx < ratio:
                    cur_col1 += blk_sp
                    tinv_f = self.add_tile(tinv_master, 1, cur_col1)
                    cur_col1 += tinv_ncols + blk_sp
                    inv_f = self.add_tile(inv_d_master, 1, cur_col1)
                    cur_col1 += inv_d_ncols
                    tinv_f_list.extend([tinv_f, inv_f])

                    # ff_f output to tinv_f input
                    self.connect_to_track_wires(tinv_f.get_pin('nin'), ff_f.get_pin('out'))

                    # tinv_f output, inv_f input and output
                    tinv_out_list.extend([tinv_f.get_pin('pout'), tinv_f.get_pin('nout'), inv_f.get_pin('nin')])
                    inv_out_list.extend([inv_f.get_pin('pout'), inv_f.get_pin('nout')])

                    # tinv_f enable
                    en_hm_list.append(tinv_f.get_pin('enb'))
                    enb_hm_list.append(tinv_f.get_pin('en'))
                else:
                    dout_vm = ff_f.get_pin('out')

            # tile 2: slow flops and tinv and data inverter
            cur_col2 = cur_col
            if idx < ratio:
                ff_s = self.add_tile(ff_master, 2, cur_col2)
                ff_s_list.append(ff_s)
                cur_col2 += ff_ncols
                clk_div_vm = ff_s.get_pin('clk')
                clk_div_list.append(clk_div_vm)
                clk_divb_list.append(ff_s.get_pin('clkb'))

                # ff_s input
                in_vm_tid = self.tr_manager.get_next_track_obj(clk_div_vm, 'sig', 'sig', count_rel_tracks=-1)
                in_vm = self.connect_to_tracks(ff_s.get_pin('pin'), in_vm_tid, min_len_mode=MinLenMode.MIDDLE)
                in_list.append(in_vm)

                if idx > 0:
                    cur_col2 += blk_sp
                    tinv_s = self.add_tile(tinv_master, 2, cur_col2)
                    cur_col2 += tinv_ncols + blk_sp
                    inv_s = self.add_tile(inv_d_master, 2, cur_col2)
                    cur_col2 += inv_d_ncols
                    tinv_s_list.extend([tinv_s, inv_s])
                    _tidx = self.grid.coord_to_track(vm_layer, cur_col2 * self.sd_pitch, RoundMode.NEAREST)
                    _, _vm_locs = self.tr_manager.place_wires(vm_layer, ['sig'] * 5, _tidx, -1)

                    # ff_s output to tinv_s input
                    self.connect_to_track_wires(tinv_s.get_pin('nin'), ff_s.get_pin('out'))

                    # tinv_s output, inv_s input and output
                    tinv_out_list.extend([tinv_s.get_pin('pout'), tinv_s.get_pin('nout'), inv_s.get_pin('nin')])
                    self.connect_to_tracks(tinv_out_list, TrackID(vm_layer, _vm_locs[-3], w_sig_vm))
                    inv_out_list.extend([inv_s.get_pin('pout'), inv_s.get_pin('nout')])
                    _d = self.connect_to_tracks(inv_out_list, TrackID(vm_layer, _vm_locs[-1], w_sig_vm))

                    # tinv_s enable
                    en_hm_list.append(tinv_s.get_pin('en'))
                    enb_hm_list.append(tinv_s.get_pin('enb'))

                    enb_list.append(self.connect_to_tracks(enb_hm_list, TrackID(vm_layer, _vm_locs[0], w_sig_vm)))
                    en_list.append(self.connect_to_tracks(en_hm_list, TrackID(vm_layer, _vm_locs[1], w_sig_vm)))
                else:
                    _d = ff_s.get_pin('out')
                self.add_pin(f'd<{ratio - 1 - idx}>', _d, hide=not export_nets)

            cur_col = max(cur_col0, cur_col1, cur_col2)

        inst0_list = [inv_r, inv_en]
        inst1_list = []

        # flops for reset synchronizer
        if is_rst_async:
            cur_col += blk_sp
            rst_ff0 = self.add_tile(ff_rst_master, 0, cur_col + ff_rst_ncols, flip_lr=True)
            inst0_list.append(rst_ff0)
            clkb_list0.append(rst_ff0.get_pin('clk'))
            clk_list0.append(rst_ff0.get_pin('clkb'))
            self.connect_to_track_wires(inv_r.get_pin('in'), rst_ff0.get_pin('out'))

            # extra blk_sp so that rst_ff1 output on vm_layer can go down to rst_ff0 input
            cur_col += ff_rst_ncols + blk_sp
            rst_ff1 = self.add_tile(ff_rst_master, 1, cur_col - ff_rst_ncols)
            inst1_list.append(rst_ff1)
            rst_ff1_clkb = rst_ff1.get_pin('clk')
            clkb_list1.append(rst_ff1_clkb)
            clk_list1.append(rst_ff1.get_pin('clkb'))
            _in_vm_tid = self.tr_manager.get_next_track_obj(rst_ff1_clkb, 'sig', 'sig', -1)
            self.connect_to_tracks([rst_ff1.get_pin('nin'), rst_ff1.get_pin('VDD')], _in_vm_tid)
            rst_ff1_out = rst_ff1.get_pin('out')
            self.connect_to_track_wires(rst_ff0.get_pin('nin'), rst_ff1_out)

            rstb_in_vm = None

            rst_sync_sch_params = dict(ff=ff_rst_master.sch_params, buf=inv_r_master.sch_params)
            _p0_ym_idx = -3
        else:
            rst_ff1_out = None
            rst_ff0 = rst_ff1 = None
            _tid = self.tr_manager.get_next_track_obj(inv_r.get_pin('outb'), 'sig', 'sig', 1)
            rstb_in_vm = self.connect_to_tracks(inv_r.get_pin('in'), _tid)

            rst_sync_sch_params = inv_r_master.sch_params
            _p0_ym_idx = -2

        # clock inverters chains
        cur_col += blk_sp
        _lower_idx = self.grid.coord_to_track(vm_layer, cur_col * self.sd_pitch, RoundMode.GREATER)
        cur_col += inv_clk_ncols
        invs_1 = self.add_tile(inv_1_master, 2, cur_col, flip_lr=True)
        cur_col += inv_clk_ncols
        _upper_idx = self.grid.coord_to_track(vm_layer, cur_col * self.sd_pitch, RoundMode.LESS)
        invs_0 = self.add_tile(inv_0_master, 2, cur_col, flip_lr=True)

        invf_0 = self.add_tile(inv_clk_master, 0, cur_col, flip_lr=True)
        invf_1 = self.add_tile(inv_clk_master, 1, cur_col, flip_lr=True)

        inst0_list.append(invf_0)
        inst1_list.append(invf_1)

        # try to fit as many vm_layer tracks as possible
        clk_vm_locs = []
        vm_clk_num = 1
        for vm_clk_num in range(4, 0, -1):
            try:
                _num = (vm_clk_num * 2 - 1) * 2 + 3
                clk_vm_locs = self.tr_manager.spread_wires(vm_layer, ['clk'] * _num,
                                                           _lower_idx, _upper_idx, ('clk', 'clk'))
                break
            except ValueError:
                continue
        assert vm_clk_num > 0, 'Redo routing'

        # right tap
        cur_col += sub_sep
        for idx in range(num_tiles):
            self.add_tap(cur_col, vdd_list[idx], vss_list[idx], tile_idx=idx, seg=seg_tap)
        sup_coords.append(self.grid.track_to_coord(self.conn_layer, cur_col + (tap_ncols >> 1)))

        self.set_mos_size()
        xh = self.bound_box.xh
        yh = self.bound_box.yh

        # --- Routing --- #
        # supplies
        vss_hm_list = [[] for _ in range(num_tiles)]
        vdd_hm_list = [[] for _ in range(num_tiles)]
        for inst in chain(ff_rst_list, inst0_list):
            vss_hm_list[0].append(inst.get_pin('VSS'))
            vdd_hm_list[0].append(inst.get_pin('VDD'))
        for inst in chain(ff_f_list, tinv_f_list, inst1_list):
            vss_hm_list[1].append(inst.get_pin('VSS'))
            vdd_hm_list[1].append(inst.get_pin('VDD'))
        for inst in chain(ff_s_list, tinv_s_list, [invs_1, invs_0]):
            vss_hm_list[2].append(inst.get_pin('VSS'))
            vdd_hm_list[2].append(inst.get_pin('VDD'))
        vss_hm, vdd_hm = [], []
        for idx in range(num_tiles):
            vss_hm.append(self.connect_to_track_wires(vss_list[idx], self.connect_wires(vss_hm_list[idx])[0]))
            vdd_hm.append(self.connect_to_track_wires(vdd_list[idx], self.connect_wires(vdd_hm_list[idx])[0]))
        vss_hm = self.connect_wires(vss_hm, lower=0, upper=xh)[0]
        vdd_hm = self.connect_wires(vdd_hm, lower=0, upper=xh)[0]
        vdd_dict, vss_dict = self.connect_supplies(vdd_hm, vss_hm, sup_coords, xh, yh)
        self.add_pin('VDD_ym', vdd_dict[ym_layer], hide=True)
        self.add_pin('VSS_ym', vss_dict[ym_layer], hide=True)

        # find xm_layer and xxm_layer tracks using supply tracks as reference
        xm_locs0 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'clk', 'clk', 'clk', 'sup'],
                                                lower=vss_dict[xm_layer][0].track_id.base_index,
                                                upper=vdd_dict[xm_layer][0].track_id.base_index, sp_type=('clk', 'clk'))
        xm_locs1 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'clk', 'clk', 'clk', 'sup'],
                                                lower=vdd_dict[xm_layer][0].track_id.base_index,
                                                upper=vss_dict[xm_layer][1].track_id.base_index, sp_type=('clk', 'clk'))
        xm_locs2 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'clk', 'clk', 'clk', 'sup'],
                                                lower=vss_dict[xm_layer][1].track_id.base_index,
                                                upper=vdd_dict[xm_layer][1].track_id.base_index, sp_type=('clk', 'clk'))
        xxm_locs0 = self.tr_manager.spread_wires(xxm_layer, ['sup', 'clk', 'sig', 'sig', 'clk', 'sup'],
                                                 lower=vss_dict[xxm_layer][0].track_id.base_index,
                                                 upper=vdd_dict[xxm_layer][0].track_id.base_index,
                                                 sp_type=('clk', 'clk'))
        xxm_locs1 = self.tr_manager.spread_wires(xxm_layer, ['sup', 'clk', 'sig', 'sig', 'clk', 'sup'],
                                                 lower=vdd_dict[xxm_layer][0].track_id.base_index,
                                                 upper=vss_dict[xxm_layer][1].track_id.base_index,
                                                 sp_type=('sig', 'sig'))

        # --- Clocks #
        w_clk_vm = self.tr_manager.get_width(vm_layer, 'clk')
        vm_clk_pitch = clk_vm_locs[1] - clk_vm_locs[0]
        w_clk_xm = self.tr_manager.get_width(xm_layer, 'clk')
        # clk -> clkb_buf in row 1
        clkb_vm = self.connect_to_tracks([invf_1.get_pin('pout'), invf_1.get_pin('nout')],
                                         TrackID(vm_layer, clk_vm_locs[2 * vm_clk_num], w_clk_vm, num=vm_clk_num,
                                                 pitch=2 * vm_clk_pitch))
        clkb_list0.append(clkb_vm)
        clkb_xm0 = self.connect_to_tracks(clkb_list0, TrackID(xm_layer, xm_locs0[-2], w_clk_xm))
        clkb_dict0 = self.connect_up(clkb_list0, clkb_xm0, xxm_locs0[-2], 'clk', MinLenMode.LOWER)
        clkb_list1.append(clkb_vm)
        clkb_xm1 = self.connect_to_tracks(clkb_list1, TrackID(xm_layer, xm_locs1[-2], w_clk_xm))
        clkb_dict1 = self.connect_up(clkb_list1, clkb_xm1, xxm_locs1[-2], 'clk', MinLenMode.LOWER)
        self.add_pin('clkb_buf', [clkb_dict0[xxm_layer], clkb_dict1[xxm_layer], clkb_xm0, clkb_xm1], mode=PinMode.LOWER)

        # clkb -> clk_buf in row 0
        clk_vm = self.connect_to_tracks([invf_0.get_pin('pout'), invf_0.get_pin('nout')],
                                        TrackID(vm_layer, clk_vm_locs[0], w_clk_vm, num=vm_clk_num,
                                                pitch=2 * vm_clk_pitch))
        clk_list0.append(clk_vm)
        clk_xm0 = self.connect_to_tracks(clk_list0, TrackID(xm_layer, xm_locs0[1], w_clk_xm))
        clk_dict0 = self.connect_up(clk_list0, clk_xm0, xxm_locs0[1], 'clk', MinLenMode.UPPER)
        clk_list1.append(clk_vm)
        clk_xm1 = self.connect_to_tracks(clk_list1, TrackID(xm_layer, xm_locs1[1], w_clk_xm))
        clk_dict1 = self.connect_up(clk_list1, clk_xm1, xxm_locs1[1], 'clk', MinLenMode.UPPER)
        self.add_pin('clk_buf', [clk_dict0[xxm_layer], clk_dict1[xxm_layer], clk_xm0, clk_xm1], mode=PinMode.LOWER)
        # hidden pins on clk ym_layer for top level routing
        for idx in range(ratio):
            self.add_pin(f'left_ym<{ratio - 1 - idx}>', clk_dict0[ym_layer][idx], hide=True)

        # clk in row 1
        clk_in_vm = self.connect_to_tracks(invf_1.get_pin('nin'), TrackID(vm_layer, clk_vm_locs[-1], w_clk_vm),
                                           min_len_mode=MinLenMode.MIDDLE)
        clk_in_xm = self.connect_to_tracks(clk_in_vm, TrackID(xm_layer, xm_locs1[2], w_clk_xm),
                                           min_len_mode=MinLenMode.UPPER)
        self.add_pin('clk', clk_in_xm)

        # clkb in row 0
        clkb_in_vm = self.connect_to_tracks(invf_0.get_pin('nin'), TrackID(vm_layer, clk_vm_locs[-1], w_clk_vm),
                                            min_len_mode=MinLenMode.MIDDLE)
        clkb_in_xm = self.connect_to_tracks(clkb_in_vm, TrackID(xm_layer, xm_locs0[-3], w_clk_xm),
                                            min_len_mode=MinLenMode.UPPER)
        self.add_pin('clkb', clkb_in_xm)

        # clk_divb_buf
        clk_divb_vm = self.connect_to_tracks([invs_0.get_pin('pout'), invs_0.get_pin('nout'), invs_1.get_pin('nin')],
                                             TrackID(vm_layer, clk_vm_locs[2 * vm_clk_num], w_clk_vm, num=vm_clk_num,
                                                     pitch=2 * vm_clk_pitch))
        clk_divb_list.append(clk_divb_vm)
        clk_divb_xm = self.connect_to_tracks(clk_divb_list, TrackID(xm_layer, xm_locs2[1], w_clk_xm))
        self.add_pin('clk_divb_buf', clk_divb_xm, hide=not export_nets, mode=PinMode.LOWER)

        # clk_div_buf
        clk_div_vm = self.connect_to_tracks([invs_1.get_pin('pout'), invs_1.get_pin('nout')],
                                            TrackID(vm_layer, clk_vm_locs[0], w_clk_vm, num=vm_clk_num,
                                                    pitch=2 * vm_clk_pitch))
        clk_div_list.append(clk_div_vm)
        clk_div_xm = self.connect_to_tracks(clk_div_list, TrackID(xm_layer, xm_locs2[-2], w_clk_xm))
        self.add_pin('clk_div_buf', clk_div_xm, mode=PinMode.LOWER)

        # clk_div
        clk_div_vm = self.connect_to_tracks(invs_0.get_pin('nin'), TrackID(vm_layer, clk_vm_locs[-1], w_clk_vm),
                                            min_len_mode=MinLenMode.MIDDLE)
        clk_div_xm = self.connect_to_tracks(clk_div_vm, TrackID(xm_layer, xm_locs2[-3], w_clk_xm),
                                            min_len_mode=MinLenMode.UPPER)
        self.add_pin('clk_div', [clk_div_vm, clk_div_xm])

        # connect p<0> to complete shift register
        p0_xm = self.connect_to_tracks(p0_list, TrackID(xm_layer, xm_locs0[2], w_clk_xm))
        self.connect_up(p0_list, p0_xm, xxm_locs0[2], 'sig', MinLenMode.UPPER)

        # p0_buf and p0b_buf
        en_xm0 = self.connect_to_tracks(en_list[-1], TrackID(xm_layer, xm_locs0[2], w_clk_xm),
                                        min_len_mode=MinLenMode.UPPER)
        en_xm1 = self.connect_to_tracks(en_list[:-1], TrackID(xm_layer, xm_locs1[2], w_clk_xm))
        en_dict = self.connect_up(en_list[:-1], en_xm1, xxm_locs1[2], 'sig', MinLenMode.UPPER)
        en_ym_tid = self.tr_manager.get_next_track_obj(clkb_dict1[ym_layer][_p0_ym_idx], 'sig', 'clk', 1)
        self.connect_to_tracks([en_xm0, en_xm1, en_dict[xxm_layer]], en_ym_tid)
        self.add_pin('p0_buf', en_dict[xxm_layer], hide=not export_nets, mode=PinMode.LOWER)

        enb_xm0 = self.connect_to_tracks(enb_list[-1], TrackID(xm_layer, xm_locs0[2], w_clk_xm),
                                         min_len_mode=MinLenMode.LOWER)
        enb_xm1 = self.connect_to_tracks(enb_list[:-1], TrackID(xm_layer, xm_locs1[-3], w_clk_xm))
        enb_dict = self.connect_up(enb_list[:-1], enb_xm1, xxm_locs1[-3], 'sig', MinLenMode.LOWER)
        enb_ym_tid = self.tr_manager.get_next_track_obj(clk_dict1[ym_layer][_p0_ym_idx], 'sig', 'clk', -1)
        self.connect_to_tracks([enb_xm0, enb_xm1, enb_dict[xxm_layer]], enb_ym_tid)
        # hidden pins on p0b_buf ym_layer for top level routing
        for idx in range(ratio - 1):
            self.add_pin(f'right_ym<{ratio - 2 - idx}>', enb_dict[ym_layer][idx], hide=True)
        self.add_pin(f'right_ym<{ratio - 1}>', clkb_dict0[ym_layer][1], hide=True)

        # reset
        self.connect_wires(rst_hm_list)
        rst_sync_xm = self.connect_to_tracks(rst_vm_list, TrackID(xm_layer, xm_locs0[-3], w_clk_xm))
        self.add_pin('rst_sync', rst_sync_xm, hide=not export_nets, mode=PinMode.LOWER)

        if is_rst_async:
            w_sig_ym = self.tr_manager.get_width(ym_layer, 'sig')
            rst_vm_tid = self.tr_manager.get_next_track_obj(rst_ff1_out, 'sig', 'sig', 1)
            rst_vm = self.connect_to_tracks([rst_ff0.get_pin('prst'), rst_ff1.get_pin('prst')], rst_vm_tid)
            rst_xm = self.connect_to_tracks(rst_vm, TrackID(xm_layer, xm_locs1[2], w_clk_xm),
                                            min_len_mode=MinLenMode.MIDDLE)
            rst_ym_tidx = self.grid.coord_to_track(ym_layer, rst_xm.middle, RoundMode.NEAREST)
            rst_ym = self.connect_to_tracks(rst_xm, TrackID(ym_layer, rst_ym_tidx, w_sig_ym),
                                            min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('rst', rst_ym)
        else:
            rstb_in = self.connect_to_tracks(rstb_in_vm, TrackID(xm_layer, xm_locs0[2], w_clk_xm),
                                             min_len_mode=MinLenMode.UPPER)
            self.add_pin('rstb_sync_in', rstb_in)

        # output
        dout = self.connect_to_tracks(dout_vm, TrackID(xm_layer, xm_locs1[-3], w_clk_xm), min_len_mode=MinLenMode.UPPER)
        self.add_pin('dout', dout)

        # inputs on xm_layer
        in_xm_tid = TrackID(xm_layer, xm_locs2[2], w_clk_xm)
        for idx, in_vm in enumerate(in_list):
            in_xm = self.connect_to_tracks(in_vm, in_xm_tid, min_len_mode=MinLenMode.MIDDLE)
            self.add_pin(f'din<{ratio - 1 - idx}>', in_xm)

        # get schematic parameters
        self.sch_params = dict(
            ff_rst=ff_rst_master.sch_params,
            ff_set=ff_set_master.sch_params,
            rst_sync=rst_sync_sch_params,
            inv_d=inv_d_sch,
            inv_en=inv_en_master.sch_params,
            ff=ff_master.sch_params,
            tinv=tinv_master.sch_params,
            inv_clk=inv_clk_master.sch_params,
            inv_clk_div=dict(inv_params=[inv_0_master.sch_params, inv_1_master.sch_params], dual_output=True),
            ratio=ratio,
            export_nets=export_nets,
            is_rst_async=is_rst_async,
        )

    def connect_supplies(self, vdd_hm: WireArray, vss_hm: WireArray, sup_coords: Sequence[int], xh: int, yh: int
                         ) -> Tuple[Mapping[int, Union[WireArray, Sequence[WireArray]]],
                                    Mapping[int, Union[WireArray, Sequence[WireArray]]]]:
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1
        ym_layer = xm_layer + 1
        xxm_layer = ym_layer + 1
        vdd_dict = {hm_layer: vdd_hm}
        vss_dict = {hm_layer: vss_hm}
        self.add_pin('VDD', vdd_hm)
        self.add_pin('VSS', vss_hm)

        for _vm, _hm in [(vm_layer, xm_layer), (ym_layer, xxm_layer)]:
            # connect to vertical layer
            w_vm_sup = self.tr_manager.get_width(_vm, 'sup')
            vss_vm_list, vdd_vm_list = [], []
            for _coord in sup_coords:
                _, _locs = self.tr_manager.place_wires(_vm, ['sup', 'sup'], center_coord=_coord)
                vss_tid = TrackID(_vm, _locs[0], w_vm_sup)
                vss_vm_list.append(self.connect_to_tracks(vss_hm, vss_tid, track_lower=0, track_upper=yh))
                vdd_tid = TrackID(_vm, _locs[-1], w_vm_sup)
                vdd_vm_list.append(self.connect_to_tracks(vdd_hm, vdd_tid, track_lower=0, track_upper=yh))
            vdd_dict[_vm] = vdd_vm_list
            vss_dict[_vm] = vss_vm_list

            # connect to horizontal layer
            w_hm_sup = self.tr_manager.get_width(_hm, 'sup')
            vss0_hm_idx = self.grid.coord_to_track(_hm, vss_hm[0].bound_box.ym, RoundMode.NEAREST)
            vss1_hm_idx = self.grid.coord_to_track(_hm, vss_hm[1].bound_box.ym, RoundMode.NEAREST)

            vdd0_hm_idx = self.grid.coord_to_track(_hm, vdd_hm[0].bound_box.ym, RoundMode.NEAREST)
            vdd1_hm_idx = self.grid.coord_to_track(_hm, vdd_hm[1].bound_box.ym, RoundMode.NEAREST)

            vss_hm = self.connect_to_tracks(vss_vm_list, TrackID(_hm, vss0_hm_idx, w_hm_sup, 2,
                                                                 vss1_hm_idx - vss0_hm_idx),
                                            track_lower=0, track_upper=xh)
            vdd_hm = self.connect_to_tracks(vdd_vm_list, TrackID(_hm, vdd0_hm_idx, w_hm_sup, 2,
                                                                 vdd1_hm_idx - vdd0_hm_idx),
                                            track_lower=0, track_upper=xh)
            vdd_dict[_hm] = vdd_hm
            vss_dict[_hm] = vss_hm
            self.add_pin('VDD', vdd_hm)
            self.add_pin('VSS', vss_hm)
        return vdd_dict, vss_dict

    def connect_up(self, warr_vm_list: Sequence[WireArray], warr_xm: WireArray, xxm_tidx: HalfInt, sig_type: str,
                   mlm_mode: MinLenMode) -> Mapping[int, Union[WireArray, Sequence[WireArray]]]:
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1
        ym_layer = xm_layer + 1
        xxm_layer = ym_layer + 1

        # connect to ym_layer
        w_ym = self.tr_manager.get_width(ym_layer, sig_type)
        warr_ym_list = []
        for _warr_vm in warr_vm_list:
            _tidx = self.grid.coord_to_track(ym_layer, _warr_vm.bound_box.xm, RoundMode.NEAREST)
            warr_ym_list.append(self.connect_to_tracks(warr_xm, TrackID(ym_layer, _tidx, w_ym), min_len_mode=mlm_mode))

        # connect to xxm_layer
        w_xxm = self.tr_manager.get_width(xxm_layer, sig_type)
        warr_xxm = self.connect_to_tracks(warr_ym_list, TrackID(xxm_layer, xxm_tidx, w_xxm))
        return {ym_layer: warr_ym_list, xxm_layer: warr_xxm}

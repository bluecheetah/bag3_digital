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
from ...schematic.serdes_generic import bag3_digital__serdes_generic


class SerDesGeneric(MOSBase):
    """
    2 rows of FF that can be used either as a serializer or deserializer.
    All that changes are whether the slow is an input to fast (ser) or fast is
    an input to slow (des).
    Control whether this is Ser or Des using the param flag 'is_ser'.
    This cell requires both clock and divided clock as inputs.
    """
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__serdes_generic

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_dict='Dictionary of segments',
            ratio='Number of serialized inputs/deserialized outputs',
            is_ser='True to make this a serializer. Otherwise, deserializer',
            horz_slow='True to have serialized inputs/deserialized outputs on horizontal layer',
            export_nets='True to export intermediate nets',
            tap_sep_flop='Horizontal separation between column taps in number of flops. Default is ratio // 2.'
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            is_ser=False,
            horz_slow=True,
            export_nets=False,
            tap_sep_flop=-1,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg_dict: Mapping[str, int] = self.params['seg_dict']
        ratio: int = self.params['ratio']
        is_ser: bool = self.params['is_ser']
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
        sup_coords = [self.grid.track_to_coord(self.conn_layer, tap_ncols >> 1)]

        # clock inverters
        cur_col = tap_ncols + sub_sep
        invf = self.add_tile(invf_master, 0, cur_col)
        invs = self.add_tile(invs_master, 1, cur_col)
        inv_list = [invf, invs]

        # flops
        cur_col += inv_ncols
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

            if is_ser:
                dslow = fs.get_pin('pin')
                # Bring up to vm_layer
                assert dslow.layer_id == hm_layer
                avail_vm_tid = self.tr_manager.get_next_track_obj(clk_div_vm, 'sig', 'sig', count_rel_tracks=1)
                dslow = self.connect_to_tracks(dslow, avail_vm_tid, min_len_mode=MinLenMode.MIDDLE)
            else:
                dslow = fs.get_pin('out')

            # check if dslow can be routed down to row 0 for connecting to xm_layer
            if horz_slow:
                avail_vm_idx = self.tr_manager.get_next_track(vm_layer, clk_vm.track_id.base_index, 'sig', 'sig', up=-1)
                if dslow.track_id.base_index > avail_vm_idx:
                    raise ValueError(f'dslow on vm_layer={vm_layer} cannot be routed down to row 0 for connecting to '
                                     f'xm_layer={xm_layer} because of collision / spacing error on vm_layer={vm_layer}')
                dslow_list.append(dslow)
            else:
                prefix = 'din' if is_ser else 'dout'
                self.add_pin(f'{prefix}<{idx}>', dslow)

            if is_ser:
                d_int = self.connect_to_track_wires(ff.get_pin('pin'), fs.get_pin('out'))
            else:
                d_int = self.connect_to_track_wires(fs.get_pin('pin'), ff.get_pin('out'))
            self.add_pin(f'd<{idx}>', d_int, hide=not export_nets)

            if not is_ser and idx == 0:
                self.reexport(ff.get_port('pin'), net_name='din', hide=False)
            elif is_ser and idx == ratio - 1:
                self.reexport(ff.get_port('out'), net_name='dout')
            if idx != 0:
                self.connect_wires([ff.get_pin('pin'), ff_list[-2].get_pin('pout')])

        # dout inverter, if it exists
        inv_sch_params = None
        w_vm_sig = self.tr_manager.get_width(vm_layer, 'sig')
        if is_ser:
            seg_inv = seg_dict.get('inv_data', 0)
            if seg_inv % 2:
                raise ValueError(f'Dout inverter must have even number of fingers. inv_data={seg_inv} has to be even.')
            if seg_inv > 0:
                # make master
                ff_out_hm = ff_list[-1].get_pin('pout')
                inv_params = dict(pinfo=pinfo, seg=seg_inv // 2, vertical_out=False,
                                  sig_locs={'pin': ff_out_hm.track_id.base_index})
                inv_master = self.new_template(InvCore, params=inv_params)
                inv_sch_params = dict(**inv_master.sch_params)
                inv_sch_params.update({'seg_p': seg_inv, 'seg_n': seg_inv})

                # place
                cur_col += blk_sp
                invd0 = self.add_tile(inv_master, 0, cur_col)
                invd1 = self.add_tile(inv_master, 1, cur_col)
                cur_col += inv_master.num_cols
                inv_list.extend([invd0, invd1])

                # local routing
                inv_in_hm = invd0.get_pin('pin')
                inv_in_vm_idx = self.grid.coord_to_track(vm_layer, inv_in_hm.lower, RoundMode.LESS_EQ)
                inv_in_vm = self.connect_to_tracks([ff_out_hm, inv_in_hm, invd1.get_pin('pin')],
                                                   TrackID(vm_layer, inv_in_vm_idx, w_vm_sig))
                inv_out_vm_tid = self.tr_manager.get_next_track_obj(inv_in_vm, 'sig', 'sig', count_rel_tracks=1)
                inv_out_vm = self.connect_to_tracks([invd0.get_pin('pout'), invd0.get_pin('nout'),
                                                     invd1.get_pin('pout'), invd1.get_pin('nout')], inv_out_vm_tid)
                self.add_pin('doutb', inv_out_vm)

        # right tap
        cur_col += sub_sep
        self.add_tap(cur_col, vdd_list, vss_list, tile_idx=0)
        self.add_tap(cur_col, vdd_list, vss_list, tile_idx=1)
        sup_coords.append(self.grid.track_to_coord(self.conn_layer, cur_col + (tap_ncols >> 1)))

        self.set_mos_size()
        xh = self.bound_box.xh

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
            vss_vm_list.append(self.connect_to_tracks(vss_hm, vss_tid, min_len_mode=MinLenMode.UPPER))
            vdd_tid = TrackID(vm_layer, _locs[-1], w_vm_sup)
            vdd_vm_list.append(self.connect_to_tracks(vdd_hm, vdd_tid, track_lower=vss_vm_list[-1].lower,
                                                      track_upper=vss_vm_list[-1].upper))

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

        # clkb
        clkb_pout = invf.get_pin('pout')
        clkb_nout = invf.get_pin('nout')
        clkb_vm_idx = self.grid.coord_to_track(vm_layer, clkb_pout.upper, RoundMode.NEAREST)
        w_vm_clk = self.tr_manager.get_width(vm_layer, 'clk')
        clkb_vm = TrackID(vm_layer, clkb_vm_idx, w_vm_clk)
        clkb_vm = self.connect_to_tracks([clkb_pout, clkb_nout], clkb_vm)
        clkb_list.append(clkb_vm)
        w_xm_clk = self.tr_manager.get_width(xm_layer, 'clk')
        clkb_xm = self.connect_to_tracks(clkb_list, TrackID(xm_layer, xm_locs0[1], w_xm_clk))
        self.add_pin('clkb', [clkb_vm, clkb_xm], hide=not export_nets)

        # clk
        clk_vm = self.tr_manager.get_next_track_obj(clkb_vm, 'clk', 'clk', -1)
        clk_vm = self.connect_to_tracks(invf.get_pin('in'), clk_vm)
        clk_list.append(clk_vm)
        clk_xm = self.connect_to_tracks(clk_list, TrackID(xm_layer, xm_locs0[-2], w_xm_clk))
        self.add_pin('clk', [clk_vm, clk_xm])

        # clk_divb
        clk_divb_pout = invs.get_pin('pout')
        clk_divb_nout = invs.get_pin('nout')
        clk_divb_vm_idx = self.grid.coord_to_track(vm_layer, clk_divb_pout.upper, RoundMode.NEAREST)
        clk_divb_vm = TrackID(vm_layer, clk_divb_vm_idx, w_vm_clk)
        clk_divb_vm = self.connect_to_tracks([clk_divb_pout, clk_divb_nout], clk_divb_vm)
        clk_divb_list.append(clk_divb_vm)
        clk_divb_xm = self.connect_to_tracks(clk_divb_list, TrackID(xm_layer, xm_locs1[-2], w_xm_clk))
        self.add_pin('clk_divb', [clk_divb_vm, clk_divb_xm], hide=not export_nets)

        # clk_div
        clk_div_vm = self.tr_manager.get_next_track_obj(clk_divb_vm, 'clk', 'clk', -1)
        clk_div_vm = self.connect_to_tracks(invs.get_pin('in'), clk_div_vm)
        clk_div_list.append(clk_div_vm)
        clk_div_xm = self.connect_to_tracks(clk_div_list, TrackID(xm_layer, xm_locs1[1], w_xm_clk))
        self.add_pin('clk_div', [clk_div_vm, clk_div_xm])

        # get schematic parameters
        self.sch_params = dict(
            flop_fast=ff_master.sch_params,
            flop_slow=fs_master.sch_params,
            inv_fast=invf_master.sch_params,
            inv_slow=invs_master.sch_params,
            ratio=ratio,
            export_nets=export_nets,
            is_ser=is_ser,
            inv_data=inv_sch_params,
        )

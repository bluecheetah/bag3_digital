from typing import Any, Optional, Mapping, Type

from pybag.enum import MinLenMode, PinMode, RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.enum import MOSWireType

from ..stdcells.gates import InvTristateCore, InvCore
from ..stdcells.memory import FlopCore
from .serNto1_fast import SerNto1Fast
from ...schematic.ser2Nto1_fast import bag3_digital__ser2Nto1_fast


class Ser2Nto1Fast(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__ser2Nto1_fast

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            ridx_p='pch row index',
            ridx_n='nch row index',
            seg_dict='Dictionary of segments',
            ratio='Number of serialized inputs for each serNto1',
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
        seg_dict: Mapping[str, Any] = self.params['seg_dict']
        ratio: int = self.params['ratio']
        export_nets: bool = self.params['export_nets']
        tap_sep_flop: int = self.params['tap_sep_flop']

        # make masters
        ser_params = dict(pinfo=pinfo, seg_dict=seg_dict['ser'], ridx_p=ridx_p, ridx_n=ridx_n, ratio=ratio,
                          tap_sep_flop=tap_sep_flop, is_rst_async=False)
        ser_master = self.new_template(SerNto1Fast, params=ser_params)
        ser_ncols = ser_master.num_cols
        ser_ntiles = ser_master.num_tile_rows

        ff_rst_params = dict(pinfo=pinfo, seg=seg_dict['ff'], resetable=True, rst_type='RESET')
        ff_rst_master = self.new_template(FlopCore, params=ff_rst_params)
        ff_rst_ncols = ff_rst_master.num_cols

        tinv_params = dict(pinfo=pinfo, seg=seg_dict['tinv'], vertical_out=False)
        tinv_master = self.new_template(InvTristateCore, params=tinv_params)
        tinv_ncols = tinv_master.num_cols

        seg_inv = seg_dict['inv']
        assert seg_inv & 1 == 0, f'seg_dict["inv"] = {seg_inv} must be even'
        pg_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -2)
        inv_params = dict(pinfo=pinfo, seg=seg_inv // 2, vertical_out=False, sig_locs={'nin': pg_tidx})
        inv_master = self.new_template(InvCore, params=inv_params)
        inv_sch_params = dict(**inv_master.sch_params)
        inv_sch_params['seg_p'] = inv_sch_params['seg_n'] = seg_inv

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1
        ym_layer = xm_layer + 1
        xxm_layer = ym_layer + 1

        # --- Placement --- #
        cur_col = 0
        ser0 = self.add_tile(ser_master, 0, cur_col)
        ser1 = self.add_tile(ser_master, 2 * ser_ntiles - 1, cur_col)

        cur_col += ser_ncols + self.sub_sep_col
        rst_ff0 = self.add_tile(ff_rst_master, ser_ntiles - 1, cur_col + ff_rst_ncols, flip_lr=True)
        # extra blk_sp so that rst_ff1 output on vm_layer can go down to rst_ff0 input
        cur_col += ff_rst_ncols + self.min_sep_col
        rst_ff1 = self.add_tile(ff_rst_master, ser_ntiles, cur_col - ff_rst_ncols)

        tinv0 = self.add_tile(tinv_master, ser_ntiles - 2, cur_col - tinv_ncols)
        tinv1 = self.add_tile(tinv_master, ser_ntiles + 1, cur_col - tinv_ncols)

        cur_col += self.min_sep_col
        inv0 = self.add_tile(inv_master, ser_ntiles - 1, cur_col)
        inv1 = self.add_tile(inv_master, ser_ntiles, cur_col)
        inst_list = [ser0, ser1, tinv0, tinv1, rst_ff0, rst_ff1, inv0, inv1]

        self.set_mos_size()

        # --- Routing --- #
        # supplies
        vdd_hm_list, vss_hm_list = [], []
        lower = 0
        upper = self.bound_box.xh
        for inst in inst_list:
            vdd_hm_list.append(inst.get_pin('VDD', layer=hm_layer))
            vss_hm_list.append(inst.get_pin('VSS', layer=hm_layer))
            lower = min(lower, vdd_hm_list[0].lower, vss_hm_list[-1].lower)
            upper = max(upper, vdd_hm_list[0].upper, vss_hm_list[-1].upper)
        vdd_hm = self.connect_wires(vdd_hm_list, lower=lower, upper=upper)[0]
        vss_hm = self.connect_wires(vss_hm_list, lower=lower, upper=upper)[0]
        vdd_xm = self.connect_wires([ser0.get_pin('VDD', layer=xm_layer), ser1.get_pin('VDD', layer=xm_layer)],
                                    lower=lower, upper=upper)[0]
        vdd_xxm = self.connect_wires([ser0.get_pin('VDD', layer=xxm_layer), ser1.get_pin('VDD', layer=xxm_layer)],
                                     lower=lower, upper=upper)[0]
        vss_xm = self.connect_wires([ser0.get_pin('VSS', layer=xm_layer), ser1.get_pin('VSS', layer=xm_layer)],
                                    lower=lower, upper=upper)[0]
        vss_xxm = self.connect_wires([ser0.get_pin('VSS', layer=xxm_layer), ser1.get_pin('VSS', layer=xxm_layer)],
                                     lower=lower, upper=upper)[0]
        self.add_pin('VDD', [vdd_hm, vdd_xm, vdd_xxm])
        self.add_pin('VSS', [vss_hm, vss_xm, vss_xxm])
        vdd_ym = self.connect_wires(ser0.get_all_port_pins('VDD_ym') + ser1.get_all_port_pins('VDD_ym'))
        vss_ym = self.connect_wires(ser0.get_all_port_pins('VSS_ym') + ser1.get_all_port_pins('VSS_ym'))
        self.add_pin('VDD_ym', vdd_ym, hide=True)
        self.add_pin('VSS_ym', vss_ym, hide=True)

        _tidx = self.grid.coord_to_track(vm_layer, self.bound_box.xh, RoundMode.NEAREST)
        _, vm_locs = self.tr_manager.place_wires(vm_layer, ['clk', 'clk', 'clk', 'clk', 'clk'], _tidx, -1)

        # dout
        inv0_pout = inv0.get_pin('pout')
        w_clk_vm = self.tr_manager.get_width(vm_layer, 'clk')
        dout_vm = self.connect_to_tracks([inv0_pout, inv0.get_pin('nout'), inv1.get_pin('pout'),
                                          inv1.get_pin('nout')], TrackID(vm_layer, vm_locs[-1], w_clk_vm))
        self.add_pin('dout', dout_vm)

        # doutb
        doutb_hm_list = [tinv0.get_pin('pout'), tinv0.get_pin('nout'), tinv1.get_pin('pout'), tinv1.get_pin('nout'),
                         inv0.get_pin('nin'), inv1.get_pin('nin')]
        self.connect_to_tracks(doutb_hm_list, TrackID(vm_layer, vm_locs[-2], w_clk_vm))

        # dout<0> and dout<1>
        in_vm_tid = TrackID(vm_layer, vm_locs[0], w_clk_vm)
        dout0_vm = self.connect_to_tracks(tinv0.get_pin('nin'), in_vm_tid, min_len_mode=MinLenMode.MIDDLE)
        dout0_xm = self.connect_to_track_wires(dout0_vm, ser0.get_pin('dout'))
        self.add_pin('ser_out<0>', dout0_xm, hide=not export_nets, mode=PinMode.UPPER)

        dout1_vm = self.connect_to_tracks(tinv1.get_pin('nin'), in_vm_tid, min_len_mode=MinLenMode.MIDDLE)
        dout1_xm = self.connect_to_track_wires(dout1_vm, ser1.get_pin('dout'))
        self.add_pin('ser_out<1>', dout1_xm, hide=not export_nets, mode=PinMode.UPPER)

        # rstb_sync
        rstb_sync = self.connect_to_track_wires([ser0.get_pin('rstb_sync_in'), ser1.get_pin('rstb_sync_in')],
                                                rst_ff0.get_pin('out'))
        self.add_pin('rstb_sync', rstb_sync, hide=not export_nets)

        # rst_ff1 output to rst_ff0 input
        rst_ff1_out = rst_ff1.get_pin('out')
        self.connect_to_track_wires(rst_ff0.get_pin('nin'), rst_ff1_out)

        # get xm_layer tracks
        xm_locs0 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'clk', 'clk', 'clk', 'sup'],
                                                lower=vdd_xm[0].track_id.base_index,
                                                upper=vss_xm[1].track_id.base_index, sp_type=('clk', 'clk'))
        xm_locs1 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'sig', 'clk', 'clk', 'sup'],
                                                lower=vss_xm[1].track_id.base_index,
                                                upper=vdd_xm[1].track_id.base_index, sp_type=('clk', 'clk'))
        xm_locs2 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'clk', 'sig', 'clk', 'sup'],
                                                lower=vdd_xm[1].track_id.base_index,
                                                upper=vss_xm[2].track_id.base_index, sp_type=('clk', 'clk'))
        xm_locs3 = self.tr_manager.spread_wires(xm_layer, ['sup', 'clk', 'clk', 'clk', 'clk', 'sup'],
                                                lower=vss_xm[2].track_id.base_index,
                                                upper=vdd_xm[2].track_id.base_index, sp_type=('clk', 'clk'))

        # rst
        rst_vm_tid = self.tr_manager.get_next_track_obj(rst_ff1_out, 'sig', 'sig', 1)
        rst_vm = self.connect_to_tracks([rst_ff0.get_pin('prst'), rst_ff1.get_pin('prst')], rst_vm_tid)
        rst_ym = self.connect_via_stack(self.tr_manager, rst_vm, ym_layer,
                                        coord_list_o_override=[self.grid.track_to_coord(xm_layer, xm_locs1[2]),
                                                               self.grid.track_to_coord(xm_layer, xm_locs2[-3])])
        self.add_pin('rst', rst_ym, mode=PinMode.LOWER)

        # clk and clkb from reset synchronizer flops
        w_clk_xm = self.tr_manager.get_width(xm_layer, 'clk')
        rst0_clk = self.connect_to_tracks(rst_ff0.get_pin('clk'), TrackID(xm_layer, xm_locs1[-2], w_clk_xm),
                                          min_len_mode=MinLenMode.MIDDLE)
        rst0_clkb = self.connect_to_tracks(rst_ff0.get_pin('clkb'), TrackID(xm_layer, xm_locs1[1], w_clk_xm),
                                           min_len_mode=MinLenMode.MIDDLE)
        rst1_clk = self.connect_to_tracks(rst_ff1.get_pin('clk'), TrackID(xm_layer, xm_locs2[1], w_clk_xm),
                                          min_len_mode=MinLenMode.MIDDLE)
        rst1_clkb_vm = rst_ff1.get_pin('clkb')
        rst1_clkb = self.connect_to_tracks(rst1_clkb_vm, TrackID(xm_layer, xm_locs2[-2], w_clk_xm),
                                           min_len_mode=MinLenMode.MIDDLE)

        # input of rst_ff1
        _in_vm_tid = self.tr_manager.get_next_track_obj(rst1_clkb_vm, 'sig', 'sig', -1)
        self.connect_to_tracks([rst_ff1.get_pin('nin'), rst_ff1.get_pin('VDD')], _in_vm_tid)

        # clk and clkb from tristate inverters
        tinv0_clk_vm = self.connect_to_tracks(tinv0.get_pin('enb'), TrackID(vm_layer, vm_locs[1], w_clk_vm),
                                              min_len_mode=MinLenMode.MIDDLE)
        tinv0_clk = self.connect_to_tracks(tinv0_clk_vm, TrackID(xm_layer, xm_locs0[1], w_clk_xm),
                                           min_len_mode=MinLenMode.MIDDLE)
        tinv0_clkb_vm = self.connect_to_tracks(tinv0.get_pin('en'), TrackID(vm_layer, vm_locs[2], w_clk_vm),
                                               min_len_mode=MinLenMode.MIDDLE)
        tinv0_clkb = self.connect_to_tracks(tinv0_clkb_vm, TrackID(xm_layer, xm_locs0[-2], w_clk_xm),
                                            min_len_mode=MinLenMode.MIDDLE)

        tinv1_clk_vm = self.connect_to_tracks(tinv1.get_pin('en'), TrackID(vm_layer, vm_locs[1], w_clk_vm),
                                              min_len_mode=MinLenMode.MIDDLE)
        tinv1_clk = self.connect_to_tracks(tinv1_clk_vm, TrackID(xm_layer, xm_locs3[1], w_clk_xm),
                                           min_len_mode=MinLenMode.MIDDLE)
        tinv1_clkb_vm = self.connect_to_tracks(tinv1.get_pin('enb'), TrackID(vm_layer, vm_locs[2], w_clk_vm),
                                               min_len_mode=MinLenMode.MIDDLE)
        tinv1_clkb = self.connect_to_tracks(tinv1_clkb_vm, TrackID(xm_layer, xm_locs3[-2], w_clk_xm),
                                            min_len_mode=MinLenMode.MIDDLE)

        clk_list = [ser0.get_pin('clk'), rst0_clk, rst1_clk, tinv0_clk, tinv1_clk]
        clkb_list = [ser1.get_pin('clk'), rst0_clkb, rst1_clkb, tinv0_clkb, tinv1_clkb]

        # get ym_layer tracks
        _, ym_locs = self.tr_manager.place_wires(ym_layer, ['clk', 'clk', 'sig'], rst_ym.track_id.base_index, -1)
        w_clk_ym = self.tr_manager.get_width(ym_layer, 'clk')

        # clk and clkb
        clk = self.connect_to_tracks(clk_list, TrackID(ym_layer, ym_locs[0], w_clk_ym))
        self.add_pin('clk', clk, mode=PinMode.LOWER)
        self.reexport(ser0.get_port('clk'))
        clkb = self.connect_to_tracks(clkb_list, TrackID(ym_layer, ym_locs[1], w_clk_ym))
        self.add_pin('clkb', clkb, mode=PinMode.LOWER)
        self.reexport(ser1.get_port('clk'), net_name='clkb')

        # clk_div
        self.connect_wires([ser0.get_pin('clk_div', layer=vm_layer), ser1.get_pin('clk_div', layer=vm_layer)])
        clk_div_xm = self.connect_wires([ser0.get_pin('clk_div', layer=xm_layer),
                                         ser1.get_pin('clk_div', layer=xm_layer)])[0]
        _ym_tid = self.tr_manager.get_next_track_obj(vss_ym[-1][-1], 'sup', 'clk', -1)
        clk_div = self.connect_to_tracks(clk_div_xm, _ym_tid)
        self.add_pin('clk_div', clk_div_xm)
        self.add_pin('clk_div', clk_div, mode=PinMode.LOWER)

        # clk_div_buf from XSER1
        self.reexport(ser1.get_port('clk_div_buf'))

        # reexport wires on ym_layer for top level routing
        for idx in range(ratio):
            self.reexport(ser0.get_port(f'left_ym<{idx}>'))
            self.reexport(ser0.get_port(f'right_ym<{idx}>'))

        # inputs
        for idx in range(ratio):
            self.reexport(ser0.get_port(f'din<{idx}>'), net_name=f'din<{2 * idx}>')
            self.reexport(ser1.get_port(f'din<{idx}>'), net_name=f'din<{2 * idx + 1}>')

        # get schematic parameters
        self.sch_params = dict(
            ser=ser_master.sch_params,
            rst_sync=dict(ff=ff_rst_master.sch_params),
            tinv=tinv_master.sch_params,
            inv=inv_sch_params,
            export_nets=export_nets,
        )

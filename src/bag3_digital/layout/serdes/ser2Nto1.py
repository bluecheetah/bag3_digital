from typing import Any, Optional, Mapping, Type

from pybag.enum import MinLenMode, PinMode, RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.enum import MOSWireType

from ..stdcells.gates import InvTristateCore, InvCore
from .serNto1 import SerNto1
from ...schematic.ser2Nto1 import bag3_digital__ser2Nto1


class Ser2Nto1(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__ser2Nto1

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
        seg_dict: Mapping[str, int] = self.params['seg_dict']
        ratio: int = self.params['ratio']
        export_nets: bool = self.params['export_nets']
        tap_sep_flop: int = self.params['tap_sep_flop']

        # make masters
        ser_params = dict(pinfo=pinfo, seg_dict=seg_dict['ser'], ridx_p=ridx_p, ridx_n=ridx_n, ratio=ratio,
                          tap_sep_flop=tap_sep_flop)
        ser_master = self.new_template(SerNto1, params=ser_params)
        ser_ncols = ser_master.num_cols
        ser_ntiles = ser_master.num_tile_rows

        tinv_params = dict(pinfo=pinfo, seg=seg_dict['tinv'], vertical_out=False)
        tinv_master = self.new_template(InvTristateCore, params=tinv_params)
        tinv_ncols = tinv_master.num_cols

        seg_inv = seg_dict.get('inv', 0)
        if seg_inv > 0:
            assert seg_inv & 1 == 0, f'seg_dict["inv"] = {seg_inv} must be even'
            pg_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -2)
            inv_params = dict(pinfo=pinfo, seg=seg_inv // 2, vertical_out=False, sig_locs={'nin': pg_tidx})
            inv_master = self.new_template(InvCore, params=inv_params)
            inv_sch_params = dict(**inv_master.sch_params)
            inv_sch_params['seg_p'] = inv_sch_params['seg_n'] = seg_inv
        else:
            inv_master = None
            inv_sch_params = None

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1
        w_clk_vm = self.tr_manager.get_width(vm_layer, 'clk')

        # --- Placement --- #
        cur_col = 0
        ser0 = self.add_tile(ser_master, 0, cur_col)
        ser1 = self.add_tile(ser_master, 2 * ser_ntiles - 1, cur_col)

        cur_col += ser_ncols + self.sub_sep_col
        tinv0 = self.add_tile(tinv_master, ser_ntiles - 1, cur_col)
        tinv1 = self.add_tile(tinv_master, ser_ntiles, cur_col)
        _, vm_locs = self.tr_manager.place_wires(vm_layer, ['clk', 'clk', 'clk', 'clk'],
                                                 center_coord=(cur_col + tinv_ncols // 2) * self.sd_pitch)
        inst_list = [ser0, ser1, tinv0, tinv1]

        dout_hm_list = [tinv0.get_pin('pout'), tinv0.get_pin('nout'), tinv1.get_pin('pout'), tinv1.get_pin('nout')]

        if seg_inv > 0:
            cur_col += tinv_ncols + self.min_sep_col
            inv0 = self.add_tile(inv_master, ser_ntiles - 1, cur_col)
            inv1 = self.add_tile(inv_master, ser_ntiles, cur_col)
            inst_list.extend([inv0, inv1])

            # doutb
            inv0_pout = inv0.get_pin('pout')
            doutb_vm_tidx = self.grid.coord_to_track(vm_layer, inv0_pout.upper, RoundMode.NEAREST)
            doutb_vm = self.connect_to_tracks([inv0_pout, inv0.get_pin('nout'), inv1.get_pin('pout'),
                                               inv1.get_pin('nout')], TrackID(vm_layer, doutb_vm_tidx, w_clk_vm))
            self.add_pin('doutb', doutb_vm)

            dout_hm_list.extend([inv0.get_pin('nin'), inv1.get_pin('nin')])

        self.set_mos_size()

        # --- Routing --- #
        # supplies
        vdd_hm_list, vss_hm_list = [], []
        lower = 0
        upper = self.bound_box.xh
        for inst in inst_list:
            vdd_hm_list.append(inst.get_pin('VDD', layer=hm_layer))
            vss_hm_list.append(inst.get_pin('VSS', layer=hm_layer))
            lower = min(lower, vdd_hm_list[-1].lower, vss_hm_list[-1].lower)
            upper = max(upper, vdd_hm_list[-1].upper, vss_hm_list[-1].upper)
        vdd_hm = self.connect_wires(vdd_hm_list, lower=lower, upper=upper)[0]
        vss_hm = self.connect_wires(vss_hm_list, lower=lower, upper=upper)[0]
        vdd_xm = self.connect_wires([ser0.get_pin('VDD', layer=xm_layer), ser1.get_pin('VDD', layer=xm_layer)],
                                    lower=lower, upper=upper)[0]
        vss_xm = self.connect_wires([ser0.get_pin('VSS', layer=xm_layer), ser1.get_pin('VSS', layer=xm_layer)],
                                    lower=lower, upper=upper)[0]
        self.add_pin('VDD', [vdd_hm, vdd_xm])
        self.add_pin('VSS', [vss_hm, vss_xm])
        vdd_vm = ser0.get_all_port_pins('VDD_vm') + ser1.get_all_port_pins('VDD_vm')
        vss_vm = ser0.get_all_port_pins('VSS_vm') + ser1.get_all_port_pins('VSS_vm')
        self.add_pin('VDD_vm', vdd_vm, hide=True)
        self.add_pin('VSS_vm', vss_vm, hide=True)

        # doutb<0> and doutb<1>
        in_vm_tid = TrackID(vm_layer, vm_locs[0], w_clk_vm)
        doutb0_vm = self.connect_to_tracks(tinv0.get_pin('nin'), in_vm_tid, min_len_mode=MinLenMode.MIDDLE)
        doutb0_xm = self.connect_to_track_wires(doutb0_vm, ser0.get_pin('doutb'))
        self.add_pin('ser_outb<0>', doutb0_xm, hide=not export_nets, mode=PinMode.UPPER)

        doutb1_vm = self.connect_to_tracks(tinv1.get_pin('nin'), in_vm_tid, min_len_mode=MinLenMode.MIDDLE)
        doutb1_xm = self.connect_to_track_wires(doutb1_vm, ser1.get_pin('doutb'))
        self.add_pin('ser_outb<1>', doutb1_xm, hide=not export_nets, mode=PinMode.UPPER)

        # dout
        dout_vm = self.connect_to_tracks(dout_hm_list, TrackID(vm_layer, vm_locs[-1], w_clk_vm))
        self.add_pin('dout', dout_vm)

        # clk and clkb
        clk_vm = self.connect_to_tracks([tinv0.get_pin('enb'), tinv1.get_pin('en')],
                                        TrackID(vm_layer, vm_locs[1], w_clk_vm))
        clk_xm = self.connect_to_track_wires(clk_vm, ser0.get_pin('clk'))
        self.add_pin('clk', clk_xm, mode=PinMode.UPPER)

        clkb_vm = self.connect_to_tracks([tinv0.get_pin('en'), tinv1.get_pin('enb')],
                                         TrackID(vm_layer, vm_locs[-2], w_clk_vm))
        clkb_xm = self.connect_to_track_wires(clkb_vm, ser1.get_pin('clk'))
        self.add_pin('clkb', clkb_xm, mode=PinMode.UPPER)

        # clk_div
        self.connect_wires([ser0.get_pin('clk_div', layer=vm_layer), ser1.get_pin('clk_div', layer=vm_layer)])
        clk_div_xm = self.connect_wires([ser0.get_pin('clk_div', layer=xm_layer),
                                         ser1.get_pin('clk_div', layer=xm_layer)])[0]
        self.add_pin('clk_div', clk_div_xm, mode=PinMode.LOWER)

        # rst
        rst = self.connect_wires([ser0.get_pin('rst'), ser1.get_pin('rst')])[0]
        self.add_pin('rst', rst, mode=PinMode.LOWER)

        # inputs
        for idx in range(ratio):
            self.reexport(ser0.get_port(f'din<{idx}>'), net_name=f'din<{2 * idx}>')
            self.reexport(ser1.get_port(f'din<{idx}>'), net_name=f'din<{2 * idx + 1}>')

        # get schematic parameters
        self.sch_params = dict(
            ser=ser_master.sch_params,
            tinv=tinv_master.sch_params,
            inv=inv_sch_params,
            export_nets=export_nets,
        )

from typing import Any, Mapping, Optional, Type

from pybag.enum import RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .latch_diff import LatchDiffCore
from ...schematic.flop_diff import bag3_digital__flop_diff


class FlopDiffCore(MOSBase):
    """Differential latch using tristate inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__flop_diff

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg='number of segments of output inverter.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Signal track location dictionary.',
            fanout_in='input stage fanout.',
            fanout_kp='keeper stage fanout.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            sig_locs=None,
            fanout_in=4,
            fanout_kp=8,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        sig_locs: Optional[Mapping[str, float]] = self.params['sig_locs']
        if sig_locs is None:
            sig_locs = {}

        # --- make masters --- #
        latch_master = self.new_template(LatchDiffCore, params=self.params)
        latch_ncols = latch_master.num_cols

        # --- Placement --- #
        cur_col = 0
        latch0 = self.add_tile(latch_master, 0, cur_col)

        cur_col += latch_ncols + self.min_sep_col
        latch1 = self.add_tile(latch_master, 0, cur_col)

        self.set_mos_size()

        # --- Routing --- #
        # supplies
        vss_list, vdd_list = [], []
        for inst in (latch0, latch1):
            vss_list.extend(inst.get_all_port_pins('VSS'))
            vdd_list.extend(inst.get_all_port_pins('VDD'))
        self.add_pin('VDD', self.connect_wires(vdd_list)[0])
        self.add_pin('VSS', self.connect_wires(vss_list)[0])

        # inputs
        self.reexport(latch0.get_port('in'))
        self.reexport(latch0.get_port('inb'))

        # outputs
        self.reexport(latch1.get_port('out'))
        self.reexport(latch1.get_port('outb'))

        # middle nodes
        self.connect_to_track_wires(latch1.get_pin('nin'), latch0.get_pin('out'))
        self.connect_to_track_wires(latch1.get_pin('ninb'), latch0.get_pin('outb'))

        # clocks on xm_layer
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1
        clk_vm = latch1.get_pin('clk')
        clk_xm_tidx = sig_locs.get('clk_xm', self.grid.coord_to_track(xm_layer, clk_vm.lower, RoundMode.NEAREST))
        clkb_xm_tidx = sig_locs.get('clkb_xm', self.grid.coord_to_track(xm_layer, clk_vm.upper, RoundMode.NEAREST))
        w_clk_xm = self.tr_manager.get_width(xm_layer, 'clk')
        clk_xm = self.connect_to_tracks([latch0.get_pin('clkb'), latch1.get_pin('clk')],
                                        TrackID(xm_layer, clk_xm_tidx, w_clk_xm))
        self.add_pin('clk', clk_xm)
        clkb_xm = self.connect_to_tracks([latch0.get_pin('clk'), latch1.get_pin('clkb')],
                                         TrackID(xm_layer, clkb_xm_tidx, w_clk_xm))
        self.add_pin('clkb', clkb_xm)

        # get schematic parameters
        self.sch_params = dict(
            latch=latch_master.sch_params,
        )

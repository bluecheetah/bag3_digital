from typing import Any, Optional, Mapping, Type

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.enum import MOSWireType

from ..stdcells.gates import InvChainCore
from ..stdcells.memory import FlopCore
from ...schematic.reset_sync import bag3_digital__reset_sync


class ResetSync(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__reset_sync

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            ridx_p='pch row index',
            ridx_n='nch row index',
            seg_dict='Dictionary of segments',
            reset_priority='"high" or "low"; "high" by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            ridx_p=-1,
            ridx_n=0,
            reset_priority='high',
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        seg_dict: Mapping[str, int] = self.params['seg_dict']
        reset_priority: str = self.params['reset_priority']

        # make masters
        ff_rst_params = dict(pinfo=pinfo, seg=seg_dict['ff'], resetable=True)
        ff_rst_master = self.new_template(FlopCore, params=ff_rst_params)
        ff_rst_ncols = ff_rst_master.num_cols

        pg0_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -3)
        ng_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 1)
        buf_params = dict(pinfo=pinfo, seg_list=seg_dict['buf'], dual_output=True,
                          sig_locs={'nin0': pg0_tidx, 'nin1': ng_tidx})
        buf_master = self.new_template(InvChainCore, params=buf_params)

        # --- Placement --- #
        cur_col = 0
        ff0 = self.add_tile(ff_rst_master, 0, cur_col)

        cur_col += ff_rst_ncols + self.min_sep_col
        ff1 = self.add_tile(ff_rst_master, 0, cur_col)

        cur_col += ff_rst_ncols + self.min_sep_col
        buf = self.add_tile(buf_master, 0, cur_col)

        self.set_mos_size()

        # --- Routing --- #
        # supplies
        vdd_hm = self.connect_wires([ff0.get_pin('VDD'), ff1.get_pin('VDD'), buf.get_pin('VDD')])[0]
        self.add_pin('VDD', vdd_hm)
        vss_hm = self.connect_wires([ff0.get_pin('VSS'), ff1.get_pin('VSS'), buf.get_pin('VSS')])[0]
        self.add_pin('VSS', vss_hm)

        # din
        if reset_priority == 'high':
            clk_vm = ff0.get_pin('clk')
            in_vm_tid = self.tr_manager.get_next_track_obj(clk_vm, 'clk', 'sig', -1)
            self.connect_to_tracks([ff0.get_pin('nin'), vdd_hm], in_vm_tid)
        elif reset_priority == 'low':
            self.reexport(ff0.get_port('nin'), net_name='din', hide=False)
        else:
            raise ValueError(f'Unknown reset_priority={reset_priority}. Use "high" or "low".')

        # dint
        self.connect_to_track_wires(ff1.get_pin('nin'), ff0.get_pin('out'))

        # internal rstb
        self.connect_to_track_wires(buf.get_pin('in'), ff1.get_pin('out'))

        # rst_async
        rst = self.connect_wires([ff0.get_pin('prst'), ff1.get_pin('prst')])[0]
        self.add_pin('rst_async', rst)

        # outputs
        self.reexport(buf.get_port('out'), net_name='rstb_sync')
        self.reexport(buf.get_port('outb'), net_name='rst_sync')

        # clocks
        for inst in (ff0, ff1):
            for pin_name in ('clk', 'clkb'):
                self.reexport(inst.get_port(pin_name), connect=True)

        # set schematic parameters
        self.sch_params = dict(
            ff=ff_rst_master.sch_params,
            buf=buf_master.sch_params,
            reset_priority=reset_priority,
        )

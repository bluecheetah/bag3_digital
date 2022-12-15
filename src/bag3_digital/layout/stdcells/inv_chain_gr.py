from typing import Any, Dict, Optional, Mapping, Type, List

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import WireArray
from bag.layout.enum import DrawTaps

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase
from xbase.layout.mos.guardring import GuardRing
from xbase.layout.enum import MOSWireType

from ...schematic.inv_chain import bag3_digital__inv_chain
from .gates import InvChainCore


class InvChainCoreWithTaps(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        ans = InvChainCore.get_params_info()
        ans.update(
            draw_taps='LEFT or RIGHT or BOTH or NONE',
        )
        return ans

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        ans = InvChainCore.get_default_param_values()
        ans.update(
            draw_taps='NONE',
        )
        return ans

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_chain

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        draw_taps: DrawTaps = DrawTaps[self.params['draw_taps']]

        # create masters
        inv_params = self.params.copy(remove=['draw_taps'], append=dict(is_guarded=True))
        master = self.new_template(InvChainCore, params=inv_params)
        inv_ncol = master.num_cols

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1

        sep = max(self.min_sep_col, self.get_hm_sp_le_sep_col())
        # taps
        sub_sep = self.sub_sep_col
        sup_info = self.get_supply_column_info(xm_layer)
        num_taps = 0
        tap_offset = 0
        tap_left = tap_right = False
        if draw_taps in DrawTaps.RIGHT | DrawTaps.BOTH:
            num_taps += 1
            tap_right = True
        if draw_taps in DrawTaps.LEFT | DrawTaps.BOTH:
            num_taps += 1
            tap_offset += sup_info.ncol + sub_sep // 2
            tap_left = True

        # set total number of columns
        seg_tot = inv_ncol + (sup_info.ncol + sub_sep // 2) * num_taps
        self.set_mos_size(seg_tot)

        # --- Placement --- #
        cur_col = tap_offset
        inst = self.add_tile(master, 0, cur_col)
        cur_col += inv_ncol + sep

        # add taps
        lay_range = range(self.conn_layer, xm_layer + 1)
        vdd_table: Dict[int, List[WireArray]] = {lay: [] for lay in lay_range}
        vss_table: Dict[int, List[WireArray]] = {lay: [] for lay in lay_range}
        if tap_left:
            self.add_supply_column(sup_info, 0, vdd_table, vss_table)
        if tap_right:
            self.add_supply_column(sup_info, seg_tot, vdd_table, vss_table, flip_lr=True)

        # --- Routing --- #
        # 1. supplies
        self.connect_to_track_wires(inst.get_all_port_pins('VDD'), vdd_table[vm_layer])
        self.connect_to_track_wires(inst.get_all_port_pins('VDD'), vdd_table[self.conn_layer])

        self.connect_to_track_wires(inst.get_all_port_pins('VSS'), vss_table[vm_layer])
        self.connect_to_track_wires(inst.get_all_port_pins('VSS'), vss_table[self.conn_layer])

        vdd_xm = self.connect_wires(vdd_table[xm_layer])
        vss_xm = self.connect_wires(vss_table[xm_layer])

        self.add_pin('VDD', vdd_xm)
        self.add_pin('VSS', vss_xm)
        self.add_pin('VDD_vm', vdd_table[vm_layer], label='VDD')
        self.add_pin('VSS_vm', vss_table[vm_layer], label='VSS')

        self.reexport(inst.get_port('in'))
        self.reexport(inst.get_port('out'))

        # set properties
        self.sch_params = master.sch_params


class InvChainCoreWithTapRows(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return InvChainCore.get_params_info()

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return InvChainCore.get_default_param_values()

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_chain

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        # create masters
        tile_ptap = 0
        tile_logic = 1
        tile_ntap = 2
        logic_pinfo = self.get_tile_pinfo(tile_idx=tile_logic)
        inv_params = self.params.copy(append=dict(vertical_sup=True), remove=['pinfo'])
        master = self.new_template(InvChainCore, params=dict(pinfo=logic_pinfo, **inv_params))
        inv_ncol = master.num_cols

        # --- Placement --- #
        inst = self.add_tile(master, tile_logic, 0)
        self.add_substrate_contact(0, 0, tile_idx=tile_ptap, seg=inv_ncol)
        self.add_substrate_contact(0, 0, tile_idx=tile_ntap, seg=inv_ncol)

        self.set_mos_size()

        # --- Routing --- #
        # 1. supplies
        ptap_tid = self.get_track_id(0, MOSWireType.DS, 'sup', tile_idx=tile_ptap)
        vss_hm = self.connect_to_tracks(inst.get_all_port_pins('VSS'), ptap_tid)
        self.add_pin('VSS', vss_hm)

        ntap_tid = self.get_track_id(0, MOSWireType.DS, 'sup', tile_idx=tile_ntap)
        vdd_hm = self.connect_to_tracks(inst.get_all_port_pins('VDD'), ntap_tid)
        self.add_pin('VDD', vdd_hm)

        for pin in ['in', 'out', 'outb']:
            self.reexport(inst.get_port(pin))

        # set properties
        self.sch_params = master.sch_params


class InvChainCoreGuardRing(GuardRing):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        GuardRing.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return InvChainCoreWithTaps.get_schematic_class()

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        ans = dict(
            **InvChainCoreWithTaps.get_params_info(),
            pmos_gr='pmos guard ring tile name.',
            nmos_gr='nmos guard ring tile name.',
            edge_ncol='Number of columns on guard ring edge.  Use 0 for default.',
        )
        return ans

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        ans = dict(
            **InvChainCoreWithTaps.get_default_param_values(),
            pmos_gr='pgr',
            nmos_gr='ngr',
            edge_ncol=0,
        )
        return ans

    def get_layout_basename(self) -> str:
        return self.__class__.__name__

    def draw_layout(self) -> None:
        params = self.params
        pmos_gr: str = params['pmos_gr']
        nmos_gr: str = params['nmos_gr']
        edge_ncol: int = params['edge_ncol']

        core_params = params.copy(remove=['pmos_gr', 'nmos_gr', 'edge_ncol'])
        master = self.new_template(InvChainCoreWithTaps, params=core_params)

        sub_sep = master.sub_sep_col
        gr_sub_sep = master.gr_sub_sep_col
        sep_ncol_left = sep_ncol_right = sub_sep
        draw_taps: DrawTaps = DrawTaps[params['draw_taps']]
        if draw_taps in DrawTaps.RIGHT | DrawTaps.BOTH:
            sep_ncol_right = gr_sub_sep - sub_sep // 2
        if draw_taps in DrawTaps.LEFT | DrawTaps.BOTH:
            sep_ncol_left = gr_sub_sep - sub_sep // 2
        sep_ncol = (sep_ncol_left, sep_ncol_right)

        inst, sup_list = self.draw_guard_ring(master, pmos_gr, nmos_gr, sep_ncol, edge_ncol)
        vdd_hm_list, vss_hm_list = [], []
        for (vss_list, vdd_list) in sup_list:
            vss_hm_list.extend(vss_list)
            vdd_hm_list.extend(vdd_list)

        self.connect_to_track_wires(vss_hm_list, inst.get_all_port_pins('VSS_vm'))
        self.connect_to_track_wires(vdd_hm_list, inst.get_all_port_pins('VDD_vm'))

"""This module contains layout generators for logic unit, used for makings gates"""

from typing import Mapping, Any

from bag.util.immutable import Param
from bag.layout.template import TemplateDB

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase


# TODO: develop more examples
class LogicUnit(MOSBase):
    """A logic unit to built NAND/NOR gates.
    Based on BAG2 version
    """

    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg='number of segments.',
            w_p='pmos width. Defaults to using the width from pinfo',
            w_n='nmos width. Defaults to using the width from pinfo',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(w_p=None, w_n=None, ridx_p=-1, ridx_n=0,)

    def get_layout_basename(self) -> str:
        return 'unit_%dx' % self.params['seg']

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg: int = self.params['seg']
        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']

        if not w_p:
            w_p = self.place_info.get_row_place_info(-1).row_info.width
        if not w_n: 
            w_n = self.place_info.get_row_place_info(0).row_info.width

        # get track information
        hm_layer = self.conn_layer + 1

        # add blocks and collect wires
        pmos = self.add_mos(ridx_p, 0, seg, g_on_s=seg % 2, w=w_p)
        nmos = self.add_mos(ridx_n, 0, seg, g_on_s=seg % 2, w=w_n)
        self.set_mos_size()

        # draw VDD/VSS
        vss_tid = self.get_track_id(ridx_n, MOSWireType.DS, 'sup', 0)
        vdd_tid = self.get_track_id(ridx_p, MOSWireType.DS, 'sup', -1)
        sup_w = vss_tid.width
        xl, xr = self.bound_box.xl, self.bound_box.xh
        vss = self.add_wires(hm_layer, vss_tid.base_index, xl, xr, width=sup_w)
        vdd = self.add_wires(hm_layer, vdd_tid.base_index, xl, xr, width=sup_w)
        self.add_pin('VSS', vss)
        self.add_pin('VDD', vdd)

        # export
        self.add_pin('pg', pmos.g)
        self.add_pin('ps', pmos.s)
        self.add_pin('pd', pmos.d)
        self.add_pin('ng', nmos.g)
        self.add_pin('ns', nmos.s)
        self.add_pin('nd', nmos.d)

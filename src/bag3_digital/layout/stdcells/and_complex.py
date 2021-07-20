"""This module contains layout generator for complex AND gate with 2 - 9 inputs"""

from typing import Mapping, Any, Optional, Type, Sequence

from pybag.enum import MinLenMode, RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .gates import NAND2Core, NAND3Core, NOR2Core, NOR3Core, InvCore

from ...schematic.and_complex import bag3_digital__and_complex


class AndComplex(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)
        self._nand_in_list = []

    @property
    def nand_in_list(self) -> Sequence[int]:
        return self._nand_in_list

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__and_complex

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_dict='Dictionary of segments of standard cell components',
            num_in='Number of inputs',
            export_outb='True to export outb; True by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(export_outb=True)

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg_dict: Mapping[str, int] = self.params['seg_dict']
        num_in: int = self.params['num_in']
        export_outb: bool = self.params['export_outb']

        if num_in < 2 or num_in > 9:
            raise ValueError(f'num_in={num_in} has to be within 2 and 9.')

        sep_col = self.min_sep_col
        sep_col += sep_col & 1

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1

        # pick hm_layer tracks
        pd_tidx = self.get_track_index(1, MOSWireType.DS, 'sig', 1)
        pg1_tid = self.get_track_id(1, MOSWireType.G, 'sig', -1)
        pg1_tidx = self.get_track_index(1, MOSWireType.G, 'sig', -1)
        pg0_tidx = self.get_track_index(1, MOSWireType.G, 'sig', -2)
        ng1_tidx = self.get_track_index(0, MOSWireType.G, 'sig', 1)
        ng0_tidx = self.get_track_index(0, MOSWireType.G, 'sig', 0)
        ng0_tid = self.get_track_id(0, MOSWireType.G, 'sig', 0)
        nd_tidx = self.get_track_index(0, MOSWireType.DS, 'sig', -2)
        sig_locs_inv = {'nin': ng0_tidx, 'nin0': ng0_tidx, 'nin1': ng1_tidx, 'nin2': pg0_tidx}
        sig_locs_nor = {'nin': pg1_tidx, 'nin0': pg1_tidx, 'nin1': pg0_tidx, 'nin2': ng1_tidx, 'nout': nd_tidx,
                        'pout': pd_tidx}

        # nand configuration
        q, r = divmod(num_in, 3)
        if r == 0:
            nand_in_list = [3] * q
        elif r == 1:
            nand_in_list = [3] * (q - 1) + [2, 2]
        else:  # r == 2
            nand_in_list = [3] * q + [2]
        self._nand_in_list = nand_in_list
        nor_in = len(nand_in_list)
        nand_params = dict(pinfo=pinfo, seg=seg_dict['nand'], vertical_out=False)
        nand_out_list = []
        nand_sch_list = []
        cur_col = 0
        in_idx = 0
        vdd_list, vss_list = [], []
        prev_out_vm_tidx = self.grid.coord_to_track(vm_layer, 0, RoundMode.NEAREST)
        prev_out_vm_tidx = self.tr_manager.get_next_track(vm_layer, prev_out_vm_tidx, 'sig', 'sig', up=-1)
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')

        for nand_idx, nand_in in enumerate(nand_in_list):
            # make master
            back_idx = nor_in - 1 - nand_idx
            nand_params['sig_locs'] = sig_locs_nor if (back_idx & 1) else sig_locs_inv
            if nand_in == 3:
                _master = self.new_template(NAND3Core, params=nand_params)
            else:  # nand_n == 2
                _master = self.new_template(NAND2Core, params=nand_params)

            # find placement based on nand width and also vm_layer wires
            out_vm_tidx = self.tr_manager.get_next_track(vm_layer, prev_out_vm_tidx, 'sig', 'sig', up=nand_in * 2 + 1)
            out_vm_tidx2 = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + _master.num_cols),
                                                    RoundMode.NEAREST)
            if out_vm_tidx > out_vm_tidx2:
                _coord = self.grid.track_to_coord(vm_layer, out_vm_tidx)
                avail_col = -(- _coord // self.sd_pitch) - _master.num_cols
                offset = avail_col - cur_col
                cur_col += offset + (offset & 1)
                out_vm_tidx = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + _master.num_cols),
                                                       RoundMode.NEAREST)
            else:
                out_vm_tidx = out_vm_tidx2
            _inst = self.add_tile(_master, 0, cur_col)
            nand_sch_list.append(_master.sch_params)

            # supplies
            vdd_list.append(_inst.get_pin('VDD'))
            vss_list.append(_inst.get_pin('VSS'))

            # nand inputs
            for _in_idx in range(nand_in):
                self.reexport(_inst.get_port(f'nin<{_in_idx}>'), net_name=f'in<{in_idx}>', hide=False)
                in_idx += 1

            # nand output
            nand_out_vm = self.connect_to_tracks([_inst.get_pin('pout'), _inst.get_pin('nout')],
                                                 TrackID(vm_layer, out_vm_tidx, w_sig_vm))
            nand_out_list.append(nand_out_vm)
            self.add_pin(f'nand_out{nand_idx}', nand_out_vm, hide=True)

            # setup for next instance
            cur_col += _master.num_cols + sep_col
            prev_out_vm_tidx = out_vm_tidx

        # nor configuration
        if nor_in == 3:
            nor_master = self.new_template(NOR3Core,
                                           params=dict(pinfo=pinfo, seg=seg_dict['nor'], vertical_out=False,
                                                       sig_locs=sig_locs_nor))
        elif nor_in == 2:
            nor_master = self.new_template(NOR2Core,
                                           params=dict(pinfo=pinfo, seg=seg_dict['nor'], vertical_out=False,
                                                       sig_locs=sig_locs_nor))
        else:
            nor_master = self.new_template(InvCore,
                                           params=dict(pinfo=pinfo, seg=seg_dict['inv'], vertical_out=False,
                                                       sig_locs=sig_locs_nor))
        # find placement based on nor width and also vm_layer wires
        out_vm_tidx = self.tr_manager.get_next_track(vm_layer, prev_out_vm_tidx, 'sig', 'sig', up=nor_in + 1)
        out_vm_tidx2 = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + nor_master.num_cols),
                                                RoundMode.NEAREST)
        if out_vm_tidx > out_vm_tidx2:
            _coord = self.grid.track_to_coord(vm_layer, out_vm_tidx)
            avail_col = -(- _coord // self.sd_pitch) - nor_master.num_cols
            offset = avail_col - cur_col
            cur_col += offset + (offset & 1)
            out_vm_tidx = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + nor_master.num_cols),
                                                   RoundMode.NEAREST)
        else:
            out_vm_tidx = out_vm_tidx2
        nor = self.add_tile(nor_master, 0, cur_col)
        cur_col += nor_master.num_cols
        vdd_list.append(nor.get_pin('VDD'))
        vss_list.append(nor.get_pin('VSS'))

        # nor output
        out_vm = self.connect_to_tracks([nor.get_pin('pout'), nor.get_pin('nout')],
                                        TrackID(vm_layer, out_vm_tidx, w_sig_vm))
        out_hm = self.connect_to_tracks(out_vm, ng0_tid, min_len_mode=MinLenMode.UPPER)

        # nor inputs: find xm_layer tracks
        vdd_xm_tidx = self.grid.coord_to_track(xm_layer, vdd_list[-1].bound_box.ym, RoundMode.NEAREST)
        vss_xm_tidx = self.grid.coord_to_track(xm_layer, vss_list[-1].bound_box.ym, RoundMode.NEAREST)
        xm_locs = self.tr_manager.spread_wires(xm_layer, ['sup'] + ['sig'] * nor_in + ['sup'], vss_xm_tidx,
                                               vdd_xm_tidx, ('sup', 'sig'))
        vm_locs = self.tr_manager.spread_wires(vm_layer, ['sig'] * (nor_in + 2), prev_out_vm_tidx, out_vm_tidx,
                                               ('sig', 'sig'))
        w_sig_xm = self.tr_manager.get_width(xm_layer, 'sig')
        for _idx in range(nor_in):
            _nor_in = self.connect_to_tracks(nor.get_pin(f'nin<{_idx}>'), TrackID(vm_layer, vm_locs[1 + _idx],
                                             w_sig_vm), min_len_mode=MinLenMode.MIDDLE)
            self.connect_to_tracks([_nor_in, nand_out_list[_idx]], TrackID(xm_layer, xm_locs[-2 - _idx], w_sig_xm))

        # output inverter
        if export_outb:
            cur_col += sep_col
            inv_master = self.new_template(InvCore,
                                           params=dict(pinfo=pinfo, seg=seg_dict['inv'],
                                                       sig_locs=sig_locs_inv))
            out_inv = self.add_tile(inv_master, 0, cur_col)
            cur_col += inv_master.num_cols
            inv_sch = inv_master.sch_params
            vdd_list.append(out_inv.get_pin('VDD'))
            vss_list.append(out_inv.get_pin('VSS'))

            out_hm = self.connect_wires([out_hm, out_inv.get_pin('nin')])
            outb_hm = self.connect_to_tracks(out_inv.get_pin('out'), pg1_tid, min_len_mode=MinLenMode.UPPER)
            self.add_pin('outb', outb_hm)
        else:
            inv_sch = None
        self.add_pin('out', out_hm)

        self.set_mos_size()

        # supplies
        self.add_pin('VDD', self.connect_wires(vdd_list))
        self.add_pin('VSS', self.connect_wires(vss_list))

        self.sch_params = dict(
            nand_params_list=nand_sch_list,
            nor_params=nor_master.sch_params,
            inv_params=inv_sch,
            export_outb=export_outb,
        )
